# Scripta — Living Build Plan

> **New Claude session? Read this entire file before touching any code.**
> This is the single source of truth. Update it at the end of every session.

---

## What We Are Building

Scripta converts machine text (PDF, DOCX, plain text) into handwriting images that are
indistinguishable from real human writing. Output is PNG or PDF.

**The goal is maximum believability — targeting 90%+.**

Two rendering backends exist:
- **Font backend** (`--backend font`): fast, uses Caveat font + WriterState variation. ~65% believable.
- **Neural backend** (`--backend neural`): uses VATr++ (a real neural handwriting model trained on
  IAM dataset). Generates authentic pen strokes. ~85%+ believable. **This is the focus.**

The core differentiator over every other tool is the **WriterState model**: fatigue accumulator,
attention curve, rush factor, and Perlin baseline drift produce state-dependent variation rather
than uniform random noise. Uniform random = detectable AI fingerprint.

---

## Hardware & Environment

- **Machine**: HP Victus Gaming Laptop 15, Windows 11
- **CPU**: Intel i5-13420H, **RAM**: 16GB
- **GPU**: NVIDIA RTX 4050 Laptop, 6GB VRAM — VATr++ runs on CUDA here
- **Python**: 3.10, **PyTorch**: 2.4.1+cu124 (CUDA 12.4)
- **Shell**: bash (Git Bash on Windows — use Unix paths)
- **Accounts**: GitHub (dev-sanidhya), HuggingFace, Kaggle

---

## Repository Structure

```
Scripta/
├── main.py                        — CLI entrypoint (--backend font|neural)
├── config.py                      — page dimensions, DPI, ink colors, margins
├── requirements.txt
├── scripts/
│   └── prep_style_samples.py      — segments IAM line images → word crops for VATr++
├── scripta/
│   ├── input_handler.py           — PDF/DOCX/TXT → List[List[str]] paragraphs
│   ├── glyph_store.py             — font-based glyph renderer (Caveat font, 10 writer personalities)
│   ├── renderer.py                — composites glyphs onto canvas, applies GlyphParams transforms
│   ├── variation_engine.py        — WriterState: fatigue, attention, rush, Perlin baseline drift
│   ├── artifact_sim.py            — ink bleed, scan noise, paper texture, vignette, micro-warp
│   ├── page_compositor.py         — font backend page layout, line wrap, pagination, PAGE_STYLES
│   ├── neural_renderer.py         — wraps VATr++ Writer, returns RGBA handwriting lines
│   └── neural_page_compositor.py  — neural backend page layout (line-level, not word-level)
├── fonts/                         — Caveat-Regular.ttf, Caveat-Bold.ttf (not in git)
├── data/iam/                      — IAM Handwriting Top50 dataset (not in git)
│   └── data_subset/data_subset/   — 4,899 line-level PNG images (e.g. a01-000u-00.png)
└── VATr-pp/                       — cloned neural model repo (nested git, not in Scripta git)
    ├── files/
    │   ├── vatrpp.pth             — converted model weights (not in git, ~929 keys)
    │   ├── resnet_18_pretrained.pth
    │   ├── unifont.pickle
    │   └── style_samples/         — word-level PNG crops per IAM writer (not in git)
    │       ├── a01/               — ~2000+ word crops at 32px height
    │       ├── a02/
    │       └── ...                — 25 writers total
    ├── generate/writer.py         — VATr++ Writer class (used by neural_renderer.py)
    └── util/misc.py               — FakeArgs class with all VATr++ model defaults
```

---

## Current Architecture

