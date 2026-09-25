"""ESpeech-TTS-1 engine implementation."""

import os
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from toni.chunker import split_into_sentences
from toni.stress import mark_stress
from toni.tts.base import TTSEngine

MODEL_REPO = "ESpeech/ESpeech-TTS-1_RL-V2"
CHECKPOINT_FILENAME = "espeech_tts_rlv2.pt"
VOCAB_FILENAME = "vocab.txt"
DIT_CONFIG = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)


F5_CLIP_SECONDS = 12.0
SENTENCE_PAUSE_SECONDS = 0.35


def _duration(path: str) -> float:
    info = sf.info(path)
    return info.frames / info.samplerate


class ESpeechTTSEngine(TTSEngine):
    """TTS engine using ESpeech-TTS-1, an F5-TTS-architecture model trained on Russian podcasts.

    - ~0.34B parameters, Russian-native, Apache-2.0
    - Zero-shot voice cloning from a reference WAV plus its transcript; no
      designed-voice mode, so a voice sample is required
    - Honours explicit '+' stress marks (e.g. "прив+ет")

    Environment overrides:
        TONI_LANGUAGE:       language code; stress marking is applied only for 'ru'
        TONI_REF_TEXT:       transcript of the voice sample; empty auto-transcribes via Whisper
        TONI_ESPEECH_DEVICE: cpu / mps / cuda; unset = auto
    """

    def __init__(self):
        self._model = None
        self._vocoder = None
        self._refs: dict[str, tuple] = {}

    @property
    def name(self) -> str:
        return "espeech"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def max_chunk_chars(self) -> int:
        return 500

    def _resolve_device(self) -> str:
        import torch

        device = os.environ.get("TONI_ESPEECH_DEVICE")
        if device:
            return device
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def load(self) -> None:
        try:
            from f5_tts.infer.utils_infer import load_model, load_vocoder
            from f5_tts.model import DiT
            from huggingface_hub import hf_hub_download
        except ImportError:
            raise ImportError(
                "f5-tts is not installed. Install it with: uv sync --extra espeech"
            )

        ckpt_file = hf_hub_download(repo_id=MODEL_REPO, filename=CHECKPOINT_FILENAME)
        vocab_file = hf_hub_download(repo_id=MODEL_REPO, filename=VOCAB_FILENAME)
        device = self._resolve_device()
        self._model = load_model(DiT, DIT_CONFIG, ckpt_file, vocab_file=vocab_file, device=device)
        self._vocoder = load_vocoder(device=device)

    def generate(
        self,
        text: str,
        voice_sample: Path | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        if voice_sample is None:
            raise ValueError(
                "espeech requires a voice sample to clone (-v); it has no designed-voice mode"
            )

        if self._model is None:
            self.load()

        from f5_tts.infer.utils_infer import infer_process, preprocess_ref_audio_text

        russian = os.environ.get("TONI_LANGUAGE") == "ru"
        if russian and "+" not in text:
            text = mark_stress(text)
        ref_audio, ref_text = self._reference(voice_sample, russian, preprocess_ref_audio_text)

        sentences = [s.strip() for s in split_into_sentences(text) if s.strip()]
        pause = np.zeros(int(SENTENCE_PAUSE_SECONDS * self.sample_rate), dtype=np.float32)
        parts: list[np.ndarray] = []
        for index, sentence in enumerate(sentences):
            wav, _sample_rate, _spectrogram = infer_process(
                ref_audio, ref_text, sentence, self._model, self._vocoder
            )
            if parts:
                parts.append(pause)
            parts.append(np.asarray(wav, dtype=np.float32))
            if progress_callback:
                progress_callback((index + 1) / len(sentences))

        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def _reference(self, voice_sample: Path, russian: bool, preprocess) -> tuple:
        key = str(voice_sample)
        if key not in self._refs:
            ref_text = os.environ.get("TONI_REF_TEXT", "")
            if russian and ref_text and "+" not in ref_text:
                ref_text = mark_stress(ref_text)
            clipped_audio, used_text = preprocess(key, ref_text)
            if ref_text and _duration(key) > F5_CLIP_SECONDS:
                clipped_audio, used_text = preprocess(key, "")
                if russian:
                    used_text = mark_stress(used_text)
            self._refs[key] = (clipped_audio, used_text)
        return self._refs[key]

    def unload(self) -> None:
        self._model = None
        self._vocoder = None
        self._refs.clear()
