"""
Glyph renderer — takes a word/char image from GlyphStore,
applies WriterState perturbation params, and composites it onto a canvas.

Two modes:
  - Word mode  : paste a full word image (preferred, looks best)
  - Char mode  : compose word letter-by-letter (fallback for OOV words)
"""

import math
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageChops

import config
from scripta.glyph_store import GlyphStore
from scripta.variation_engine import WriterState, GlyphParams


def _recolor(img: Image.Image, ink_rgb: Tuple[int, int, int]) -> Image.Image:
    """Replace dark pixels in a grayscale glyph with ink_rgb."""
    img = img.convert("RGBA")
    r, g, b, a = img.split()

    # Luminance mask: dark pixels → ink, light pixels → transparent
    gray = np.array(img.convert("L"), dtype=np.float32)
    mask = np.clip((255 - gray) / 255.0, 0, 1)

    r_ch = np.full_like(gray, ink_rgb[0])
    g_ch = np.full_like(gray, ink_rgb[1])
    b_ch = np.full_like(gray, ink_rgb[2])
    a_ch = (mask * 255).astype(np.uint8)

    out = Image.merge("RGBA", [
        Image.fromarray(r_ch.astype(np.uint8)),
        Image.fromarray(g_ch.astype(np.uint8)),
        Image.fromarray(b_ch.astype(np.uint8)),
        Image.fromarray(a_ch),
    ])
    return out


def _scale_to_height(img: Image.Image, target_h: int) -> Image.Image:
    """Scale image so its height equals target_h, preserving aspect ratio."""
    w, h = img.size
    if h == 0:
        return img
    new_w = max(1, int(w * target_h / h))
    return img.resize((new_w, target_h), Image.LANCZOS)


def _apply_params(img: Image.Image, params: GlyphParams) -> Image.Image:
    """Apply scale, rotation, slant to the glyph image."""
    w, h = img.size

    # Scale
    new_w = max(1, int(w * params.scale))
    new_h = max(1, int(h * params.scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Rotation (small, around center)
    if abs(params.rotate_deg) > 0.1:
        img = img.rotate(
            params.rotate_deg,
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )

    # Slant via affine shear
    if abs(params.slant) > 0.5:
        shear = math.tan(math.radians(params.slant))
        w2, h2 = img.size
        # Horizontal shear: x' = x + shear*y
        data = (1, shear, -shear * h2 / 2, 0, 1, 0)
        img = img.transform(
            (w2 + int(abs(shear) * h2), h2),
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
        Render `word` onto `canvas` at (x, y).
        Returns the x coordinate after the word (including spacing).
        """
        # Advance writer state for this word
        self.state.on_word(word)
        params = self.state.next_word_params(word)

        # Try word-level image first
        glyph = self.store.get_word_image(word, self.state.writer_id, self._rng)

        if glyph is None:
            # Fallback: compose character by character
            return self._render_word_from_chars(canvas, word, x, y, params)

        # Normalize height
        glyph = _scale_to_height(glyph, self.target_height)

        # Recolor to ink
        glyph = _recolor(glyph, self.ink_rgb)

        # Apply variation
        glyph = _apply_params(glyph, params)
        glyph = _apply_alpha(glyph, params.alpha)

        # Compute paste position with offsets + baseline drift
        paste_x = int(x + params.offset_x)
        paste_y = int(y - glyph.height + params.offset_y + params.baseline_y)
        paste_y = max(0, paste_y)

        # Composite onto canvas
        canvas.paste(glyph, (paste_x, paste_y), glyph)

        advance = paste_x + glyph.width + int(self.word_spacing * params.spacing_factor)
        return advance

    def _render_word_from_chars(
        self,
        canvas: Image.Image,
        word: str,
        x: int,
        y: int,
        word_params: GlyphParams,
    ) -> int:
        """Compose word glyph-by-glyph when word image is unavailable."""
        cursor_x = x

        for char in word:
            if char.isspace():
                cursor_x += self.word_spacing
                continue

            char_params = self.state.next_glyph(char)
            glyph = self.store.get_char_image(char, self.state.writer_id, self._rng)

            if glyph is None:
                # Character truly unavailable — skip with spacing
                cursor_x += int(self.target_height * 0.45)
                continue

            glyph = _scale_to_height(glyph, self.target_height)
            glyph = _recolor(glyph, self.ink_rgb)
            glyph = _apply_params(glyph, char_params)
            glyph = _apply_alpha(glyph, char_params.alpha)

            paste_x = int(cursor_x + char_params.offset_x)
            paste_y = int(y - glyph.height + char_params.offset_y + char_params.baseline_y)
            paste_y = max(0, paste_y)

            canvas.paste(glyph, (paste_x, paste_y), glyph)
            cursor_x = paste_x + glyph.width + self.char_spacing

        return cursor_x + int(self.word_spacing * word_params.spacing_factor)

    def word_width_estimate(self, word: str) -> int:
        """Rough width estimate for line-wrap planning (no rendering)."""
        return int(len(word) * self.target_height * 0.55 + self.word_spacing)