```
Input (PDF / DOCX / TXT)
        ↓
input_handler.py          — returns List[List[str]]: paragraphs → words

        ↓ (split by --backend flag in main.py)

┌─────────────────────────────────────────────────────────────────┐
│  FONT BACKEND  (--backend font, default, fast)                  │
│                                                                 │
│  glyph_store.py     — renders words via Caveat font (RGBA)      │
│  renderer.py        — applies GlyphParams: scale, rotate, slant │
│  variation_engine.py — WriterState per word                     │
│  artifact_sim.py    — post-process entire page                  │
│  page_compositor.py — line wrap, pagination, page templates     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  NEURAL BACKEND  (--backend neural, best quality)               │
│                                                                 │
│  neural_renderer.py      — VATr++ on CUDA, generates one line  │
│                            at a time as RGBA PIL Image          │
│  neural_page_compositor.py — line wrap, pagination,            │
│                              WriterState baseline drift,        │
│                              artifact_sim post-process          │
└─────────────────────────────────────────────────────────────────┘

        ↓
Output (PNG / multi-page PDF)
```

---

## What Is Fully Working (as of Session 3)

| Feature | Status | Notes |
|---|---|---|
| Text → handwriting PNG | ✅ | Both backends |
| PDF input | ✅ | pdfplumber |
| DOCX input | ✅ | python-docx |
| Plain text input | ✅ | |
| 5 page styles | ✅ | ruled, college, grid, blank, parchment |
| Ink colors | ✅ | blue, black, pencil |
| WriterState variation | ✅ | fatigue, attention, rush, Perlin drift |
| Artifact simulation | ✅ | ink bleed, scan noise, paper texture, vignette, micro-warp |
| Line wrap + pagination | ✅ | greedy wrap, multi-page PDF |
| VATr++ neural rendering | ✅ | On RTX 4050 CUDA, 25 IAM writer styles |
| Word wrap in neural mode | ✅ | Lines split correctly before VATr++ generation |
| Correct line spacing | ✅ | ruled=69px, college=56px (real paper dimensions at 200 DPI) |
| Gradio UI | ✅ | app.py — human writer names, no tech jargon, Gradio 6 |
| HuggingFace deployment | ❌ | After polish |

---

## CLI Usage

```bash
# Font backend (fast, no GPU needed)
python main.py --input "Hello world" --output output/out.png
python main.py --input doc.pdf --page college --ink black --output output/doc.pdf

# Neural backend (best quality, requires VATr++ setup)
python main.py --backend neural --style a01 --input "Hello world" --output output/neural.png
python main.py --backend neural --style a02 --input essay.docx --page ruled --ink blue --output output/essay.pdf

# List available styles
python main.py --backend neural --list-writers   # shows a01, a02, ... (25 IAM writers)
python main.py --list-writers                    # shows w01-w10 (font personalities)
python main.py --list-pages                      # shows all page styles
```

---

## Setup From Scratch (After Cloning)

### 1. Base dependencies
```bash
pip install -r requirements.txt
pip install torch==2.4.1+cu124 torchvision==0.19.1+cu124 --index-url https://download.pytorch.org/whl/cu124
```

### 2. Fonts (for font backend)
```bash
python -c "
import urllib.request, os
os.makedirs('fonts', exist_ok=True)
urllib.request.urlretrieve('https://github.com/googlefonts/caveat/raw/main/fonts/ttf/Caveat-Regular.ttf', 'fonts/Caveat-Regular.ttf')
urllib.request.urlretrieve('https://github.com/googlefonts/caveat/raw/main/fonts/ttf/Caveat-Bold.ttf', 'fonts/Caveat-Bold.ttf')
"
```

### 3. IAM dataset (for VATr++ style samples)
```bash
# Dataset: Kaggle iam-handwriting-top50 by TejasReddy
# Actual downloaded structure: data/iam/data_subset/data_subset/*.png (line-level images)
# File naming: a01-000u-00.png (writer_id-form-line.png)
python -c "
import urllib.request, zipfile, os
url = 'https://www.kaggle.com/api/v1/datasets/download/tejasreddy/iam-handwriting-top50'
req = urllib.request.Request(url)
req.add_header('Authorization', 'Bearer <KAGGLE_TOKEN>')
os.makedirs('data/iam', exist_ok=True)
urllib.request.urlretrieve(url, 'data/iam/dataset.zip')
zipfile.ZipFile('data/iam/dataset.zip').extractall('data/iam')
"
```

