"""Abstract base class for TTS engines."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import numpy as np


class TTSEngine(ABC):
    """Abstract base class for Text-to-Speech engines.

    Implement this interface to add support for a new TTS model.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the engine name identifier."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Return the audio sample rate in Hz."""

    @property
    @abstractmethod
    def max_chunk_chars(self) -> int:
        """Return the maximum recommended characters per chunk."""

    supports_speed = False
    supports_batching = False

    @abstractmethod
    def load(self) -> None:
        """Load the model into memory. Called once before generation."""

    @abstractmethod
    def generate(
        self,
        text: str,
        voice_sample: Path | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        """Generate audio from text.

        Args:
            text: The text to convert to speech.
            voice_sample: Optional path to a WAV file for voice cloning.
            progress_callback: Optional callback called with progress (0.0-1.0).

        Returns:
            Audio data as a 1D numpy array of float32 samples.
        """

    def batch_width(self) -> int:
        return 1

    def generate_batch(self, texts: list[str], voice_sample: Path | None = None, **kwargs) -> list[np.ndarray]:
        return [self.generate(text, voice_sample=voice_sample, **kwargs) for text in texts]

    def unload(self) -> None:
        """Unload the model from memory. Optional cleanup."""
