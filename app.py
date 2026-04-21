"""
Scripta — Gradio Web UI
Run:  python app.py
Then open http://localhost:7860
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
# Writer name maps  —  friendly names shown in UI, IDs passed to backend
# ──────────────────────────────────────────────────────────────────────────────

_FONT_WRITER_NAMES = {
    "w01": "Maya",
    "w02": "Ethan",
    "w03": "Chloe",
    "w04": "Marcus",
    "w05": "Priya",
    "w06": "Jake",
    "w07": "Zoe",
    "w08": "Kai",
    "w09": "Nora",
    "w10": "Leo",
}

_NEURAL_WRITER_NAMES = {
    "a01": "Sophie",
    "a02": "Liam",
    "a03": "Aria",
    "a04": "Owen",
    "a05": "Isla",
    "a06": "Noah",
    "a07": "Zara",
    "a08": "Felix",
    "a09": "Luna",
    "a10": "Rohan",
    "a11": "Mia",
    "a12": "Callum",
    "a13": "Jade",
    "a14": "Ravi",
    "a15": "Clara",
    "a16": "Dylan",
    "a17": "Niamh",
    "a18": "Sebastian",
    "a19": "Freya",
    "a20": "Mateo",
    "a21": "Vera",
    "a22": "Elliot",
    "a23": "Amara",
    "a24": "Hugo",
    "a25": "Sienna",
}

# Combined ID → display name (for status messages)
_ALL_WRITER_NAMES = {**_FONT_WRITER_NAMES, **_NEURAL_WRITER_NAMES}


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


def _font_writer_choices():
    """(display name, backend id) tuples for font writers."""
    return [(_FONT_WRITER_NAMES.get(w, w), w) for w in FONT_WRITERS]


def _neural_writer_choices():
    """(display name, backend id) tuples for neural writers."""
    return [(_NEURAL_WRITER_NAMES.get(w, w), w) for w in NEURAL_WRITERS]


# ──────────────────────────────────────────────────────────────────────────────
# Event handlers
# ──────────────────────────────────────────────────────────────────────────────

def on_backend_change(backend: str):
    """Swap writer list when the quality mode changes."""
    if backend == "realistic":
        choices = _neural_writer_choices()
        info    = "Each writer has their own authentic handwriting style"
    else:
        choices = _font_writer_choices()
        info    = "Each writer has their own natural handwriting style"

    value = choices[0][1] if choices else None
    return gr.update(choices=choices, value=value, info=info)


def generate(
    input_text: str,
    input_file,
    backend: str,
    writer_style: str,
    page_style: str,
    ink_color: str,
    apply_artifacts: bool,
    seed_raw,
    progress=gr.Progress(),
) -> tuple:
    """
    Main generation — called on button click.
    Returns (preview_pil, download_path, status_markdown).
    """
    t0   = time.time()
    seed = int(seed_raw) if seed_raw not in (None, "", 0) else None

    # ── 1. Parse input ────────────────────────────────────────────────────────
    progress(0.00, desc="Reading your text…")

    if input_file is not None:
        try:
            paragraphs = from_file(Path(str(input_file)))
        except Exception as exc:
            return None, None, f"❌ **Couldn't read that file:** {exc}"
    elif input_text and input_text.strip():
        paragraphs = from_text(input_text.strip())
    else:
        return None, None, "⚠️ **Nothing to write** — add some text or upload a file first."

    if not any(paragraphs):
        return None, None, "⚠️ **The input looks empty.** Nothing to generate."

    total_words = sum(len(p) for p in paragraphs)
    use_realistic = (backend == "realistic")

    # ── 2. Build compositor ───────────────────────────────────────────────────
    progress(0.10, desc="Getting the pen ready…")

    try:
        if use_realistic:
            from scripta.neural_page_compositor import NeuralPageCompositor

            nr        = _load_neural_renderer()
            available = nr.available_styles()
            style_id  = writer_style if writer_style in available else (available[0] if available else None)
            if not style_id:
                return None, None, (
                    "❌ **Realistic mode unavailable** — handwriting samples not found.\n\n"
                    "Switch to Instant mode to continue."
                )
            nr.set_style(style_id)
            compositor = NeuralPageCompositor(
                neural_renderer=nr,
                writer_id=style_id,
                ink_color=ink_color,
                page_style=page_style,
                apply_artifacts=apply_artifacts,
                seed=seed,
            )

        else:
            store    = _load_font_store()
            all_ids  = sorted(store.writers)
            style_id = writer_style if writer_style in all_ids else (all_ids[0] if all_ids else None)
            compositor = PageCompositor(
                glyph_store=store,
                writer_id=style_id,
                ink_color=ink_color,
                page_style=page_style,
                apply_artifacts=apply_artifacts,
                seed=seed,
            )

        # ── 3. Render ─────────────────────────────────────────────────────────
        progress(0.25, desc="Writing it out…")
        pages   = compositor.render(paragraphs)
        elapsed = time.time() - t0

        # ── 4. Save output ────────────────────────────────────────────────────
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)

        if len(pages) == 1:
            out_path = out_dir / "scripta_output.png"
            pages[0].save(str(out_path))
        else:
            out_path = out_dir / "scripta_output.pdf"
            pages[0].save(
                str(out_path), "PDF", resolution=config.PAGE_DPI,
                save_all=True, append_images=pages[1:],
            )

        progress(1.00, desc="Done!")

        writer_name  = _ALL_WRITER_NAMES.get(style_id, style_id)
        quality_name = "Realistic" if use_realistic else "Instant"
        n            = len(pages)
        status = (
            f"✅ **{n} page{'s' if n > 1 else ''} generated** in {elapsed:.1f}s\n\n"
            f"{writer_name}'s handwriting · {quality_name} · "
            f"{ink_color.capitalize()} ink · {total_words} words"
        )

        return pages[0], str(out_path), status

    except Exception as exc:
        import traceback
        return None, None, f"❌ **Something went wrong:**\n```\n{exc}\n{traceback.format_exc()}\n```"


# ──────────────────────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────────────────────

CSS = """
/* ── Header ─────────────────────────────────────────────────────────────────── */
.scripta-header {
    background: linear-gradient(135deg, #0d1b2a 0%, #162032 55%, #1a3560 100%);
    border-radius: 14px;
    padding: 2.2rem 2.6rem 1.9rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 6px 30px rgba(0,0,0,0.25);
}
.scripta-header h1 {
    color: #eef2f7;
    font-size: 2.4rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0 0 0.35rem;
    font-family: 'Georgia', 'Times New Roman', serif;
    text-shadow: 0 2px 10px rgba(0,0,0,0.35);
}
.scripta-header .tagline {
    color: #8fa8c8;
    font-size: 0.97rem;
    margin: 0 0 0.9rem;
    line-height: 1.5;
}
.scripta-pill {
    display: inline-block;
    background: rgba(255,255,255,0.07);
    color: #7ecef4;
    font-size: 0.72rem;
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    border: 1px solid rgba(126, 206, 244, 0.22);
    letter-spacing: 0.04em;
    margin-right: 0.45rem;
}

/* ── Section labels ──────────────────────────────────────────────────────────── */
.sec-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #64748b;
    margin: 1.1rem 0 0.45rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #e2e8f0;
}

