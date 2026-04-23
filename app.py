"""
Scripta — Gradio Web UI  (v5 Clean Light)
Run:  python app.py  →  http://localhost:7860
"""

import time
from pathlib import Path
from typing import List

import gradio as gr

import config
from scripta.input_handler import from_text, from_file
from scripta.page_compositor import PageCompositor, PAGE_STYLES


# ──────────────────────────────────────────────────────────────────────────────
# Lazy-loaded singletons
# ──────────────────────────────────────────────────────────────────────────────

_font_store      = None
_neural_renderer = None


def _load_font_store():
    global _font_store
    if _font_store is None:
        from scripta.glyph_store import GlyphStore
        _font_store = GlyphStore()
        _font_store.load(verbose=False)
    return _font_store


def _load_neural_renderer():
    global _neural_renderer
    if _neural_renderer is None:
        from scripta.neural_renderer import NeuralRenderer
        _neural_renderer = NeuralRenderer()
        _neural_renderer.load(verbose=True)
    return _neural_renderer


# ──────────────────────────────────────────────────────────────────────────────
# Style maps
# ──────────────────────────────────────────────────────────────────────────────

_FONT_STYLE_DESC = {
    "w01": "Casual · Loose",    "w02": "Neat · Compact",
    "w03": "Flowing · Cursive", "w04": "Bold · Chunky",
    "w05": "Sharp · Angular",   "w06": "Relaxed · Bouncy",
    "w07": "Tight · Careful",   "w08": "Free · Expressive",
    "w09": "Straight · Formal", "w10": "Slanted · Dynamic",
}
_NEURAL_STYLE_DESC = {
    "a01": "Neat · Precise",      "a02": "Casual · Flowing",
    "a03": "Cursive · Connected", "a05": "Tight · Compact",
    "a06": "Bold · Confident",    "a07": "Delicate · Fine",
    "a08": "Round · Soft",        "a09": "Sharp · Angular",
    "a10": "Free · Expressive",   "a11": "Neat · Organised",
    "a12": "Slanted · Dynamic",   "a13": "Formal · Careful",
    "a14": "Loose · Natural",     "a15": "Flowing · Elegant",
    "a16": "Bouncy · Playful",    "a17": "Straight · Direct",
    "a18": "Connected · Cursive", "a19": "Fine · Delicate",
    "a20": "Bold · Strong",       "a21": "Casual · Relaxed",
    "a22": "Tight · Precise",     "a23": "Round · Soft",
    "a24": "Angular · Sharp",     "a25": "Flowing · Smooth",
}
_ALL_STYLE_DESC = {**_FONT_STYLE_DESC, **_NEURAL_STYLE_DESC}


# ──────────────────────────────────────────────────────────────────────────────
# Writer discovery
# ──────────────────────────────────────────────────────────────────────────────

def _discover_font_writers() -> List[str]:
    try:
        return sorted(_load_font_store().writers)
    except Exception:
        return [f"w{i:02d}" for i in range(1, 11)]


def _discover_neural_writers() -> List[str]:
    try:
        from scripta.neural_renderer import STYLE_DIR
        if STYLE_DIR.exists():
            return sorted(d.name for d in STYLE_DIR.iterdir() if d.is_dir())
    except Exception:
        pass
    return []


FONT_WRITERS     = _discover_font_writers()
NEURAL_WRITERS   = _discover_neural_writers()
NEURAL_AVAILABLE = bool(NEURAL_WRITERS)


def _font_choices():
    return [(f"{_FONT_STYLE_DESC.get(w, w)}  [{w}]", w) for w in FONT_WRITERS]

def _neural_choices():
    return [(f"{_NEURAL_STYLE_DESC.get(w, w)}  [{w}]", w) for w in NEURAL_WRITERS]


# ──────────────────────────────────────────────────────────────────────────────
# Event handlers
# ──────────────────────────────────────────────────────────────────────────────

def on_backend_change(backend: str):
    if backend == "realistic":
        choices = _neural_choices()
        info    = "Authentic pen-stroke styles — each with its own rhythm"
    else:
        choices = _font_choices()
        info    = "From casual scrawl to precise cursive"
    value = choices[0][1] if choices else None
    return gr.update(choices=choices, value=value, info=info)


