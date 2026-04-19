"""
Renderer — composites glyph images onto a canvas with WriterState perturbations.

Font-rendered glyphs come in as RGBA images. We apply:
  - Recolor (white → transparent, black → ink color)
  - Scale, rotate, slant (from GlyphParams)
  - Alpha (opacity from fatigue)
  - Paste onto canvas at position + baseline drift
"""

import math
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

import config
from scripta.glyph_store import GlyphStore
from scripta.variation_engine import WriterState, GlyphParams


def _recolor(img: Image.Image, ink_rgb: Tuple[int, int, int]) -> Image.Image:
    """Replace glyph color with ink_rgb, preserving the source alpha channel."""
    img = img.convert("RGBA")
    _, _, _, a = img.split()
    a_arr = np.array(a, dtype=np.uint8)

    out = np.zeros((img.height, img.width, 4), dtype=np.uint8)
    out[:, :, 0] = ink_rgb[0]
    out[:, :, 1] = ink_rgb[1]
    out[:, :, 2] = ink_rgb[2]
    out[:, :, 3] = a_arr

    return Image.fromarray(out, "RGBA")


def _apply_params(img: Image.Image, params: GlyphParams) -> Image.Image:
    """Apply scale, rotation, and slant shear to the glyph."""
    w, h = img.size

    # Scale
    new_w = max(1, int(w * params.scale))
    new_h = max(1, int(h * params.scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Rotation
    if abs(params.rotate_deg) > 0.2:
        img = img.rotate(
            params.rotate_deg,
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )

    # Slant (horizontal shear)
    if abs(params.slant) > 0.8:
        shear = math.tan(math.radians(params.slant * 0.4))  # dampen slant for fonts
        w2, h2 = img.size
        extra_w = int(abs(shear) * h2)
        offset = -shear * h2 / 2 if shear > 0 else -shear * h2 / 2
        data = (1, shear, offset, 0, 1, 0)
        img = img.transform(
            (w2 + extra_w, h2),
            Image.AFFINE,
            data,
            resample=Image.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )

    return img


def _apply_alpha(img: Image.Image, alpha: float) -> Image.Image:
    if abs(alpha - 1.0) < 0.01:
        return img
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * alpha))
    return Image.merge("RGBA", [r, g, b, a])


def _add_stroke_variation(img: Image.Image, tremor: float) -> Image.Image:
    """Subtle edge roughness — simulates pen nib/ball inconsistency."""
    if tremor < 0.05:
        return img
    # Very slight blur on high tremor (pen wobble softens edges)
    radius = tremor * 0.6
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


class Renderer:
    def __init__(
        self,
        glyph_store: GlyphStore,
        writer_state: WriterState,
        target_height: int = config.GLYPH_TARGET_HEIGHT,
        word_spacing: int = config.WORD_SPACING,
        char_spacing: int = config.CHAR_SPACING,
    ):
        self.store = glyph_store
        self.state = writer_state
        self.target_height = target_height
        self.word_spacing = word_spacing
        self.char_spacing = char_spacing
        self.ink_rgb = config.INK_COLORS[writer_state.ink_color]
        self._rng = np.random.default_rng()

    def render_word(
        self,
        canvas: Image.Image,
        word: str,
        x: int,
        y: int,
    ) -> int:
        """
        Render `word` onto `canvas` at baseline position (x, y).
        Returns the x coordinate after the word (ready for next word).
        """
        self.state.on_word(word)
        params = self.state.next_word_params(word)

        # Get word image from store (font-rendered)
        glyph = self.store.get_word_image(word, self.state.writer_id, self._rng)
        if glyph is None:
            return x + self.word_width_estimate(word)

        # Recolor to ink
        glyph = _recolor(glyph, self.ink_rgb)

        # Apply variation transforms
        glyph = _apply_params(glyph, params)
        glyph = _add_stroke_variation(glyph, params.tremor)
        glyph = _apply_alpha(glyph, params.alpha)

        # Position: x is left edge, y is baseline — glyph hangs above
        paste_x = int(x + params.offset_x)
        paste_y = int(y - glyph.height + params.offset_y + params.baseline_y)

        # Keep within canvas bounds
        paste_x = max(0, min(paste_x, canvas.width - 1))
        paste_y = max(0, min(paste_y, canvas.height - glyph.height))

        canvas.paste(glyph, (paste_x, paste_y), glyph)

        advance = paste_x + glyph.width + int(self.word_spacing * params.spacing_factor)
        return advance

    def word_width_estimate(self, word: str) -> int:
        """Fast width estimate for line-wrap pre-computation."""
        # Font-based: ~0.55× height per character is a good estimate for Caveat
        return int(len(word) * self.target_height * 0.52 + self.word_spacing)