/* ── Unavailable quality warning ─────────────────────────────────────────────── */
.quality-warn {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    font-size: 0.82rem;
    color: #92400e;
    margin-top: 4px;
    line-height: 1.5;
}

/* ── Generate button ──────────────────────────────────────────────────────────── */
#gen-btn button {
    background: linear-gradient(135deg, #1d4ed8 0%, #1e3a8a 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 1.0rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.025em !important;
    padding: 0.8rem 1.5rem !important;
    box-shadow: 0 4px 16px rgba(29, 78, 216, 0.38) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
#gen-btn button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(29, 78, 216, 0.46) !important;
}
#gen-btn button:active {
    transform: translateY(0) !important;
}

/* ── Preview ─────────────────────────────────────────────────────────────────── */
#preview-panel .image-container {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 8px 40px rgba(0,0,0,0.13);
    border: 1px solid #dee2e6;
}
#preview-panel img {
    border-radius: 10px;
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Static choice lists
# ──────────────────────────────────────────────────────────────────────────────

# Backend: label shown in UI → value passed to generate()
_quality_choices = [("⚡  Instant", "font")]
if NEURAL_AVAILABLE:
    _quality_choices.append(("✨  Realistic", "realistic"))

_page_choices = [
    ("📏  Ruled",         "ruled"),
    ("📒  College Ruled", "college"),
    ("⬛  Grid",          "grid"),
    ("⬜  Blank",         "blank"),
    ("📜  Parchment",     "parchment"),
]

_ink_choices = [
    ("🔵  Blue",   "blue"),
    ("⚫  Black",  "black"),
    ("✏️  Pencil", "pencil"),
]

