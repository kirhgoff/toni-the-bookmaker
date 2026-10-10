import sys
from types import SimpleNamespace

import numpy as np
import pytest

from toni.transcribe import load_transcriber


@pytest.fixture
def asr_calls(monkeypatch):
    calls = []

    def fake_pipeline(*args, **kwargs):
        def asr(inputs, **call_kwargs):
            calls.append(call_kwargs)
            return {"text": " привет "}
        return asr

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float32="f32", float16="f16"))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(pipeline=fake_pipeline))
    monkeypatch.setitem(
        sys.modules,
        "transformers.models.whisper.tokenization_whisper",
        SimpleNamespace(TO_LANGUAGE_CODE={"english": "en", "russian": "ru"}),
    )
    return calls


def transcribe(device="cpu", seconds=1):
    return load_transcriber(device)(np.zeros(16000 * seconds, dtype="float32"), 16000)


def test_language_is_passed_to_whisper(asr_calls, monkeypatch):
    monkeypatch.setenv("TONI_LANGUAGE", "ru")
    assert transcribe() == "привет"
    assert asr_calls == [
        {"return_timestamps": False, "generate_kwargs": {"language": "ru", "task": "transcribe"}}
    ]


def test_language_is_auto_detected_when_unset(asr_calls, monkeypatch):
    monkeypatch.delenv("TONI_LANGUAGE", raising=False)
    transcribe()
    assert asr_calls == [{"return_timestamps": False, "generate_kwargs": {}}]


def test_region_tag_is_reduced_to_whispers_base_code(asr_calls, monkeypatch):
    monkeypatch.setenv("TONI_LANGUAGE", "en-US")
    transcribe()
    assert asr_calls[0]["generate_kwargs"] == {"language": "en", "task": "transcribe"}


def test_language_whisper_lacks_falls_back_to_auto_detect(asr_calls, monkeypatch):
    monkeypatch.setenv("TONI_LANGUAGE", "tlh")
    transcribe()
    assert asr_calls[0]["generate_kwargs"] == {}


def test_long_audio_uses_long_form_generation(asr_calls):
    transcribe(seconds=31)
    transcribe(seconds=1)
    assert [call["return_timestamps"] for call in asr_calls] == [True, False]
