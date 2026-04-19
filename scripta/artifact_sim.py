"""
Physical artifact simulation — applied to the fully composited page image.

Layers applied in order:
  1. Ink bleed       — slight edge blur, simulates ink absorbing into paper
  2. Scan noise      — luminance noise, simulates scanner grain
  3. Paper texture   — multiply-blend a paper texture if one is available
  4. Vignette        — subtle darkening at corners (scanner lamp falloff)
  5. Slight warp     — micro-distortion, eliminates any pixel-perfect regularity
"""

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageChops, ImageDraw

import config

try:
    from opensimplex import noise2 as pnoise2
    _HAS_NOISE = True
except ImportError:
    _HAS_NOISE = False


def apply_ink_bleed(img: Image.Image, radius: float = 0.6) -> Image.Image:
    """Soften glyph edges — ink spreads slightly on paper grain."""
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_scan_noise(img: Image.Image, intensity: float = 6.0) -> Image.Image:
    """Add subtle luminance noise — simulates scanner sensor noise."""
    arr = np.array(img).astype(np.float32)
    noise = np.random.normal(0, intensity, arr.shape[:2])

    if arr.ndim == 3:
        for c in range(min(3, arr.shape[2])):
            arr[:, :, c] = np.clip(arr[:, :, c] + noise, 0, 255)
    else:
        arr = np.clip(arr + noise, 0, 255)

    return Image.fromarray(arr.astype(np.uint8), mode=img.mode)


def apply_paper_texture(
    page: Image.Image,
    texture_path: Optional[Path] = None,
    blend_alpha: float = 0.18,
) -> Image.Image:
    """
    Multiply-blend a paper texture over the page.
    If no texture file exists, synthesize a simple linen grain.
    """
    if texture_path and texture_path.exists():
        texture = Image.open(texture_path).convert("RGB").resize(page.size, Image.LANCZOS)
    else:
        texture = _synthesize_paper_grain(page.size)

    page_rgb = page.convert("RGB")
    blended = ImageChops.multiply(page_rgb, texture)
    out = Image.blend(page_rgb, blended, blend_alpha)

    if page.mode == "RGBA":
        r, g, b = out.split()
        _, _, _, a = page.split()
        out = Image.merge("RGBA", [r, g, b, a])

    return out


def _synthesize_paper_grain(size: Tuple[int, int]) -> Image.Image:
    """Generate a subtle cream paper grain texture using Perlin or fallback."""
    w, h = size
    arr = np.zeros((h, w), dtype=np.float32)

    if _HAS_NOISE:
        scale = 0.008
        for y in range(h):
            for x in range(w):
                arr[y, x] = pnoise2(x * scale, y * scale, octaves=4)
        arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-6)
    else:
        # Simple fallback: gaussian-smoothed noise
        arr = np.random.rand(h, w).astype(np.float32)
        from scipy.ndimage import gaussian_filter
        arr = gaussian_filter(arr, sigma=3)
        arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-6)

    # Map to cream paper range (220–255)
    paper = (arr * 35 + 220).astype(np.uint8)
    return Image.fromarray(paper).convert("RGB")


def apply_vignette(img: Image.Image, strength: float = 0.06) -> Image.Image:
    """Darken corners slightly — scanner lamp falloff effect."""
    w, h = img.size
    vignette = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(vignette)

    # Radial gradient approximated by concentric ellipses
    cx, cy = w // 2, h // 2
    steps = 30
    for i in range(steps):
        t = i / steps
        darkness = int(255 * (1.0 - strength * t * t))
        rx = int(cx * (1 - t))
        ry = int(cy * (1 - t))
        draw.ellipse(
            [cx - rx, cy - ry, cx + rx, cy + ry],
            fill=darkness,
        )

    # Actually we want corners dark, center bright — invert logic
    vignette_arr = np.array(vignette, dtype=np.float32) / 255.0
    # Flip: bright at center → dark at corners
    corner_mask = 1.0 - vignette_arr
    darkening = 1.0 - corner_mask * strength * 3.0
    darkening = np.clip(darkening, 0, 1)

    img_arr = np.array(img.convert("RGB")).astype(np.float32)
    img_arr[:, :, 0] *= darkening
    img_arr[:, :, 1] *= darkening
    img_arr[:, :, 2] *= darkening
    img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)

    out = Image.fromarray(img_arr, "RGB")
    if img.mode == "RGBA":
        _, _, _, a = img.split()
        r, g, b = out.split()
        out = Image.merge("RGBA", [r, g, b, a])
    return out


def apply_micro_warp(img: Image.Image, amplitude: float = 1.2) -> Image.Image:
    """
    Subtle pixel-level warp using a displacement map.
    Eliminates pixel-perfect regularity — the last tell of digital rendering.
    """
    w, h = img.size
    arr = np.array(img)

    # Generate smooth displacement fields
    if _HAS_NOISE:
        scale = 0.03
        dx = np.array([[pnoise2(x * scale, y * scale, octaves=2)
                         for x in range(w)] for y in range(h)], dtype=np.float32)
        dy = np.array([[pnoise2(x * scale + 100, y * scale + 100, octaves=2)
                         for x in range(w)] for y in range(h)], dtype=np.float32)
    else:
        from scipy.ndimage import gaussian_filter
        dx = gaussian_filter(np.random.randn(h, w).astype(np.float32), sigma=8)
        dy = gaussian_filter(np.random.randn(h, w).astype(np.float32), sigma=8)

    dx = dx * amplitude
    dy = dy * amplitude

    # Build remapping coordinates
    grid_y, grid_x = np.mgrid[0:h, 0:w]
    map_x = np.clip(grid_x + dx, 0, w - 1).astype(np.float32)
    map_y = np.clip(grid_y + dy, 0, h - 1).astype(np.float32)

    # Remap using OpenCV for speed
    try:
        import cv2
        if arr.ndim == 3 and arr.shape[2] == 4:
            warped = cv2.remap(arr, map_x, map_y, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REFLECT)
        else:
            warped = cv2.remap(arr, map_x, map_y, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REFLECT)
        return Image.fromarray(warped, mode=img.mode)
    except ImportError:
        return img  # Skip warp if cv2 not available


def apply_all(
    page: Image.Image,
    fatigue_level: float = 0.3,
    texture_path: Optional[Path] = None,
) -> Image.Image:
    """
    Apply the full artifact stack to a completed page.
    fatigue_level (0–1) scales noise and warp intensity.
    """
    page = apply_ink_bleed(page, radius=0.5 + fatigue_level * 0.4)
    page = apply_micro_warp(page, amplitude=0.8 + fatigue_level * 0.6)
    page = apply_scan_noise(page, intensity=4.0 + fatigue_level * 3.0)
    page = apply_paper_texture(page, texture_path=texture_path, blend_alpha=0.15)
    page = apply_vignette(page, strength=0.05)
    return page