### 4. VATr++ neural backend
```bash
# Clone VATr-pp into Scripta root (it's a separate git repo, not a submodule)
git clone https://github.com/EDM-Research/VATr-pp.git VATr-pp

# Install VATr-pp dependencies
cd VATr-pp
pip install -r requirements.txt
pip install msgpack wandb

# Download and convert model weights from HuggingFace
# Model: blowing-up-groundhogs/vatrpp (safetensors format → converted to .pth)
python -c "
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
import torch, collections
path = hf_hub_download('blowing-up-groundhogs/vatrpp', 'model.safetensors')
st = load_file(path)
# Strip 'model.' prefix from all 929 keys — VATr++ code expects bare keys
od = collections.OrderedDict((k.replace('model.','',1), v) for k,v in st.items())
torch.save({'model': od}, 'files/vatrpp.pth')
print('Done — saved to VATr-pp/files/vatrpp.pth')
"

# resnet_18_pretrained.pth must also be in VATr-pp/files/ (46.6 MB)
# Download from the VATr-pp repo releases or HuggingFace if missing

# Segment IAM line images into word crops (runs from Scripta root)
cd ..
python scripts/prep_style_samples.py
# Output: VATr-pp/files/style_samples/{writer_id}/word_XXXX.png
# Produces ~53,825 word samples across 25 writers
```

---

## Critical Technical Decisions — DO NOT CHANGE

| Decision | What | Why |
|---|---|---|
| Noise library | `opensimplex` (not `noise`) | `noise` requires C++ build tools, fails on Windows |
| opensimplex API | `noise2(x, 0.0)` — no `octaves` arg | opensimplex doesn't support octaves like pnoise2 |
| Glyph background | `(0,0,0,0)` transparent | White background causes solid-color bleed after LANCZOS |
| Recoloring | Use actual alpha channel | Luminance-based alpha caused solid blue rectangles |
| VATr++ cwd | Must `os.chdir(VATRPP_DIR)` before calling | Loads `files/unifont.pickle` with relative paths |
| VATr++ weights key format | Strip `model.` prefix, wrap in `{'model': ...}` | HuggingFace safetensors has `model.*` keys; code expects bare keys |
| Line spacing (ruled) | 69px at 200 DPI | Real wide-ruled paper = 8.7mm. Smaller = text looks tiny |
| IAM data structure | Line-level images (not word-level) | Top50 dataset has full line PNGs, not word crops |
| Word crops for VATr++ | Generated by scripts/prep_style_samples.py | VATr++ FolderDataset needs word-level 32px PNGs |

---

## Key Files — What Each Does

**`scripta/variation_engine.py`** — WriterState class
- Personality traits per writer (size_base, slant_bias, tremor_sensitivity)
- `next_word_params(word)` → GlyphParams (scale, rotate_deg, slant, baseline_y, alpha, tremor)
- Scale range: (0.82, 1.18), noise std=0.015 (tightened to avoid words 2-3x larger than neighbors)
- Uses opensimplex: `from opensimplex import noise2; def pnoise1(x): return noise2(x, 0.0)`

**`scripta/neural_renderer.py`** — NeuralRenderer class
- Lazy-loads VATr++ Writer on first call, singleton pattern
- `set_style(writer_id)` — picks IAM writer (e.g. 'a01')
- `render_line(text, target_height, ink_rgb)` → RGBA PIL Image
  - VATr++ native output: uint8 (H=32, W=variable), ~0=ink ~255=paper
  - Converts to RGBA: `alpha = 255 - grayscale`, color = ink_rgb