def generate(
    input_text, input_file, backend, writer_style,
    page_style, ink_color, apply_artifacts, seed_raw,
    progress=gr.Progress(),
):
    t0   = time.time()
    seed = int(seed_raw) if seed_raw not in (None, "", 0) else None

    progress(0.00, desc="Reading input…")
    if input_file is not None:
        try:
            paragraphs = from_file(Path(str(input_file)))
        except Exception as exc:
            return None, None, f"❌ **Couldn't read file:** {exc}"
    elif input_text and input_text.strip():
        paragraphs = from_text(input_text.strip())
    else:
        return None, None, "⚠️ Paste some text or upload a file to get started."

    if not any(paragraphs):
        return None, None, "⚠️ The input looks empty."

    total_words   = sum(len(p) for p in paragraphs)
    use_realistic = (backend == "realistic")

    progress(0.12, desc="Preparing…")
    try:
        if use_realistic:
            from scripta.neural_page_compositor import NeuralPageCompositor
            nr  = _load_neural_renderer()
            av  = nr.available_styles()
            sid = writer_style if writer_style in av else (av[0] if av else None)
            if not sid:
                return None, None, "❌ Realistic mode unavailable. Switch to Instant."
            nr.set_style(sid)
            compositor = NeuralPageCompositor(
                neural_renderer=nr, writer_id=sid,
                ink_color=ink_color, page_style=page_style,
                apply_artifacts=apply_artifacts, seed=seed,
            )
        else:
            store = _load_font_store()
            ids   = sorted(store.writers)
            sid   = writer_style if writer_style in ids else (ids[0] if ids else None)
            compositor = PageCompositor(
                glyph_store=store, writer_id=sid,
                ink_color=ink_color, page_style=page_style,
                apply_artifacts=apply_artifacts, seed=seed,
            )

        progress(0.3, desc="Writing…")
        pages   = compositor.render(paragraphs)
        elapsed = time.time() - t0

        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        if len(pages) == 1:
            out_path = out_dir / "scripta_output.png"
            pages[0].save(str(out_path))
        else:
            out_path = out_dir / "scripta_output.pdf"
            pages[0].save(str(out_path), "PDF", resolution=config.PAGE_DPI,
                          save_all=True, append_images=pages[1:])

        progress(1.0, desc="Done!")
        desc   = _ALL_STYLE_DESC.get(sid, sid)
        mode   = "Realistic" if use_realistic else "Instant"
        n      = len(pages)
        status = (
            f"✅ **{n} page{'s' if n > 1 else ''} generated** · "
            f"{elapsed:.1f}s · {desc} · {mode} · {ink_color.capitalize()} ink · {total_words} words"
        )
        return pages[0], str(out_path), status

    except Exception as exc:
        import traceback
        return None, None, f"❌ **Error:** {exc}\n```\n{traceback.format_exc()}\n```"


# ──────────────────────────────────────────────────────────────────────────────
# Theme  — Soft base, light and clean, minimal overrides needed
# ──────────────────────────────────────────────────────────────────────────────

_theme = gr.themes.Soft(
    primary_hue="violet",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
).set(
    body_background_fill="#f0f2f8",
    body_text_color="#1e293b",
    body_text_size="*text_sm",
    body_text_color_subdued="#64748b",

    block_background_fill="#ffffff",
    block_border_color="#e8ecf4",
    block_border_width="1px",
    block_shadow="0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.03)",
    block_radius="16px",
    block_label_text_color="#64748b",
    block_label_text_size="*text_xs",
    block_info_text_color="#94a3b8",

    input_background_fill="#f8faff",
    input_background_fill_focus="#ffffff",
    input_border_color="#dde3f0",
    input_border_color_focus="#7c3aed",
    input_border_width="1.5px",
    input_shadow="none",
    input_shadow_focus="0 0 0 3px rgba(124,58,237,0.10)",
    input_radius="10px",
    input_placeholder_color="#b0bbd4",

    button_primary_background_fill="linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)",
    button_primary_background_fill_hover="linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%)",
    button_primary_text_color="#ffffff",
    button_primary_border_color="transparent",
    button_large_radius="12px",
    button_large_text_weight="600",
    button_large_padding="14px 24px",

    color_accent="#7c3aed",
    color_accent_soft="rgba(124,58,237,0.08)",
    border_color_accent="#7c3aed",
    shadow_drop="0 1px 4px rgba(0,0,0,0.06), 0 6px 20px rgba(0,0,0,0.04)",
    shadow_spread="0px",
)


