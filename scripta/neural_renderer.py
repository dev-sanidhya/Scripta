"""
NeuralRenderer — line-level handwriting synthesis via VATr++.
Wraps the VATr++ Writer to generate realistic handwriting lines in IAM writer styles.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

import config

VATRPP_DIR = Path(__file__).parent.parent / "VATr-pp"
STYLE_DIR = VATRPP_DIR / "files" / "style_samples"


def _vatrpp_on_path() -> None:
    s = str(VATRPP_DIR)
    if s not in sys.path:
        sys.path.insert(0, s)


class _ChdirCtx:
    """Context manager: chdir to VATr-pp dir, restore on exit."""
    def __init__(self):
        self._orig = None

    def __enter__(self):
        self._orig = os.getcwd()
        os.chdir(VATRPP_DIR)
        return self

    def __exit__(self, *_):
        os.chdir(self._orig)


class NeuralRenderer:
    """
    Generates handwriting lines using VATr++ neural style transfer.
    Each line is rendered as an RGBA PIL Image (ink colored, transparent background).
    """

    def __init__(self):
        self._writer = None
        self._current_style: Optional[str] = None
        self._loaded = False

    def load(self, verbose: bool = True) -> None:
        if self._loaded:
            return

        _vatrpp_on_path()

        with _ChdirCtx():
            import torch
            from generate.writer import Writer
            from util.misc import FakeArgs

            checkpoint = VATRPP_DIR / "files" / "vatrpp.pth"
            if not checkpoint.exists():
                raise FileNotFoundError(
                    f"VATr++ checkpoint not found at {checkpoint}. "
                    "Run the VATr-pp setup steps first."
                )

            args = FakeArgs()
            # Override relative paths inside FakeArgs to absolute so we can
            # chdir back after loading without breaking anything.
            args.feat_model_path = str(VATRPP_DIR / "files" / "resnet_18_pretrained.pth")

            self._writer = Writer(str(checkpoint), args, only_generator=True)
            self._writer.model.eval()
            self._loaded = True

            if verbose:
                device = args.device
                print(f"NeuralRenderer ready  (device={device})")

    def available_styles(self) -> List[str]:
        if not STYLE_DIR.exists():
            return []
        return sorted(d.name for d in STYLE_DIR.iterdir() if d.is_dir())

    def set_style(self, writer_id: str) -> None:
        """Choose a handwriting style by IAM writer ID (e.g. 'a01')."""
        if not self._loaded:
            self.load()

        folder = STYLE_DIR / writer_id
        if not folder.exists():
            avail = self.available_styles()
            raise ValueError(
                f"Style '{writer_id}' not found in {STYLE_DIR}. "
                f"Available: {avail[:8]}"
            )

        with _ChdirCtx():
            self._writer.set_style_folder(str(folder))

        self._current_style = writer_id

    def render_line(
        self,
        text: str,
        target_height: int = config.GLYPH_TARGET_HEIGHT,
        ink_rgb: Tuple[int, int, int] = (20, 20, 30),
    ) -> Optional[Image.Image]:
        """
        Generate one line of handwriting.

        Returns an RGBA PIL Image scaled to *target_height* pixels tall.
        Background is transparent; ink pixels use *ink_rgb*.
        Returns None if generation fails.
        """
        if not self._loaded:
            self.load()
        if self._current_style is None:
            raise ValueError("Call set_style(writer_id) before rendering.")
        if not text.strip():
            return None

        import cv2

        with _ChdirCtx():
            fakes = self._writer.generate([text], align_words=False)

        if not fakes:
            return None

        fake = fakes[0]  # uint8 (H, W): ~0=ink, ~255=paper

        # Scale from VATr++ native 32 px to requested height
        h, w = fake.shape[:2]
        if h != target_height:
            scale = target_height / h
            new_w = max(1, int(w * scale))
            fake = cv2.resize(fake, (new_w, target_height), interpolation=cv2.INTER_LANCZOS4)

        # Build RGBA: dark ink → opaque, white paper → transparent
        alpha = (255 - fake).astype(np.uint8)
        rgba = np.zeros((fake.shape[0], fake.shape[1], 4), dtype=np.uint8)
        rgba[:, :, 0] = ink_rgb[0]
        rgba[:, :, 1] = ink_rgb[1]
        rgba[:, :, 2] = ink_rgb[2]
        rgba[:, :, 3] = alpha

        return Image.fromarray(rgba, "RGBA")