**`scripta/page_compositor.py`** — PAGE_STYLES dict + PageCompositor class
- `target_height = int(line_spacing * 0.80)` — glyph height from line spacing
- Word wrap uses `renderer.word_width_estimate()` = `len(word) * target_height * 0.52 + word_spacing`

**`scripta/neural_page_compositor.py`** — NeuralPageCompositor class
- Generates whole lines (not word-by-word) via `neural_renderer.render_line()`
- Applies WriterState `baseline_y` drift per line
- Scales oversized lines to fit write area width
- Same artifact pipeline as font backend

**`scripta/artifact_sim.py`** — `apply_all(img, fatigue_level)`
- Micro-warp: `scipy.ndimage.gaussian_filter` on random noise + `cv2.remap` (fast, not pixel loop)
- Paper texture: opensimplex grain at multiple octaves manually summed

---

## Believability Assessment

| Backend | Score | Main Bottleneck |
|---|---|---|
| Font (Caveat) | ~65% | Caveat is a recognizable Google Font |
| Neural (VATr++) | ~85-87% | Real IAM strokes, but no per-word WriterState size variation |
| Target | 90%+ | |

**Remaining gap to 90%:**
- VATr++ generates lines uniformly — no within-line size/tremor variation per word
- No user-uploaded custom style (currently locked to 25 IAM writers)
- Ink color is post-hoc alpha recolor, not stroke-width pressure variation

---

## What To Build Next (Session 6)

**Priority 1: HuggingFace Spaces deployment**
- Free tier → font backend only (Instant mode), no GPU needed
- Paid GPU Space or Colab link for Realistic mode
- `requirements.txt` is already correct; add `app.py` as HF entrypoint

**Priority 2: UI Polish**
- Live preview thumbnail of each writer style (pre-rendered sample strip)
- Page count estimate before generating ("~2 pages")
- Mobile layout check

**Priority 3 (nice to have):**
- User uploads own handwriting image → generates in that style
- More page styles (legal pad, dot grid)
- Multi-page PDF preview in Gradio (show page thumbnails strip)

---

## Session 5 — What Was Done

- Rewrote `app.py` to v5 "Clean Light" design (scrapped split-panel dark/light)
- New design: deep violet gradient hero header + light white cards below
- Switched from `gr.themes.Soft` → `gr.themes.Base` (no auto dark-mode override)
- Added `color-scheme: light` + `@media (prefers-color-scheme: dark)` override CSS
- Added force-white CSS overrides for `.block`, `textarea`, `input` to defeat OS dark mode
- Fixed multi-server port conflict (old server was blocking port 7860 on restarts)
- Writer style labels use descriptors: `"Casual · Loose [w01]"` etc.
- All changes committed and pushed

## Session 4 — What Was Done

- Built `app.py`: full Gradio 6 UI wired to both backends
- Human names for all 35 writers (Maya, Ethan, Chloe… Sophie, Liam, Aria…)
- Zero tech jargon in UI — "Instant / Realistic" quality modes
- Backend/theme/css moved to `launch()` per Gradio 6 API
- Lazy-load singletons: font store + neural renderer only load when needed
- End-to-end tested: status reads "Chloe's handwriting · Instant · Blue ink"

---

## Known Issues / Blockers

- **VATr-pp is a nested git repo** — not tracked in Scripta. Clone separately: `git clone https://github.com/EDM-Research/VATr-pp.git VATr-pp`
- **Style samples not in git** — VATr-pp/files/style_samples/ is 53k files. Regenerate with `python scripts/prep_style_samples.py` after cloning VATr-pp and downloading IAM dataset.
- **resnet_18_pretrained.pth** must be manually placed in VATr-pp/files/ (check VATr-pp repo README for download link).
- **Font backend** requires fonts/ dir with Caveat-Regular.ttf and Caveat-Bold.ttf (see setup steps above).
- **Unicode em-dash (—)** is stripped by VATr++ alphabet filter — shows as `?` in neural output. VATr++ alphabet only covers ASCII printable chars.
