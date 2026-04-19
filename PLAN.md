# Scripta — Living Build Plan

> This file is the source of truth for any Claude session working on this project.
> Read this FIRST before touching any code. Update it at the end of every session.

---

## What This Project Is

AI system that converts machine text (PDF, DOCX, plain text) into humanized handwriting images
that are indistinguishable from real human writing. Output is PNG/PDF on user-chosen page styles.

**The core differentiator**: A writer state model that simulates fatigue, attention, rush, and
hand inertia — producing state-dependent variation (not uniform random noise). This is what
makes it undetectable vs. every other tool that uses "font + jitter".

---

## Architecture (Finalized)

```
Input (PDF/DOCX/TXT)
        ↓
input_handler.py       — extracts clean text, preserves paragraph structure
        ↓
glyph_store.py         — loads IAM dataset, indexes word/char images by writer + text
        ↓
renderer.py            — pulls glyphs, applies per-instance transforms
        ↓
variation_engine.py    — WriterState model: fatigue, attention, rush, baseline drift
        ↓
artifact_sim.py        — ink blobs, tremor, pressure width variation, paper texture
        ↓
page_compositor.py     — page templates, line layout, margin handling, pagination
        ↓
Output (PNG / PDF)
```

---

## Dataset

- **IAM Handwriting Top50** (Kaggle: TejasReddy/iam-handwriting-top50)
  - 50 most common writers from IAM dataset
  - Word-level PNG images + XML annotations with character bounding boxes
  - ~16k downloads, well-structured

- Download path expected at: `data/iam/`

- Dataset structure expected:
  ```
  data/iam/
    words/          — word image PNGs organized by form
    xml/            — XML annotation files (character bounding boxes)
    words.txt       — master index: word_id, status, transcription
  ```

---

## Hardware

- Machine: HP Victus Gaming Laptop 15, Windows 11
- CPU: Intel i5-13420H
- RAM: 16GB
- GPU: NVIDIA RTX 4050 Laptop (6GB VRAM) — CUDA capable, can run neural inference locally
- Accounts: HuggingFace, Kaggle, Google Colab, GitHub

---

## Build Phases

### Phase 1 — Base Layer ✅ COMPLETE
Goal: Text in → handwriting PNG out, end-to-end

- [x] Project structure created
- [x] PLAN.md created
- [x] requirements.txt
- [x] config.py
- [x] glyph_store.py — IAM loader, word index, char index (with XML char extraction)
- [x] renderer.py — word-level + char-level fallback renderer
- [x] variation_engine.py — full WriterState: fatigue, attention, rush, Perlin baseline
- [x] artifact_sim.py — ink bleed, scan noise, paper texture, vignette, micro-warp
- [x] page_compositor.py — ruled/college/grid/blank/parchment, line wrap, pagination
- [x] input_handler.py — plain text, PDF (pdfplumber), DOCX (python-docx)
- [x] main.py — full CLI with --input --style --page --ink --output --seed

**Base layer success criteria**: `python main.py --input "Hello world" --output out.png`
produces a readable handwriting image on lined paper.

⚠️ REQUIRES: IAM dataset downloaded to data/iam/ before running

---

### Phase 2 — Variation Engine (NEXT)
Goal: Same input produces different output every run. Fatigue visible across page.

- [ ] Fatigue accumulator (chars written → tremor amplitude, size compression)
- [ ] Attention curve (paragraph start → neatness boost)
- [ ] Rush factor (word frequency lookup → size compression for common words)
- [ ] Perlin noise baseline drift (smooth, not random)
- [ ] Hand inertia (consecutive stroke direction carries over)
- [ ] Pen lift probabilistic model (ligature inconsistency)

---

### Phase 3 — Artifact Simulation
Goal: Output looks like a scanned handwritten page, not a render.

- [ ] Ink blob simulation at stroke start/end
- [ ] Tremor on long strokes (Perlin displacement)
- [ ] Stroke width pressure variation (non-uniform width along stroke)
- [ ] Paper grain texture overlay (multiply blend)
- [ ] Ink bleed (edge Gaussian blur, simulates absorption)
- [ ] Scan noise (slight luminance noise)

---

### Phase 4 — Input Pipeline + Page Styles
Goal: Real files in, polished output out.

- [ ] PDF extraction (pdfplumber)
- [ ] DOCX extraction (python-docx)
- [ ] Page styles: ruled, grid, blank, college, parchment, legal pad
- [ ] Multi-page pagination (long documents → multi-page PDF)
- [ ] Ink color options: blue, black, pencil gray

---

### Phase 5 — Neural Upgrade (Highest Quality)
Goal: Replace dataset-direct with VATr style-transfer model for unlimited text generation.

