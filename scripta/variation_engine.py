"""
WriterState — the core differentiator.

Models the internal state of a human writer over time and produces
state-dependent perturbation parameters. Every call to `next_glyph()`
advances the state and returns a GlyphParams bundle used by the renderer.

Key insight: variation is NOT uniform random noise. It's structured:
  - Fatigue accumulates → tremor grows, size shrinks, slant drifts
  - Attention resets at paragraph/sentence starts → neatness spikes
  - Common words are written faster → more compressed, looser strokes
  - Hand inertia: consecutive stroke direction carries over
  - Baseline drifts smoothly across the line (Perlin, not random)
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    from opensimplex import noise2
    def pnoise1(x): return noise2(x, 0.0)
    _HAS_NOISE = True
except ImportError:
    _HAS_NOISE = False

import config

# Most frequent English words — written faster, therefore sloppier
_COMMON_WORDS = frozenset({
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "it",
    "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
    "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
    "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "is", "was", "are", "were", "been", "has", "had", "did", "does",
})


@dataclass
class GlyphParams:
    """Perturbation parameters for a single glyph instance."""
    scale: float = 1.0          # size multiplier (fatigue shrinks this)
    rotate_deg: float = 0.0     # rotation in degrees
    offset_x: float = 0.0      # horizontal nudge (px)
    offset_y: float = 0.0      # vertical nudge (px, positive = down)
    baseline_y: float = 0.0    # baseline drift for this position (px)
    alpha: float = 1.0          # ink opacity (fatigue fades slightly)
    tremor: float = 0.0         # amplitude for stroke tremor (0–1)
    slant: float = 0.0          # italic-like lean (degrees, + = right)
    spacing_factor: float = 1.0 # word spacing multiplier (rush = tighter)


class WriterState:
    def __init__(
        self,
        writer_id: str = "default",
        ink_color: str = config.DEFAULT_INK,
        seed: Optional[int] = None,
    ):
        self.writer_id = writer_id
        self.ink_color = ink_color
        self._rng = np.random.default_rng(seed)
        self._py_rng = random.Random(seed)

        # Fatigue (0 = fresh, 1 = max tired)
        self._fatigue: float = 0.0

        # Attention (1 = fully focused, 0 = autopilot)
        self._attention: float = 1.0

        # Total characters written this session
        self._chars_written: int = 0

        # Current line index (for baseline drift phase)
        self._line_idx: int = 0

        # Perlin noise offset — advances with each character for continuity
        self._noise_offset: float = self._rng.uniform(0, 1000)

        # Slant drift — slow random walk
        self._slant_base: float = self._py_rng.uniform(-3.0, 3.0)

        # Per-writer "personality" — sampled once at init
        self._personality = self._sample_personality()

    def _sample_personality(self) -> dict:
        """Each writer has fixed traits that don't change mid-document."""
        return {
            "size_base": self._py_rng.uniform(0.88, 1.12),
            "slant_bias": self._py_rng.uniform(-5.0, 5.0),    # natural lean
            "tremor_sensitivity": self._py_rng.uniform(0.4, 1.0),
            "rush_sensitivity": self._py_rng.uniform(0.5, 1.0),
            "fatigue_sensitivity": self._py_rng.uniform(0.6, 1.2),
            "baseline_amplitude": self._py_rng.uniform(1.5, 4.5),
        }

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def on_paragraph_start(self) -> None:
        """Called before rendering the first word of a new paragraph."""
        self._attention = min(1.0, self._attention + config.ATTENTION_PARAGRAPH_BOOST)
        self._fatigue = max(0.0, self._fatigue - 0.08)

    def on_line_start(self, line_idx: int) -> None:
        """Called at the start of each new line."""
        self._line_idx = line_idx
        self._attention = max(0.0, self._attention - config.ATTENTION_DECAY)

    def on_word(self, word: str) -> None:
        """Called once per word before rendering its glyphs."""
        n = len(word)
        self._chars_written += n
        fatigue_delta = n * config.FATIGUE_RATE * self._personality["fatigue_sensitivity"]
        self._fatigue = min(config.FATIGUE_MAX, self._fatigue + fatigue_delta)
        self._noise_offset += n * 0.07

        # Slow slant random walk
        self._slant_base += self._py_rng.gauss(0, 0.15)
        self._slant_base = max(-8.0, min(8.0, self._slant_base))

    # ------------------------------------------------------------------
    # Parameter generation
    # ------------------------------------------------------------------

    def next_glyph(self, char: str = "") -> GlyphParams:
        """Return perturbation params for the next glyph, advancing noise."""
        f = self._fatigue
        a = self._attention
        pers = self._personality

        # Baseline drift — smooth sinusoidal Perlin across the line
        if _HAS_NOISE:
            baseline_y = (
                pnoise1(self._noise_offset * 0.08) *
                pers["baseline_amplitude"] *
                (1.0 + f * 0.5)
            )
        else:
            baseline_y = math.sin(self._noise_offset * 0.3) * pers["baseline_amplitude"]

        self._noise_offset += 0.11

        # Scale: fatigue shrinks, attention boosts
        scale_noise = self._rng.normal(0, 0.025)
        scale = (
            pers["size_base"] *
            (1.0 - f * 0.12) *
            (1.0 + (a - 0.5) * 0.06) +
            scale_noise
        )
        scale = float(np.clip(scale, 0.70, 1.30))

        # Rotation jitter: more at high fatigue, less when attentive
        rot_std = 0.8 + f * 2.5 - a * 0.6
        rotate_deg = float(self._rng.normal(0, max(0.3, rot_std)))

        # Offset jitter
        offset_x = float(self._rng.normal(0, 1.0 + f * 1.5))
        offset_y = float(self._rng.normal(0, 0.8 + f * 1.2))

        # Opacity: tired writers press harder sometimes, sometimes lighter
        alpha = float(np.clip(self._rng.normal(0.92 - f * 0.08, 0.04), 0.70, 1.0))

        # Tremor amplitude (used by artifact_sim)
        tremor = float(np.clip(f * pers["tremor_sensitivity"] * 0.9, 0.0, 1.0))

        # Slant
        slant = pers["slant_bias"] + self._slant_base * (1.0 + f * 0.3)
        slant = float(np.clip(slant, -12.0, 12.0))

        return GlyphParams(
            scale=scale,
            rotate_deg=rotate_deg,
            offset_x=offset_x,
            offset_y=offset_y,
            baseline_y=baseline_y,
            alpha=alpha,
            tremor=tremor,
            slant=slant,
            spacing_factor=1.0,
        )

    def next_word_params(self, word: str) -> GlyphParams:
        """
        Word-level params (used when rendering a whole word image at once).
        Includes rush factor for common words.
        """
        is_common = word.lower() in _COMMON_WORDS
        rush = is_common * self._personality["rush_sensitivity"]

        params = self.next_glyph(word)
        params.scale *= (1.0 - rush * 0.10)
        params.spacing_factor = 1.0 - rush * 0.12
        return params

    # ------------------------------------------------------------------
    # Readable state (for debugging / UI)
    # ------------------------------------------------------------------

    @property
    def fatigue(self) -> float:
        return self._fatigue

    @property
    def attention(self) -> float:
        return self._attention

    @property
    def chars_written(self) -> int:
        return self._chars_written
