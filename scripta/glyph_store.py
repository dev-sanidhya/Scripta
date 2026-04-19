"""
GlyphStore — font-based glyph source.

Phase 1: Uses handwriting fonts (Caveat, etc.) as the glyph source.
         The variation engine + artifact simulation are what make it undetectable.

Phase 5 (future): Will be replaced/augmented by VATr neural style transfer
                  using the IAM line images as style references.

IAM line images in data/iam/ are already downloaded and will be used in Phase 5
as style reference inputs to VATr (one image per writer style).
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config


# Available font styles — maps style name → font file
FONT_STYLES: Dict[str, Path] = {}

def _discover_fonts() -> None:
    for f in config.FONTS_DIR.glob("*.ttf"):
        FONT_STYLES[f.stem] = f

_discover_fonts()


# Writer personality seeds — maps "writer ID" to a font + personality seed
# This simulates having multiple distinct writers
_WRITER_DEFINITIONS = [
    ("w01", "Caveat-Regular",  12),
    ("w02", "Caveat-Regular",  99),
    ("w03", "Caveat-Regular",  37),
    ("w04", "Caveat-Bold",     55),
    ("w05", "Caveat-Bold",     81),
    ("w06", "Caveat-Regular", 120),
    ("w07", "Caveat-Bold",    200),
    ("w08", "Caveat-Regular", 314),
    ("w09", "Caveat-Regular",  77),
    ("w10", "Caveat-Bold",    500),
]


class GlyphStore:
    """
    Provides rendered glyph images for individual characters and words.
    Font is rendered at high size then scaled down — preserves stroke quality.
    """

    def __init__(self, data_dir: Path = config.DATA_DIR):
        self.data_dir = data_dir
        self._fonts: Dict[str, ImageFont.FreeTypeFont] = {}
        self._writer_map: Dict[str, dict] = {}
        self.writers: List[str] = []
        self._loaded = False

        # IAM line images — available for Phase 5 neural upgrade
        self.iam_lines_dir = data_dir / "data_subset" / "data_subset"

    def load(self, verbose: bool = True) -> None:
        if self._loaded:
            return

        _discover_fonts()

        if not FONT_STYLES:
            raise FileNotFoundError(
                f"No .ttf fonts found in {config.FONTS_DIR}. "
                "Run setup to download fonts."
            )

        # Load all fonts at render size
        render_size = config.GLYPH_TARGET_HEIGHT * 3  # render 3x, scale down
        for name, path in FONT_STYLES.items():
            try:
                self._fonts[name] = ImageFont.truetype(str(path), size=render_size)
            except Exception as e:
                if verbose:
                    print(f"Warning: could not load font {name}: {e}")

        # Build writer map from definitions
        for writer_id, font_name, seed in _WRITER_DEFINITIONS:
            font_key = font_name if font_name in self._fonts else list(self._fonts.keys())[0]
            self._writer_map[writer_id] = {
                "font_key": font_key,
                "seed": seed,
            }

        self.writers = list(self._writer_map.keys())
        self._loaded = True

        if verbose:
            iam_count = len(list(self.iam_lines_dir.glob("*.png"))) if self.iam_lines_dir.exists() else 0
            print(f"GlyphStore loaded: {len(self.writers)} writer styles, "
                  f"{len(self._fonts)} fonts, "
                  f"{iam_count} IAM style-reference images available")

    def _get_font(self, writer_id: str) -> ImageFont.FreeTypeFont:
        info = self._writer_map.get(writer_id, list(self._writer_map.values())[0])
        return self._fonts[info["font_key"]]

    def render_char(
        self,
        char: str,
        writer_id: str,
        target_height: int = config.GLYPH_TARGET_HEIGHT,
    ) -> Optional[Image.Image]:
        """Render a single character and return as RGBA image."""
        if not char.strip():
            return None

        font = self._get_font(writer_id)

        # Render at high resolution, then scale down
        render_size = target_height * 3
        font_hr = ImageFont.truetype(str(FONT_STYLES[self._writer_map[writer_id]["font_key"]]),
                                      size=render_size)

        # Measure bounding box
        dummy = Image.new("RGBA", (render_size * 2, render_size * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.textbbox((0, 0), char, font=font_hr)
        w = max(1, bbox[2] - bbox[0] + 8)
        h = max(1, bbox[3] - bbox[1] + 8)

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((-bbox[0] + 4, -bbox[1] + 4), char, font=font_hr, fill=(0, 0, 0, 255))

        # Scale down to target height
        scale = target_height / h
        new_w = max(1, int(w * scale))
        img = img.resize((new_w, target_height), Image.LANCZOS)

        return img

    def render_word(
        self,
        word: str,
        writer_id: str,
        target_height: int = config.GLYPH_TARGET_HEIGHT,
    ) -> Optional[Image.Image]:
        """Render a full word as a single RGBA image (better ligature quality)."""
        if not word.strip():
            return None

        font_name = self._writer_map.get(writer_id, list(self._writer_map.values())[0])["font_key"]
        render_size = target_height * 3
        font_hr = ImageFont.truetype(str(FONT_STYLES[font_name]), size=render_size)

        dummy = Image.new("RGBA", (render_size * len(word) * 2, render_size * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.textbbox((0, 0), word, font=font_hr)
        w = max(1, bbox[2] - bbox[0] + 12)
        h = max(1, bbox[3] - bbox[1] + 12)

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((-bbox[0] + 6, -bbox[1] + 6), word, font=font_hr, fill=(0, 0, 0, 255))

        scale = target_height / h
        new_w = max(1, int(w * scale))
        img = img.resize((new_w, target_height), Image.LANCZOS)

        return img

    def get_word_image(self, word: str, writer_id: Optional[str] = None,
                       rng: Optional[np.random.Generator] = None) -> Optional[Image.Image]:
        if writer_id is None:
            writer_id = self.writers[0]
        return self.render_word(word, writer_id)

    def get_char_image(self, char: str, writer_id: Optional[str] = None,
                       rng: Optional[np.random.Generator] = None) -> Optional[Image.Image]:
        if writer_id is None:
            writer_id = self.writers[0]
        return self.render_char(char, writer_id)

    def available_writers(self) -> List[str]:
        return self.writers

    def writer_vocabulary(self, writer_id: str) -> List[str]:
        return ["<any word — font-based rendering>"]

    def get_iam_style_image(self, writer_prefix: str) -> Optional[Image.Image]:
        """Return a random IAM line image for the given writer prefix (for Phase 5)."""
        if not self.iam_lines_dir.exists():
            return None
        matches = list(self.iam_lines_dir.glob(f"{writer_prefix}-*.png"))
        if not matches:
            return None
        import random
        path = random.choice(matches)
        return Image.open(path).convert("RGB")