- [ ] VATr model setup (ankanbhunia/Handwriting-Transformers on GitHub)
- [ ] Pre-trained weights download
- [ ] Style image input (user uploads own handwriting → generates in that style)
- [ ] Inference pipeline on RTX 4050

---

### Phase 6 — Ship
- [ ] Gradio UI
- [ ] Deploy to HuggingFace Spaces

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Glyph source | IAM dataset (real humans) | Fonts cap at ~80% believability |
| Variation | State-dependent (not random) | Uniform random = AI fingerprint |
| Base layer | Dataset-direct (no neural) | Ships fast, neural added in Phase 5 |
| Compute | Local RTX 4050 | 6GB VRAM sufficient for inference |
| UI | Gradio | Free, deploys to HuggingFace in 30min |

---

## Architecture (with Neural Backend)

```
Input (PDF/DOCX/TXT)
        ↓
input_handler.py          — extracts clean text, preserves paragraph structure
        ↓
  ┌─────────────────────────────────────────────────────────┐
  │  FONT backend (--backend font, default)                 │
  │  glyph_store.py → renderer.py → variation_engine.py    │
  │  → artifact_sim.py → page_compositor.py                 │
  ├─────────────────────────────────────────────────────────┤
  │  NEURAL backend (--backend neural, best quality)        │
  │  neural_renderer.py (VATr++ on CUDA)                    │
  │  → neural_page_compositor.py → artifact_sim.py          │
  └─────────────────────────────────────────────────────────┘
        ↓
Output (PNG / PDF)
```

---

## Current Session Status

**Session 3** — COMPLETE. VATr++ neural backend fully integrated.

**What works right now:**
- `python main.py --input "any text" --output output/out.png` (font backend)
- `python main.py --backend neural --style a01 --input "any text" --output output/neural.png`
  - Runs VATr++ on RTX 4050 CUDA, generates real neural handwriting in any IAM writer style
  - 25 writer styles available: a01, a02, ... (IAM Top50 dataset)
- All 5 page styles: ruled, college, grid, blank, parchment
- Ink colors: blue, black, pencil — applied to neural output via alpha channel
- WriterState baseline drift + artifact simulation applied on top of VATr++ output

**VATr++ setup (done once, must be redone after fresh clone):**
```bash
# 1. Clone VATr-pp into Scripta root
git clone https://github.com/EDM-Research/VATr-pp.git VATr-pp

# 2. Install VATr-pp deps
cd VATr-pp && pip install -r requirements.txt && pip install msgpack wandb

# 3. Download model weights from HuggingFace
python -c "
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
import torch, collections
path = hf_hub_download('blowing-up-groundhogs/vatrpp', 'model.safetensors')
st = load_file(path)
od = collections.OrderedDict((k.replace('model.','',1), v) for k,v in st.items())
torch.save({'model': od}, 'files/vatrpp.pth')
print('Done')
"

# 4. Download resnet_18_pretrained.pth (check VATr-pp README for URL)

# 5. Segment IAM line images into word crops for style samples
cd ..
python VATr-pp/prep_style_samples.py
# (also copied to scripts/prep_style_samples.py)
```

**Font backend setup (done once):**
```bash
pip install -r requirements.txt
# Download fonts (Caveat):
python -c "
import urllib.request, os
os.makedirs('fonts', exist_ok=True)
urllib.request.urlretrieve('https://github.com/googlefonts/caveat/raw/main/fonts/ttf/Caveat-Regular.ttf', 'fonts/Caveat-Regular.ttf')
urllib.request.urlretrieve('https://github.com/googlefonts/caveat/raw/main/fonts/ttf/Caveat-Bold.ttf', 'fonts/Caveat-Bold.ttf')
"
```

**Believability assessment:**
- Font backend: ~65% believable (correct layout, good variation, but Caveat font recognizable)
- Neural backend: ~85%+ believable (real learned handwriting strokes from IAM writers)
- Gap to 90%+: larger text size (line_spacing too tight at 200 DPI), multi-line docs, more styles

**Next session should focus on:**
1. Increase line_spacing and glyph size so text fills the page more naturally at 200 DPI
   (current ruled=40px is too tight; real ruled paper is ~68px at 200 DPI)
2. Test neural backend with a multi-paragraph document (longer text, page overflow, indentation)
3. Gradio UI (Phase 6) — style picker, page style, ink color, download button
4. Deploy to HuggingFace Spaces

---

## Known Issues / Blockers

- VATr-pp is a nested git repo — not tracked in main Scripta repo. Must be cloned separately.
- resnet_18_pretrained.pth must be present in VATr-pp/files/ (check VATr-pp README for source).
- IAM style samples in VATr-pp/files/style_samples/ are excluded from git (large). Regenerate
  with `python scripts/prep_style_samples.py` after cloning VATr-pp.
- Font backend requires fonts/ directory with Caveat-Regular.ttf and Caveat-Bold.ttf.
