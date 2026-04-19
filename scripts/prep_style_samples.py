"""
Segment IAM line images into word-level crops for VATr++ style samples.
Each writer gets its own folder: files/style_samples/{writer_id}/
"""

import os
import sys
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image

IAM_DIR = Path("../data/iam/data_subset/data_subset")
OUT_DIR = Path("files/style_samples")
TARGET_H = 32
MIN_WORD_W = 10
MIN_WORDS_PER_WRITER = 15


def segment_words(line_img_gray: np.ndarray) -> list:
    """Split a line image into word crops using vertical projection profile."""
    # Invert: ink=1, background=0
    _, binary = cv2.threshold(line_img_gray, 200, 1, cv2.THRESH_BINARY_INV)

    # Vertical projection (sum along rows)
    proj = binary.sum(axis=0).astype(float)

    # Smooth to merge close strokes
    kernel = np.ones(5) / 5
    proj = np.convolve(proj, kernel, mode='same')

    # Find gaps (columns with no ink)
    gap_threshold = 0.5
    in_word = False
    word_starts = []
    word_ends = []

    for x, val in enumerate(proj):
        if not in_word and val > gap_threshold:
            in_word = True
            word_starts.append(x)
        elif in_word and val <= gap_threshold:
            in_word = False
            word_ends.append(x)

    if in_word:
        word_ends.append(len(proj))

    words = []
    for x1, x2 in zip(word_starts, word_ends):
        if x2 - x1 < MIN_WORD_W:
            continue
        crop = line_img_gray[:, max(0, x1-2):x2+2]
        if crop.shape[1] < MIN_WORD_W:
            continue
        words.append(crop)

    return words


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Group line images by writer ID
    writer_lines = defaultdict(list)
    for img_path in sorted(IAM_DIR.glob("*.png")):
        writer_id = img_path.stem.split("-")[0]
        writer_lines[writer_id].append(img_path)

    print(f"Found {len(writer_lines)} writers in IAM dataset")

    total_words = 0
    for writer_id, line_paths in writer_lines.items():
        out_folder = OUT_DIR / writer_id
        out_folder.mkdir(exist_ok=True)

        word_count = 0
        for line_path in line_paths:
            img = cv2.imread(str(line_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            words = segment_words(img)
            for word_img in words:
                # Resize to TARGET_H height preserving aspect ratio
                h, w = word_img.shape
                new_w = max(10, int(w * TARGET_H / h))
                word_resized = cv2.resize(word_img, (new_w, TARGET_H), interpolation=cv2.INTER_AREA)

                out_path = out_folder / f"word_{word_count:04d}.png"
                cv2.imwrite(str(out_path), word_resized)
                word_count += 1

        if word_count < MIN_WORDS_PER_WRITER:
            print(f"  WARNING: {writer_id} only has {word_count} words (need {MIN_WORDS_PER_WRITER})")
        else:
            print(f"  {writer_id}: {word_count} word samples saved")

        total_words += word_count

    print(f"\nDone. Total word samples: {total_words}")
    print(f"Style sample folders: {OUT_DIR}")


if __name__ == "__main__":
    main()