_initial_writer_choices = _font_writer_choices()
_initial_writer_value   = _initial_writer_choices[0][1] if _initial_writer_choices else None


# ──────────────────────────────────────────────────────────────────────────────
# Theme
# ──────────────────────────────────────────────────────────────────────────────

_theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "sans-serif"],
)


# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="Scripta — Handwriting Generator") as demo:

    # ── Header ────────────────────────────────────────────────────────────────
    gr.HTML("""
    <div class="scripta-header">
        <h1>✍️ Scripta</h1>
        <p class="tagline">
            Turn any text into natural handwritten notes —
            perfect for assignments, letters, and journaling
        </p>
        <span class="scripta-pill">35 handwriting styles</span>
        <span class="scripta-pill">5 paper types</span>
        <span class="scripta-pill">PNG &amp; PDF export</span>
    </div>
    """)

    with gr.Row(equal_height=False):

        # ── LEFT: controls ────────────────────────────────────────────────────
        with gr.Column(scale=4, min_width=320):

            # Input
            gr.HTML('<p class="sec-label">Your Text</p>')
            with gr.Tabs():
                with gr.Tab("✏️  Type or Paste"):
                    input_text = gr.Textbox(
                        lines=9,
                        placeholder=(
                            "Start typing or paste anything here…\n\n"
                            "Blank lines become paragraph breaks.\n"
                            "Long texts automatically flow across pages."
                        ),
                        show_label=False,
                        container=False,
                    )
                with gr.Tab("📎  Upload a File"):
                    input_file = gr.File(
                        label="Supports .txt, .pdf, and .docx",
                        file_types=[".txt", ".pdf", ".docx"],
                        file_count="single",
                    )

            # Quality
            gr.HTML('<p class="sec-label">Quality</p>')
            backend = gr.Radio(
                choices=_quality_choices,
                value=_quality_choices[0][1],
                label="",
                container=False,
                info="Instant: done in seconds. Realistic: ~15s per page, looks most authentic.",
            )
            if not NEURAL_AVAILABLE:
                gr.HTML("""
                <div class="quality-warn">
                    ✨ Realistic mode isn't available on this setup —
                    only Instant mode is enabled.
                </div>""")

            # Writer
            gr.HTML('<p class="sec-label">Handwriting Style</p>')
            writer_style = gr.Dropdown(
                choices=_initial_writer_choices,
                value=_initial_writer_value,
                label="Writer",
                info="Each writer has their own natural handwriting style",
            )

            # Page + ink on the same row
            gr.HTML('<p class="sec-label">Paper & Ink</p>')
            with gr.Row():
                page_style = gr.Dropdown(
                    choices=_page_choices,
                    value="ruled",
                    label="Paper",
                    scale=3,
                )
                ink_color = gr.Dropdown(
                    choices=_ink_choices,
                    value="blue",
                    label="Ink",
                    scale=2,
                )

            # Advanced
            with gr.Accordion("⚙️  More Options", open=False):
                apply_artifacts = gr.Checkbox(
                    label="Add paper texture & aging effects",
                    value=True,
                )
                seed_val = gr.Number(
                    label="Seed  (leave blank for a unique result every time)",
                    value=None,
                    precision=0,
                    minimum=0,
                    maximum=2_147_483_647,
                )

            gen_btn = gr.Button(
                "✍️   Generate Handwriting",
                variant="primary",
                elem_id="gen-btn",
                size="lg",
            )

        # ── RIGHT: output ─────────────────────────────────────────────────────
        with gr.Column(scale=6, min_width=400):

            gr.HTML('<p class="sec-label">Preview</p>')
            preview = gr.Image(
                label="",
                show_label=False,
                elem_id="preview-panel",
                container=True,
                type="pil",
                height=700,
                interactive=False,
            )
            download_file = gr.File(
                label="Download",
                interactive=False,
            )
            status_md = gr.Markdown(
                value="*Pick a style on the left and hit **Generate Handwriting** to get started →*"
            )

    # ── Event wiring ──────────────────────────────────────────────────────────
    backend.change(
        fn=on_backend_change,
        inputs=[backend],
        outputs=[writer_style],
    )

    gen_btn.click(
        fn=generate,
        inputs=[
            input_text, input_file,
            backend, writer_style, page_style, ink_color,
            apply_artifacts, seed_val,
        ],
        outputs=[preview, download_file, status_md],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo.launch(
        server_port=7860,
        share=False,
        show_error=True,
        theme=_theme,
        css=CSS,
    )
