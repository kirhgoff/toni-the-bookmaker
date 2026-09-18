"""Qwen3-TTS engine implementation."""

import os
from pathlib import Path
from typing import Callable

import numpy as np

from toni.tts.base import TTSEngine

DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

LANGUAGE_NAMES = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}


class QwenTTSEngine(TTSEngine):
    """TTS engine using Qwen3-TTS, an Apache-2.0 alternative to OmniVoice.

    - 1.7B parameters by default (12Hz token rate, 24 kHz output) — fits a
      12 GB GPU or Apple Silicon comfortably; override with TONI_QWEN_MODEL
    - Zero-shot voice cloning from a reference WAV plus its transcript; no
      designed-voice mode, so a voice sample and transcript are required
    - Does NOT honour stress marks: the maintainers say Qwen3-TTS was trained
      without them and that adding '+' notation makes pronunciation worse
      (https://github.com/QwenLM/Qwen3-TTS/discussions/185), so text is passed through unmarked

    Environment overrides:
        TONI_LANGUAGE:   language code (e.g. 'ru'); unset = English
        TONI_REF_TEXT:   transcript of the voice sample (required for cloning)
        TONI_QWEN_MODEL: HuggingFace model repo id; default Qwen/Qwen3-TTS-12Hz-1.7B-Base
    """

    def __init__(self):
        self._model = None

    @property
    def name(self) -> str:
        return "qwen"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def max_chunk_chars(self) -> int:
        return 300

    def _resolve_device(self) -> str:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def load(self) -> None:
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError:
            raise ImportError(
                "qwen-tts is not installed. Install it with: uv sync --extra qwen"
            )

        device = self._resolve_device()
        self._model = Qwen3TTSModel.from_pretrained(
            os.environ.get("TONI_QWEN_MODEL", DEFAULT_MODEL),
            device_map=device,
            dtype=torch.float32 if device == "cpu" else torch.float16,
        )

    def generate(
        self,
        text: str,
        voice_sample: Path | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        if voice_sample is None:
            raise ValueError(
                "qwen requires a voice sample to clone (-v); it has no designed-voice mode"
            )
        ref_text = os.environ.get("TONI_REF_TEXT")
        if not ref_text:
            raise ValueError("qwen requires TONI_REF_TEXT (transcript of the voice sample) for cloning")

        if self._model is None:
            self.load()

        language = LANGUAGE_NAMES.get(os.environ.get("TONI_LANGUAGE", "en").lower(), "English")

        if progress_callback:
            progress_callback(0.1)

        wavs, _sample_rate = self._model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=str(voice_sample),
            ref_text=ref_text,
        )

        if progress_callback:
            progress_callback(1.0)

        return np.asarray(wavs[0], dtype=np.float32)

    def unload(self) -> None:
        self._model = None
