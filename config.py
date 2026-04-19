from pathlib import Path

ROOT = Path(__file__).parent

DATA_DIR = ROOT / "data" / "iam"
WORDS_DIR = DATA_DIR / "words"
XML_DIR = DATA_DIR / "xml"
WORDS_INDEX = DATA_DIR / "words.txt"

PAGES_DIR = ROOT / "pages"
FONTS_DIR = ROOT / "fonts"
OUTPUT_DIR = ROOT / "output"

# Page dimensions (A4 at 200 DPI — good quality; bump to 300 for print quality)
PAGE_DPI = 200
PAGE_W = int(8.27 * PAGE_DPI)   # 1240 px
PAGE_H = int(11.69 * PAGE_DPI)  # 1754 px

# Margins (px)
MARGIN_TOP = int(0.75 * PAGE_DPI)
MARGIN_BOTTOM = int(0.75 * PAGE_DPI)
MARGIN_LEFT = int(0.9 * PAGE_DPI)
MARGIN_RIGHT = int(0.7 * PAGE_DPI)

# Line spacing for ruled page
LINE_SPACING_PT = 32            # px at 200 DPI
LINE_COLOR = (176, 196, 222)    # steel blue, like real ruled paper
MARGIN_LINE_COLOR = (220, 120, 120)  # pink margin line

# Ink colors
INK_COLORS = {
    "blue": (30, 60, 180),
    "black": (20, 20, 30),
    "pencil": (90, 90, 95),
}
DEFAULT_INK = "blue"

# Glyph rendering
GLYPH_TARGET_HEIGHT = 46        # px — standard glyph height at 200 DPI
WORD_SPACING = 18               # px between words
CHAR_SPACING = 3                # px between chars within composed word

# Writer state defaults (variation engine)
FATIGUE_RATE = 0.0008           # fatigue increase per character written
FATIGUE_MAX = 0.45              # cap on fatigue level (0–1)
ATTENTION_DECAY = 0.12          # attention drops this fraction per line
ATTENTION_PARAGRAPH_BOOST = 0.6 # attention reset on paragraph break
