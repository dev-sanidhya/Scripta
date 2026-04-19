"""
Loads the IAM Handwriting Top50 dataset and builds two indexes:
  - word_index[writer_id][word_text] = list of image paths
  - char_index[writer_id][char]      = list of cropped char PIL Images

The word index is used for direct word-level rendering (preferred).
The char index is the fallback when a word isn't in the dataset.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image
from tqdm import tqdm

import config


class GlyphStore:
    def __init__(self, data_dir: Path = config.DATA_DIR):
        self.data_dir = data_dir
        self.words_dir = data_dir / "words"
        self.xml_dir = data_dir / "xml"
        self.words_txt = data_dir / "words.txt"

        # writer_id -> word_text (lowercase) -> [Path, ...]
        self.word_index: Dict[str, Dict[str, List[Path]]] = defaultdict(lambda: defaultdict(list))

        # writer_id -> char -> [PIL.Image, ...]
        self.char_index: Dict[str, Dict[str, List[Image.Image]]] = defaultdict(lambda: defaultdict(list))

        # All known writer IDs
        self.writers: List[str] = []

        self._loaded = False

    def load(self, verbose: bool = True) -> None:
        if self._loaded:
            return

        if not self.words_txt.exists():
            raise FileNotFoundError(
                f"IAM words.txt not found at {self.words_txt}\n"
                f"Download: kaggle datasets download -d tejasreddy/iam-handwriting-top50 "
                f"-p data/iam --unzip"
            )

        self._build_word_index(verbose)
        self._build_char_index(verbose)
        self.writers = list(self.word_index.keys())
        self._loaded = True

        if verbose:
            total_words = sum(
                sum(len(v) for v in w.values()) for w in self.word_index.values()
            )
            total_chars = sum(
                sum(len(v) for v in c.values()) for c in self.char_index.values()
            )
            print(f"GlyphStore loaded: {len(self.writers)} writers, "
                  f"{total_words} word images, {total_chars} char crops")

    def _build_word_index(self, verbose: bool) -> None:
        """Parse words.txt and map each valid word to its image path + writer."""
        lines = self.words_txt.read_text(encoding="utf-8").splitlines()
        iter_ = tqdm(lines, desc="Indexing words", disable=not verbose)

        for line in iter_:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 9:
                continue

            word_id = parts[0]        # e.g. a01-000u-00-00
            status = parts[1]         # ok / err
            transcription = parts[-1] # the actual word text

            if status != "ok":
                continue

            # writer_id is the first segment of word_id
            writer_id = word_id.split("-")[0]

            # Build expected image path: words/a01/a01-000/a01-000u-00-00.png
            parts_id = word_id.split("-")
            folder1 = parts_id[0]                         # a01
            folder2 = "-".join(parts_id[:2])              # a01-000
            img_path = self.words_dir / folder1 / folder2 / f"{word_id}.png"

            if img_path.exists():
                self.word_index[writer_id][transcription.lower()].append(img_path)

    def _build_char_index(self, verbose: bool) -> None:
        """Parse XML files to extract character-level crops from word images."""
        if not self.xml_dir.exists():
            return

        xml_files = list(self.xml_dir.glob("*.xml"))
        iter_ = tqdm(xml_files, desc="Extracting chars", disable=not verbose)

        for xml_file in iter_:
            try:
                self._parse_xml_for_chars(xml_file)
            except Exception:
                continue

    def _parse_xml_for_chars(self, xml_file: Path) -> None:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        form_id = xml_file.stem  # e.g. a01-000
        writer_id = form_id.split("-")[0]

        for word_el in root.iter("word"):
            word_id = word_el.get("id", "")
            transcription = word_el.get("text", "").lower()
            if not word_id or not transcription:
                continue

            parts_id = word_id.split("-")
            if len(parts_id) < 3:
                continue

            folder1 = parts_id[0]
            folder2 = "-".join(parts_id[:2])
            word_img_path = self.words_dir / folder1 / folder2 / f"{word_id}.png"

            if not word_img_path.exists():
                continue

            try:
                word_img = Image.open(word_img_path).convert("L")
            except Exception:
                continue

            chars_in_word = list(transcription)
            cmp_els = [c for c in word_el if c.tag == "cmp"]

            if len(cmp_els) != len(chars_in_word):
                continue

            w_img, h_img = word_img.size

            for char, cmp_el in zip(chars_in_word, cmp_els):
                try:
                    x = int(cmp_el.get("x", 0))
                    y = int(cmp_el.get("y", 0))
                    w = int(cmp_el.get("width", 0))
                    h = int(cmp_el.get("height", 0))
                except (ValueError, TypeError):
                    continue

                if w < 3 or h < 3:
                    continue

                # Clamp to image bounds
                x1, y1 = max(0, x), max(0, y)
                x2, y2 = min(w_img, x + w), min(h_img, y + h)

                if x2 <= x1 or y2 <= y1:
                    continue

                crop = word_img.crop((x1, y1, x2, y2))
                if char.strip():
                    self.char_index[writer_id][char].append(crop)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_word_image(
        self,
        word: str,
        writer_id: Optional[str] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> Optional[Image.Image]:
        """Return a random word image for `word` from the given writer."""
        if rng is None:
            rng = np.random.default_rng()

        writers_to_try = [writer_id] if writer_id else self.writers
        word_lower = word.lower()

        for wid in writers_to_try:
            candidates = self.word_index.get(wid, {}).get(word_lower, [])
            if candidates:
                path = rng.choice(candidates)
                try:
                    return Image.open(path).convert("RGBA")
                except Exception:
                    continue
        return None

    def get_char_image(
        self,
        char: str,
        writer_id: Optional[str] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> Optional[Image.Image]:
        """Return a random char crop for `char` from the given writer."""
        if rng is None:
            rng = np.random.default_rng()

        writers_to_try = [writer_id] if writer_id else self.writers

        for wid in writers_to_try:
            candidates = self.char_index.get(wid, {}).get(char, [])
            if candidates:
                img = rng.choice(candidates)
                return img.copy().convert("RGBA")
        return None

    def available_writers(self) -> List[str]:
        return self.writers

    def writer_vocabulary(self, writer_id: str) -> List[str]:
        return list(self.word_index.get(writer_id, {}).keys())
