"""
NeuralPageCompositor — full-page handwriting via VATr++ neural rendering.
Generates each text line with VATr++, applies WriterState drift, and
assembles pages with the same artifact pipeline as PageCompositor.
"""

import random
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

import config
from scripta.neural_renderer import NeuralRenderer
from scripta.page_compositor import _create_page_background, PAGE_STYLES
from scripta.variation_engine import WriterState
from scripta import artifact_sim


# Approximate VATr++ char width at 32 px height (px per character including gaps).
# Used for word-wrap estimation before generating.
_PX_PER_CHAR_AT_32 = 10.0


def _estimate_line_width(words: List[str], target_height: int) -> int:
    """Rough width estimate for a joined line at *target_height* px."""
    text = " ".join(words)
    return int(len(text) * _PX_PER_CHAR_AT_32 * target_height / 32)


class NeuralPageCompositor:
    """
    Renders a document to pages using VATr++ for line-level handwriting synthesis.

    Args:
        neural_renderer: Loaded NeuralRenderer with a style already set.
        writer_id: Logical writer ID (used for WriterState personality; independent
                   of the VATr++ style folder chosen via neural_renderer.set_style).
        ink_color: One of 'blue', 'black', 'pencil'.
        page_style: One of 'ruled', 'college', 'grid', 'blank', 'parchment'.
        apply_artifacts: Whether to run the artifact simulation pipeline.
        seed: Random seed for reproducible output.
    """

    def __init__(
        self,
        neural_renderer: NeuralRenderer,
        writer_id: Optional[str] = None,
        ink_color: str = config.DEFAULT_INK,
        page_style: str = "ruled",
        apply_artifacts: bool = True,
        seed: Optional[int] = None,
    ):
        if page_style not in PAGE_STYLES:
            raise ValueError(f"Unknown page style '{page_style}'. Choose: {list(PAGE_STYLES)}")

        self.neural = neural_renderer
        self.style = PAGE_STYLES[page_style]
        self.apply_artifacts = apply_artifacts
        self.ink_rgb: Tuple[int, int, int] = config.INK_COLORS[ink_color]

        rng = np.random.default_rng(seed)
        self.writer_state = WriterState(
            writer_id=writer_id or "neural",
            ink_color=ink_color,
            seed=int(rng.integers(0, 2**31)),
        )

        self._line_spacing: int = self.style["line_spacing"]
        # Target glyph height: same proportion as font-based compositor
        self._target_h: int = int(self._line_spacing * 0.80)
        self._write_w: int = config.PAGE_W - config.MARGIN_LEFT - config.MARGIN_RIGHT
        self._write_h: int = config.PAGE_H - config.MARGIN_TOP - config.MARGIN_BOTTOM

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, paragraphs: List[List[str]]) -> List[Image.Image]:
        """
        Render document paragraphs to a list of finished page images.

        *paragraphs* is a List[List[str]] where each inner list is the words
        of one paragraph. An empty inner list inserts a blank-line gap.
        """
        pages: List[Image.Image] = []
        canvas = self._new_canvas()
        line_y = config.MARGIN_TOP + self._line_spacing
        line_idx = 0

        for para_idx, paragraph in enumerate(paragraphs):
            if not paragraph:
                line_y += self._line_spacing
                if line_y >= config.PAGE_H - config.MARGIN_BOTTOM:
                    pages.append(self._finish(canvas))
                    canvas = self._new_canvas()
                    line_y = config.MARGIN_TOP + self._line_spacing
                    line_idx = 0
                continue

            self.writer_state.on_paragraph_start()
            lines = self._wrap_words(paragraph)

            for line_words in lines:
                self.writer_state.on_line_start(line_idx)

                if line_y >= config.PAGE_H - config.MARGIN_BOTTOM:
                    pages.append(self._finish(canvas))
                    canvas = self._new_canvas()
                    line_y = config.MARGIN_TOP + self._line_spacing
                    line_idx = 0
                    self.writer_state.on_paragraph_start()

                self._render_line(canvas, line_words, line_y, para_idx, line_words is lines[0])
                line_y += self._line_spacing
                line_idx += 1

        pages.append(self._finish(canvas))
        return pages

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_canvas(self) -> Image.Image:
        return _create_page_background(self.style).convert("RGBA")

    def _wrap_words(self, words: List[str]) -> List[List[str]]:
        """Greedy word wrap using estimated character widths."""
        lines: List[List[str]] = []
        current: List[str] = []
        current_chars = 0

        for word in words:
            # +1 for the space
            needed = len(word) + (1 if current else 0)
            joined_estimate = _estimate_line_width(current + [word], self._target_h)

            if joined_estimate > self._write_w and current:
                lines.append(current)
                current = [word]
                current_chars = len(word)
            else:
                current.append(word)
                current_chars += needed

        if current:
            lines.append(current)
        return lines

    def _render_line(
        self,
        canvas: Image.Image,
        words: List[str],
        line_y: int,
        para_idx: int,
        is_first_in_para: bool,
    ) -> None:
        """Generate and paste one line of VATr++ handwriting onto *canvas*."""
        text = " ".join(words)
        if not text.strip():
            return

        # Get WriterState perturbation for this line
        params = self.writer_state.next_word_params(words[0] if words else "the")
        baseline_drift = int(params.baseline_y)
        alpha_scale = params.alpha

        line_img = self.neural.render_line(text, self._target_h, self.ink_rgb)
        if line_img is None:
            return

        # Apply alpha dimming (fatigue / attention)
        if abs(alpha_scale - 1.0) > 0.01:
            r, g, b, a = line_img.split()
            a = a.point(lambda v: int(v * alpha_scale))
            line_img = Image.merge("RGBA", [r, g, b, a])

        # Paragraph indent on first line
        x = config.MARGIN_LEFT
        if is_first_in_para and para_idx > 0:
            x += int(self._line_spacing * 1.2)

        # If rendered line overflows write area, scale it down horizontally
        max_w = config.PAGE_W - config.MARGIN_RIGHT - x
        if line_img.width > max_w:
            new_h = line_img.height
            new_w = max_w
            line_img = line_img.resize((new_w, new_h), Image.LANCZOS)

        paste_y = line_y - self._target_h + baseline_drift
        paste_y = max(0, min(paste_y, canvas.height - self._target_h))

        canvas.paste(line_img, (x, paste_y), line_img)

    def _finish(self, canvas: Image.Image) -> Image.Image:
        white = Image.new("RGB", canvas.size, (255, 255, 255))
        white.paste(canvas.convert("RGB"), mask=canvas.split()[3])
        if self.apply_artifacts:
            white = artifact_sim.apply_all(white, fatigue_level=self.writer_state.fatigue)
        return white
