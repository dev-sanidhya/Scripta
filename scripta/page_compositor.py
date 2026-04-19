"""
Page compositor — lays out text on a page template and handles pagination.

Page styles:
  - ruled      : horizontal lines, pink margin line (classic notebook)
  - college    : narrower line spacing, like college-ruled paper
  - grid       : graph paper grid
  - blank      : plain white/cream
  - parchment  : aged cream paper, no lines

Each page is created as a PIL Image. The compositor places words line by
line using the renderer, handles line wrapping, paragraph breaks, and
page breaks. Returns a list of finished page images.
"""

from typing import List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw

import config
from scripta.glyph_store import GlyphStore
from scripta.renderer import Renderer
from scripta.variation_engine import WriterState
from scripta import artifact_sim


PAGE_STYLES = {
    # line_spacing values are in px at 200 DPI.
    # Real wide-ruled paper: 8.7mm ≈ 69px. College-ruled: 7.1mm ≈ 56px.
    "ruled": {
        "bg": (252, 251, 245),
        "line_color": (176, 196, 222),
        "line_spacing": 69,
        "margin_line": True,
        "grid": False,
    },
    "college": {
        "bg": (252, 251, 245),
        "line_color": (176, 196, 222),
        "line_spacing": 56,
        "margin_line": True,
        "grid": False,
    },
    "grid": {
        "bg": (250, 250, 255),
        "line_color": (200, 210, 230),
        "line_spacing": 48,
        "margin_line": False,
        "grid": True,
    },
    "blank": {
        "bg": (253, 252, 248),
        "line_color": None,
        "line_spacing": 69,
        "margin_line": False,
        "grid": False,
    },
    "parchment": {
        "bg": (240, 225, 185),
        "line_color": None,
        "line_spacing": 69,
        "margin_line": False,
        "grid": False,
    },
}


def _create_page_background(style: dict) -> Image.Image:
    """Draw the bare page with ruling/grid lines."""
    page = Image.new("RGB", (config.PAGE_W, config.PAGE_H), style["bg"])
    draw = ImageDraw.Draw(page)

    line_spacing = style["line_spacing"]
    line_color = style["line_color"]

    if style["grid"]:
        # Horizontal lines
        y = config.MARGIN_TOP
        while y < config.PAGE_H - config.MARGIN_BOTTOM:
            draw.line([(config.MARGIN_LEFT, y), (config.PAGE_W - config.MARGIN_RIGHT, y)],
                      fill=line_color, width=1)
            y += line_spacing
        # Vertical lines
        x = config.MARGIN_LEFT
        while x < config.PAGE_W - config.MARGIN_RIGHT:
            draw.line([(x, config.MARGIN_TOP), (x, config.PAGE_H - config.MARGIN_BOTTOM)],
                      fill=line_color, width=1)
            x += line_spacing

    elif line_color is not None:
        y = config.MARGIN_TOP + line_spacing
        while y < config.PAGE_H - config.MARGIN_BOTTOM:
            draw.line([(0, y), (config.PAGE_W, y)], fill=line_color, width=1)
            y += line_spacing

    if style.get("margin_line"):
        draw.line(
            [(config.MARGIN_LEFT, 0), (config.MARGIN_LEFT, config.PAGE_H)],
            fill=config.MARGIN_LINE_COLOR,
            width=2,
        )

    return page


