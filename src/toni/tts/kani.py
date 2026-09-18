"""Kani TTS 2 engine implementation."""

from pathlib import Path
from typing import Callable

import numpy as np

from toni.tts.base import TTSEngine


class KaniTTSEngine(TTSEngine):
    """TTS engine using NineNineSix's Kani TTS 2 model.

    Kani TTS 2 is a higher-quality model optimized for GPU execution.
    - 400M parameters
    - Requires GPU (3GB VRAM)
    - 22kHz sample rate
    - Supports voice cloning via speaker embeddings
    """

    def __init__(self):
        self._model = None
        self._embedder = None

    @property
    def name(self) -> str:
        return "kani"

    @property
    def sample_rate(self) -> int:
        return 22000

    @property
    def max_chunk_chars(self) -> int:
        return 500

    def load(self) -> None:
        try:
            from kani_tts import KaniTTS, SpeakerEmbedder
        except ImportError:
            raise ImportError(
                "kani-tts-2 is not installed. Install it with: uv sync --extra kani"
            )

        self._model = KaniTTS("nineninesix/kani-tts-2-en")
        self._embedder = SpeakerEmbedder()

    def generate(
        self,
        text: str,
        voice_sample: Path | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        if self._model is None:
            self.load()

        if progress_callback:
            progress_callback(0.1)

        speaker_emb = None
        if voice_sample is not None:
            speaker_emb = self._embedder.embed_audio_file(str(voice_sample))

        if speaker_emb is not None:
            audio, _ = self._model(text, speaker_emb=speaker_emb)
        else:
            audio, _ = self._model(text)

        if progress_callback:
            progress_callback(1.0)

        if hasattr(audio, "numpy"):
            audio = audio.numpy()

        return audio.astype(np.float32)

    def unload(self) -> None:
        self._model = None
        self._embedder = None
