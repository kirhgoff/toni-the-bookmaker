"""OmniVoice TTS engine implementation."""

import os
import sys
from pathlib import Path
from typing import Callable

import numpy as np

from toni.text_normalization import base_language, normalization_enabled
from toni.tts.base import TTSEngine

DEFAULT_INSTRUCT = "male, middle-aged, low pitch"


class OmniVoiceEngine(TTSEngine):
    """TTS engine using k2-fsa's OmniVoice model.

    - 0.6B parameters, 600+ languages, 24 kHz output
    - Voice cloning from a reference WAV, or voice design via instruct
    - Runs on Apple Silicon via MPS

    Environment overrides:
        TONI_LANGUAGE:      language code (e.g. 'ru'); unset = auto
        TONI_OMNI_INSTRUCT: voice attributes used when no voice sample is given
        TONI_REF_TEXT:      transcript of the voice sample, skips Whisper
        TONI_OMNI_DEVICE:   cpu / mps / cuda; unset = auto
        TONI_OMNI_NUM_STEP: diffusion steps, default 32 (16 is faster)
        TONI_NORMALIZE:     0 turns off number/abbreviation normalisation, here and in the chunker
        TONI_BATCH:         chunks per model call, 0 = auto
        TONI_OMNI_COMPILE:  1 compiles the language model with torch.compile on CUDA
                            with Triton; any failure falls back to eager
        TONI_OMNI_SPEED:    speaking rate factor; below 1.0 gives every chunk more room
    """

    supports_speed = True
    supports_batching = True

    def __init__(self):
        self._model = None
        self._prompts: dict[str, object] = {}
        self._eager_llm = None
        self._first_compiled_run = False

    @property
    def name(self) -> str:
        return "omni"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def max_chunk_chars(self) -> int:
        return 300

    def _on_cuda(self) -> bool:
        return self._resolve_device().startswith("cuda")

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
        self._compile_llm()

    def _compile_llm(self) -> None:
        if os.environ.get("TONI_OMNI_COMPILE") != "1" or not self._on_cuda():
            return
        try:
            import torch
            import triton
        except ImportError:
            return
        self._eager_llm = self._model.llm
        self._model.llm = torch.compile(self._eager_llm)
        self._first_compiled_run = True

    def _generate(self, kwargs: dict):
        if not self._first_compiled_run:
            return self._model.generate(**kwargs)
        self._first_compiled_run = False
        try:
            return self._model.generate(**kwargs)
        except Exception as e:
            print(
                f"torch.compile failed ({str(e)[:100]}); using eager mode",
                file=sys.stderr,
            )
            self._model.llm = self._eager_llm
            return self._model.generate(**kwargs)

    def _voice_prompt(self, voice_sample: Path):
        key = str(voice_sample)
        if key not in self._prompts:
            ref_text = os.environ.get("TONI_REF_TEXT")
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
        speed: float | None = None,
    ) -> np.ndarray:
        if progress_callback:
            progress_callback(0.1)

        audio = self.generate_batch([text], voice_sample, speed=speed)[0]

        if progress_callback:
            progress_callback(1.0)

        return audio

    def generate_batch(
        self,
        texts: list[str],
        voice_sample: Path | None = None,
        speed: float | None = None,
    ) -> list[np.ndarray]:
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig

        if self._model is None:
            self.load()

        kwargs = {
            "text": texts,
            "language": os.environ.get("TONI_LANGUAGE") or None,
            "generation_config": OmniVoiceGenerationConfig(
                num_step=int(os.environ.get("TONI_OMNI_NUM_STEP", "32"))
            ),
        }
        base_speed = float(os.environ.get("TONI_OMNI_SPEED") or 1.0)
        if speed or base_speed != 1.0:
            kwargs["speed"] = base_speed * (speed or 1.0)
        if normalization_enabled() and base_language(kwargs["language"]) == "en":
            kwargs["normalize_text"] = True
        if voice_sample is not None:
            kwargs["voice_clone_prompt"] = self._voice_prompt(voice_sample)
        else:
            kwargs["instruct"] = os.environ.get("TONI_OMNI_INSTRUCT", DEFAULT_INSTRUCT)

        return [np.asarray(a, dtype=np.float32) for a in self._generate(kwargs)]

    def batch_width(self) -> int:
        import torch

        if not self._on_cuda():
            return 2
        free_gb = torch.cuda.mem_get_info(self._resolve_device())[0] / 2**30
        return 1 if free_gb < 2 else 2 if free_gb < 6 else 4 if free_gb < 12 else 8

    def unload(self) -> None:
        self._model = None
        self._prompts.clear()
