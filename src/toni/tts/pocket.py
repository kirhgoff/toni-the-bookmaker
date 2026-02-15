"""Pocket TTS engine implementation."""

from pathlib import Path
from typing import Callable

import numpy as np

from toni.tts.base import TTSEngine


class PocketTTSEngine(TTSEngine):
    """TTS engine using Kyutai's Pocket TTS model.

    Pocket TTS is a lightweight model optimized for CPU execution.
    - 100M parameters
    - Runs on CPU (no GPU required)
    - ~6x real-time on MacBook Air M4
    - Supports voice cloning
    """

    def __init__(self):
        self._model = None
        self._voice_state = None

    @property
    def name(self) -> str:
        return "pocket"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def max_chunk_chars(self) -> int:
        return 1000

    def load(self) -> None:
        try:
            from pocket_tts import TTSModel
        except ImportError:
            raise ImportError(
                "pocket-tts is not installed. Install it with: uv sync --extra pocket"
            )

        self._model = TTSModel.load_model()

    def generate(
        self,
        text: str,
        voice_sample: Path | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        if self._model is None:
            self.load()

        if voice_sample is not None:
            voice_state = self._model.get_state_for_audio_prompt(str(voice_sample))
        else:
            voice_state = self._model.get_state_for_audio_prompt(
                "hf://kyutai/tts-voices/alba-mackenna/casual.wav"
            )

        if progress_callback:
            progress_callback(0.1)

        audio = self._model.generate_audio(voice_state, text)

        if progress_callback:
            progress_callback(1.0)

        return audio.numpy().astype(np.float32)

    def unload(self) -> None:
        self._model = None
        self._voice_state = None