class PageCompositor:
    def __init__(
        self,
        glyph_store: GlyphStore,
        writer_id: Optional[str] = None,
        ink_color: str = config.DEFAULT_INK,
        page_style: str = "ruled",
        apply_artifacts: bool = True,
        seed: Optional[int] = None,
    ):
        if page_style not in PAGE_STYLES:
            raise ValueError(f"Unknown page style '{page_style}'. Choose from: {list(PAGE_STYLES)}")

        self.style = PAGE_STYLES[page_style]
        self.apply_artifacts = apply_artifacts

        # Pick a writer — random if not specified
        rng = np.random.default_rng(seed)
        if writer_id is None and glyph_store.writers:
            writer_id = str(rng.choice(glyph_store.writers))

        self.writer_state = WriterState(
            writer_id=writer_id or "default",
            ink_color=ink_color,
            seed=int(rng.integers(0, 2**31)),
        )

        self.renderer = Renderer(
            glyph_store=glyph_store,
            writer_state=self.writer_state,
            target_height=int(self.style["line_spacing"] * 0.80),
            word_spacing=config.WORD_SPACING,
        )

        self._line_spacing = self.style["line_spacing"]
        self._write_area_w = config.PAGE_W - config.MARGIN_LEFT - config.MARGIN_RIGHT
        self._write_area_h = config.PAGE_H - config.MARGIN_TOP - config.MARGIN_BOTTOM

    def render(self, paragraphs: List[List[str]]) -> List[Image.Image]:
        """
        Render a document (list of paragraphs, each a list of words).
        Returns a list of finished page PIL Images.
        """
        pages: List[Image.Image] = []
        page = _create_page_background(self.style)

        # RGBA for compositing
        canvas = page.convert("RGBA")

        line_y = config.MARGIN_TOP + self._line_spacing
        line_idx = 0

        for para_idx, paragraph in enumerate(paragraphs):
            if not paragraph:
                # Empty paragraph = blank line gap
                line_y += self._line_spacing
                if line_y >= config.PAGE_H - config.MARGIN_BOTTOM:
                    pages.append(self._finish_page(canvas))
                    page = _create_page_background(self.style)
                    canvas = page.convert("RGBA")
                    line_y = config.MARGIN_TOP + self._line_spacing
                    line_idx = 0
                continue

            self.writer_state.on_paragraph_start()

            # Build lines by wrapping words
            lines = self._wrap_words(paragraph)

            for line_words in lines:
                self.writer_state.on_line_start(line_idx)

                # Check page overflow
                if line_y >= config.PAGE_H - config.MARGIN_BOTTOM:
                    pages.append(self._finish_page(canvas))
                    page = _create_page_background(self.style)
                    canvas = page.convert("RGBA")
                    line_y = config.MARGIN_TOP + self._line_spacing
                    line_idx = 0
                    self.writer_state.on_paragraph_start()

                # Indent first line of paragraph slightly
                x = config.MARGIN_LEFT
                if line_words is lines[0] and para_idx > 0:
                    x += int(self._line_spacing * 1.2)

                for word in line_words:
                    if x + self.renderer.word_width_estimate(word) > config.PAGE_W - config.MARGIN_RIGHT:
                        break
                    x = self.renderer.render_word(canvas, word, x, line_y)

                line_y += self._line_spacing
                line_idx += 1

        if canvas:
            pages.append(self._finish_page(canvas))

        return pages

    def _wrap_words(self, words: List[str]) -> List[List[str]]:
        """Greedy word wrap based on estimated widths."""
        lines: List[List[str]] = []
        current_line: List[str] = []
        current_w = 0

        for word in words:
            ww = self.renderer.word_width_estimate(word)
            indent = int(self._line_spacing * 1.2) if not lines else 0
            available = self._write_area_w - indent

            if current_w + ww > available and current_line:
                lines.append(current_line)
                current_line = [word]
                current_w = ww
            else:
                current_line.append(word)
                current_w += ww

        if current_line:
            lines.append(current_line)

        return lines

    def _finish_page(self, canvas: Image.Image) -> Image.Image:
        """Flatten RGBA canvas to RGB and apply artifact simulation."""
        white_bg = Image.new("RGB", canvas.size, (255, 255, 255))
        white_bg.paste(canvas.convert("RGB"), mask=canvas.split()[3])

        if self.apply_artifacts:
            white_bg = artifact_sim.apply_all(
                white_bg,
                fatigue_level=self.writer_state.fatigue,
            )

        return white_bg
