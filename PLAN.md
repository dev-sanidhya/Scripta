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

## Current Session Status

**Session 1** — COMPLETE. All Phase 1 files written.

**Next session should**:
1. Download IAM dataset: `kaggle datasets download -d tejasreddy/iam-handwriting-top50 -p data/iam --unzip`
2. Install deps: `pip install -r requirements.txt`
3. Run: `python main.py --input "The quick brown fox" --output output/test.png`
4. Inspect output, then move to Phase 2 (variation engine tuning based on real output)

---

## Known Issues / Blockers

- IAM dataset needs to be downloaded from Kaggle before glyph_store.py works.
  Command: `kaggle datasets download -d tejasreddy/iam-handwriting-top50 -p data/iam --unzip`
- Check exact folder structure after download, may need path adjustments in config.py.
