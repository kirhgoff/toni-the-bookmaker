"""OmniVoice TTS engine implementation."""

import os
from pathlib import Path
from typing import Callable

import numpy as np

from toni.tts.base import TTSEngine

DEFAULT_INSTRUCT = "male, middle-aged, low pitch"


class OmniVoiceEngine(TTSEngine):
    """TTS engine using k2-fsa's OmniVoice model.

    - 0.6B parameters, 600+ languages, 24 kHz output
    - Voice cloning from a reference WAV, or voice design via instruct
    - Runs on Apple Silicon via MPS

    Environment overrides:
        TONI_OMNI_LANGUAGE: language code (e.g. 'ru'); unset = auto
        TONI_OMNI_INSTRUCT: voice attributes used when no voice sample is given
        TONI_OMNI_REF_TEXT: transcript of the voice sample, skips Whisper
        TONI_OMNI_DEVICE:   cpu / mps / cuda; unset = auto
        TONI_OMNI_NUM_STEP: diffusion steps, default 32 (16 is faster)
    """

    def __init__(self):
        self._model = None
        self._prompts: dict[str, object] = {}

    @property
    def name(self) -> str:
        return "omni"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def max_chunk_chars(self) -> int:
        return 300

    def _resolve_device(self) -> str:
        import torch

        device = os.environ.get("TONI_OMNI_DEVICE")
        if device:
            return device
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def load(self) -> None:
        try:
            import torch
            from omnivoice import OmniVoice
        except ImportError:
            raise ImportError(
                "omnivoice is not installed. Install it with: uv sync --extra omni"
            )

        device = self._resolve_device()
        self._model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map=device,
            dtype=torch.float32 if device == "cpu" else torch.float16,
        )

    def _voice_prompt(self, voice_sample: Path):
        key = str(voice_sample)
        if key not in self._prompts:
            ref_text = os.environ.get("TONI_OMNI_REF_TEXT")
            if ref_text is None and getattr(self._model, "_asr_pipe", None) is None:
                self._model.load_asr_model()
            self._prompts[key] = self._model.create_voice_clone_prompt(
                key, ref_text=ref_text
            )
        return self._prompts[key]

    def generate(
        self,
        text: str,
        voice_sample: Path | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig

        if self._model is None:
            self.load()

        kwargs = {
            "text": text,
            "language": os.environ.get("TONI_OMNI_LANGUAGE") or None,
            "generation_config": OmniVoiceGenerationConfig(
                num_step=int(os.environ.get("TONI_OMNI_NUM_STEP", "32"))
            ),
        }
        if voice_sample is not None:
            kwargs["voice_clone_prompt"] = self._voice_prompt(voice_sample)
        else:
            kwargs["instruct"] = os.environ.get("TONI_OMNI_INSTRUCT", DEFAULT_INSTRUCT)

        if progress_callback:
            progress_callback(0.1)

        audio = self._model.generate(**kwargs)

        if progress_callback:
            progress_callback(1.0)

        return np.asarray(audio[0], dtype=np.float32)

    def unload(self) -> None:
        self._model = None
        self._prompts.clear()
