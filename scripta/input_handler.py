"""
Input handler — extracts clean text from PDF, DOCX, or plain text.
Returns a list of paragraphs, each paragraph a list of words.
Paragraph structure matters: it feeds the attention curve in WriterState.
"""

import re
from pathlib import Path
from typing import List


def _tokenize(text: str) -> List[List[str]]:
    """
    Split raw text into paragraphs → words.
    Blank lines delimit paragraphs. Single newlines within a paragraph are joined.
    """
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split on double newlines (paragraph breaks)
    raw_paragraphs = re.split(r"\n{2,}", text)

    paragraphs: List[List[str]] = []
    for raw in raw_paragraphs:
        # Collapse single newlines within a paragraph
        cleaned = " ".join(raw.split())
        words = [w for w in cleaned.split() if w]
        if words:
            paragraphs.append(words)
        else:
            paragraphs.append([])  # preserve intentional blank lines

    return paragraphs


def from_text(text: str) -> List[List[str]]:
    return _tokenize(text)


def from_file(path: str | Path) -> List[List[str]]:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return _from_txt(path)
    elif suffix == ".pdf":
        return _from_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _from_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Use .txt, .pdf, or .docx")


def _from_txt(path: Path) -> List[List[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return _tokenize(text)


def _from_pdf(path: Path) -> List[List[str]]:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Install pdfplumber: pip install pdfplumber")

    paragraphs: List[List[str]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            paragraphs.extend(_tokenize(text))
            paragraphs.append([])  # page break = paragraph break

    # Remove trailing blank paragraph
    while paragraphs and not paragraphs[-1]:
        paragraphs.pop()

    return paragraphs


def _from_docx(path: Path) -> List[List[str]]:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("Install python-docx: pip install python-docx")

    doc = Document(str(path))
    paragraphs: List[List[str]] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        words = [w for w in text.split() if w]
        paragraphs.append(words if words else [])

    return paragraphs
