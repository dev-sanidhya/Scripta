"""
Scripta CLI

Usage examples:
  python main.py --input "Hello, this is Scripta." --output output/test.png
  python main.py --input doc.pdf --style a01 --page ruled --ink blue --output output/doc.pdf
  python main.py --input essay.docx --page parchment --ink black --output output/essay.pdf
  python main.py --list-writers
  python main.py --list-pages
"""

import argparse
import sys
from pathlib import Path

import config
from scripta.glyph_store import GlyphStore
from scripta.input_handler import from_text, from_file
from scripta.page_compositor import PageCompositor, PAGE_STYLES


def save_output(pages, out_path: Path) -> None:
    suffix = out_path.suffix.lower()

    if suffix == ".pdf":
        try:
            import img2pdf
            pdf_bytes = img2pdf.convert([p.tobytes() for p in pages])
            # img2pdf needs raw bytes with size info — use PIL save approach instead
        except Exception:
            pass

        # Reliable PDF output via Pillow
        if len(pages) == 1:
            pages[0].save(str(out_path), "PDF", resolution=config.PAGE_DPI)
        else:
            pages[0].save(
                str(out_path), "PDF", resolution=config.PAGE_DPI,
                save_all=True, append_images=pages[1:],
            )
    else:
        # PNG output — save each page
        if len(pages) == 1:
            pages[0].save(str(out_path))
        else:
            for i, page in enumerate(pages):
                p = out_path.with_stem(f"{out_path.stem}_p{i+1}")
                page.save(str(p))
            print(f"Saved {len(pages)} pages.")


def main():
    parser = argparse.ArgumentParser(
        prog="scripta",
        description="Convert text to humanized handwriting.",
    )
    parser.add_argument("--input", "-i", type=str,
                        help="Input text string, or path to .txt / .pdf / .docx")
    parser.add_argument("--output", "-o", type=str, default="output/out.png",
                        help="Output path (.png or .pdf). Default: output/out.png")
    parser.add_argument("--style", "-s", type=str, default=None,
                        help="Writer ID from IAM dataset (e.g. a01). Default: random.")
    parser.add_argument("--page", "-p", type=str, default="ruled",
                        choices=list(PAGE_STYLES.keys()),
                        help="Page style. Default: ruled")
    parser.add_argument("--ink", type=str, default=config.DEFAULT_INK,
                        choices=list(config.INK_COLORS.keys()),
                        help="Ink color. Default: blue")
    parser.add_argument("--no-artifacts", action="store_true",
                        help="Skip artifact simulation (faster, cleaner)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible output")
    parser.add_argument("--list-writers", action="store_true",
                        help="List all available writer IDs and exit")
    parser.add_argument("--list-pages", action="store_true",
                        help="List all page styles and exit")

    args = parser.parse_args()

    if args.list_pages:
        print("Available page styles:")
        for name in PAGE_STYLES:
            print(f"  {name}")
        return

    # Load dataset
    print("Loading handwriting dataset...")
    store = GlyphStore()
    store.load(verbose=True)

    if args.list_writers:
        print(f"\nAvailable writers ({len(store.writers)}):")
        for w in sorted(store.writers):
            vocab_size = len(store.writer_vocabulary(w))
            print(f"  {w}  ({vocab_size} words in vocabulary)")
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    # Parse input
    input_path = Path(args.input)
    if input_path.exists():
        print(f"Reading file: {input_path}")
        paragraphs = from_file(input_path)
    else:
        paragraphs = from_text(args.input)

    total_words = sum(len(p) for p in paragraphs)
    print(f"Input: {len(paragraphs)} paragraph(s), {total_words} word(s)")

    # Render
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    compositor = PageCompositor(
        glyph_store=store,
        writer_id=args.style,
        ink_color=args.ink,
        page_style=args.page,
        apply_artifacts=not args.no_artifacts,
        seed=args.seed,
    )

    print(f"Rendering with writer '{compositor.writer_state.writer_id}' "
          f"on '{args.page}' page in {args.ink} ink...")

    pages = compositor.render(paragraphs)
    print(f"Rendered {len(pages)} page(s)")

    save_output(pages, out_path)
    print(f"Saved: {out_path.resolve()}")


if __name__ == "__main__":
    main()