# ──────────────────────────────────────────────────────────────────────────────
# CSS  — minimal, purposeful, no !important wars
# ──────────────────────────────────────────────────────────────────────────────

CSS = """
/* ── Reset & page ─────────────────────────────────────────────────────────── */
footer { display: none !important; }
.gradio-container {
    max-width: 1280px !important;
    margin: 0 auto !important;
    padding: 0 !important;
    background: #f0f2f8 !important;
}

/* ── Hero header ───────────────────────────────────────────────────────────── */
#scripta-header {
    background: linear-gradient(135deg, #1e0a3c 0%, #2d1065 45%, #1e1b4b 100%);
    padding: 2.8rem 3rem 2.5rem;
    border-radius: 0 0 32px 32px;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}
#scripta-header::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(139,92,246,0.25) 0%, transparent 70%);
    pointer-events: none;
}
#scripta-header::after {
    content: '';
    position: absolute;
    bottom: -40px; left: 20%;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%);
    pointer-events: none;
}
.s-hero-eyebrow {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: rgba(167,139,250,0.9);
    margin-bottom: 0.5rem;
    display: block;
}
.s-hero-title {
    font-size: 2.8rem;
    font-weight: 800;
    letter-spacing: -1.5px;
    line-height: 1.05;
    background: linear-gradient(120deg, #f8fafc 0%, #c4b5fd 50%, #a5f3fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 0.5rem 0;
    display: block;
}
.s-hero-sub {
    font-size: 0.9rem;
    color: rgba(203,213,225,0.75);
    margin: 0;
    font-weight: 400;
    letter-spacing: 0.01em;
}
.s-hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(139,92,246,0.15);
    border: 1px solid rgba(139,92,246,0.3);
    color: #c4b5fd;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    padding: 0.3rem 0.8rem;
    border-radius: 20px;
    margin-top: 1.2rem;
    margin-right: 0.5rem;
    backdrop-filter: blur(4px);
}

/* ── Main layout ───────────────────────────────────────────────────────────── */
#main-row {
    padding: 0 1.5rem 2rem;
    gap: 1.5rem !important;
    align-items: flex-start !important;
}

/* ── Left panel ─────────────────────────────────────────────────────────────── */
#ctrl-panel {
    gap: 1rem !important;
}
#ctrl-panel > .block {
    border-radius: 16px !important;
    border: 1px solid #e8ecf4 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.02) !important;
}

/* ── Section headers inside panels ─────────────────────────────────────────── */
.s-section {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #94a3b8;
    margin: 0 0 0.75rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #f1f5f9;
    display: block;
}

/* ── Textarea ───────────────────────────────────────────────────────────────── */
#text-input textarea {
    min-height: 180px !important;
    line-height: 1.65 !important;
    font-size: 0.875rem !important;
    resize: vertical !important;
}

/* ── Quality pills (radio) ──────────────────────────────────────────────────── */
#quality-radio .wrap {
    gap: 0.6rem !important;
    flex-wrap: nowrap !important;
}
#quality-radio label {
    flex: 1 !important;
    justify-content: center !important;
    border-radius: 10px !important;
    border: 1.5px solid #dde3f0 !important;
    padding: 0.6rem 1rem !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
    cursor: pointer !important;
    background: #f8faff !important;
    color: #475569 !important;
}
#quality-radio label:hover {
    border-color: #7c3aed !important;
    background: rgba(124,58,237,0.04) !important;
    color: #7c3aed !important;
}
#quality-radio input[type="radio"]:checked + span,
#quality-radio .selected {
    background: linear-gradient(135deg,rgba(124,58,237,0.08),rgba(109,40,217,0.06)) !important;
    border-color: #7c3aed !important;
    color: #7c3aed !important;
    font-weight: 600 !important;
}

/* ── Generate button ────────────────────────────────────────────────────────── */
#gen-btn {
    margin-top: 0.25rem !important;
}
#gen-btn button {
    width: 100% !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.06em !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    padding: 0.9rem 1.5rem !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.35), 0 2px 6px rgba(0,0,0,0.1) !important;
    transition: all 0.2s ease !important;
    background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%) !important;
}
#gen-btn button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 28px rgba(124,58,237,0.45), 0 4px 10px rgba(0,0,0,0.12) !important;
}

/* ── Right panel — preview ──────────────────────────────────────────────────── */
#preview-panel {
    gap: 1rem !important;
}
#preview-panel > .block {
    border-radius: 16px !important;
    border: 1px solid #e8ecf4 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.02) !important;
}

/* Preview image ── */
#preview-image {
    background: #f8faff !important;
    border-radius: 12px !important;
    min-height: 480px !important;
}
#preview-image .upload-container,
#preview-image > div {
    min-height: 480px !important;
    border-radius: 12px !important;
}
#preview-image img {
    border-radius: 8px !important;
    box-shadow: 0 8px 32px rgba(30,9,60,0.12), 0 2px 8px rgba(0,0,0,0.06) !important;
    object-fit: contain !important;
}
/* Clean empty-state placeholder */
#preview-image svg {
    opacity: 0.25 !important;
}

/* Status ── */
#status-box {
    background: #f8faff !important;
    border: 1px solid #e8ecf4 !important;
    border-radius: 12px !important;
    padding: 0.75rem 1rem !important;
}
#status-box p, #status-box .prose {
    font-size: 0.78rem !important;
    color: #64748b !important;
    margin: 0 !important;
    line-height: 1.5 !important;
}

/* Download ── */
#download-file .file-preview {
    border-radius: 10px !important;
    border: 1px solid #e8ecf4 !important;
    background: #f8faff !important;
}

/* ── Tabs ───────────────────────────────────────────────────────────────────── */
.tabs > .tab-nav {
    border-bottom: 1px solid #e8ecf4 !important;
    gap: 0 !important;
    padding: 0 !important;
    background: transparent !important;
}
.tabs > .tab-nav button {
    border-radius: 0 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 0.5rem 1rem !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: #94a3b8 !important;
    background: transparent !important;
    transition: all 0.15s !important;
}
.tabs > .tab-nav button.selected {
    color: #7c3aed !important;
    border-bottom-color: #7c3aed !important;
    font-weight: 600 !important;
}

/* ── Accordion ──────────────────────────────────────────────────────────────── */
.accordion > .label-wrap {
    padding: 0.6rem 0 !important;
}
.accordion > .label-wrap span {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: #64748b !important;
}

/* ── Scrollbar ──────────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.25); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(124,58,237,0.5); }
"""


# ──────────────────────────────────────────────────────────────────────────────
# Choice lists
# ──────────────────────────────────────────────────────────────────────────────

_quality_choices = [("⚡  Instant  —  seconds", "font")]
if NEURAL_AVAILABLE:
    _quality_choices.append(("✨  Realistic  —  most authentic", "realistic"))

_page_choices = [
    ("Ruled",         "ruled"),
    ("College Ruled", "college"),
    ("Grid",          "grid"),
    ("Blank",         "blank"),
    ("Parchment",     "parchment"),
]
_ink_choices = [
    ("Blue Ink",    "blue"),
    ("Black Ink",   "black"),
    ("Pencil",      "pencil"),
]

_init_choices = _font_choices()
_init_value   = _init_choices[0][1] if _init_choices else None


# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="Scripta — Text to Handwriting") as demo:

    # ── Hero header ──────────────────────────────────────────────────────────
    gr.HTML("""
    <div id="scripta-header">
        <span class="s-hero-eyebrow">AI-Powered Handwriting Generator</span>
        <span class="s-hero-title">Scripta</span>
        <p class="s-hero-sub">Transform any text into beautiful, human-looking handwriting — instantly.</p>
        <span class="s-hero-badge">✍️ Powered by IAM Handwriting Dataset</span>
        <span class="s-hero-badge">🧠 Neural + Font Backends</span>
    </div>
    """)

    # ── Two-column layout ─────────────────────────────────────────────────────
    with gr.Row(elem_id="main-row", equal_height=False):

        # ── LEFT — Controls ───────────────────────────────────────────────────
        with gr.Column(scale=5, min_width=340, elem_id="ctrl-panel"):

            # Text input card
            with gr.Group():
                gr.HTML('<span class="s-section">Your Text</span>')
                with gr.Tabs():
                    with gr.Tab("✏️  Type or Paste"):
                        input_text = gr.Textbox(
                            lines=9,
                            placeholder=(
                                "Start typing or paste text here…\n\n"
                                "Blank lines create paragraph breaks.\n"
                                "Long text automatically flows across pages."
                            ),
                            show_label=False,
                            container=False,
                            elem_id="text-input",
                        )
                    with gr.Tab("📎  Upload File"):
                        input_file = gr.File(
                            label="Drop a file or click to browse",
                            file_types=[".txt", ".pdf", ".docx"],
                            file_count="single",
                        )

            # Quality card
            with gr.Group():
                gr.HTML('<span class="s-section">Quality Mode</span>')
                backend = gr.Radio(
                    choices=_quality_choices,
                    value=_quality_choices[0][1],
                    label="",
                    show_label=False,
                    container=False,
                    elem_id="quality-radio",
                )
                if not NEURAL_AVAILABLE:
                    gr.HTML(
                        '<p style="font-size:0.73rem;color:#94a3b8;margin:0.3rem 0 0;">'
                        '✨ Realistic mode requires the neural backend (GPU).</p>'
                    )

            # Style card
            with gr.Group():
                gr.HTML('<span class="s-section">Handwriting Style</span>')
                writer_style = gr.Dropdown(
                    choices=_init_choices,
                    value=_init_value,
                    label="",
                    show_label=False,
                    info="Each style mimics a distinct human writer",
                    container=False,
                )

            # Paper & Ink card
            with gr.Group():
                gr.HTML('<span class="s-section">Paper & Ink</span>')
                with gr.Row():
                    page_style = gr.Dropdown(
                        choices=_page_choices, value="ruled",
                        label="Paper", scale=3,
                    )
                    ink_color = gr.Dropdown(
                        choices=_ink_choices, value="blue",
                        label="Ink", scale=2,
                    )

            # Advanced options
            with gr.Accordion("Advanced options", open=False):
                apply_artifacts = gr.Checkbox(
                    label="Paper texture & aging effects",
                    value=True,
                    info="Adds realistic ink bleed, scan noise, and paper grain",
                )
                seed_val = gr.Number(
                    label="Seed  (blank = unique every time)",
                    value=None, precision=0,
                    minimum=0, maximum=2_147_483_647,
                )

            gen_btn = gr.Button(
                "✍️  Generate Handwriting",
                variant="primary",
                elem_id="gen-btn",
                size="lg",
            )

        # ── RIGHT — Preview ───────────────────────────────────────────────────
        with gr.Column(scale=7, min_width=440, elem_id="preview-panel"):

            with gr.Group():
                gr.HTML('<span class="s-section">Preview</span>')
                preview = gr.Image(
                    label="",
                    show_label=False,
                    elem_id="preview-image",
                    type="pil",
                    height=500,
                    interactive=False,
                    container=False,
                )

            with gr.Group(elem_id="status-box"):
                status_md = gr.Markdown(
                    value="*Configure your settings on the left and click **Generate Handwriting** to begin.*",
                )

            download_file = gr.File(
                label="Download Output",
                interactive=False,
                elem_id="download-file",
            )

    # ── Wiring ────────────────────────────────────────────────────────────────
    backend.change(fn=on_backend_change, inputs=[backend], outputs=[writer_style])
    gen_btn.click(
        fn=generate,
        inputs=[input_text, input_file, backend, writer_style,
                page_style, ink_color, apply_artifacts, seed_val],
        outputs=[preview, download_file, status_md],
    )


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    demo.launch(
        server_port=7860,
        share=False,
        show_error=True,
        theme=_theme,
        css=CSS,
    )
