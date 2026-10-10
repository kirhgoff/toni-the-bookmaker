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
    return calls


def transcribe(device="cpu"):
    return load_transcriber(device)(np.zeros(16000, dtype="float32"), 16000)


def test_language_is_passed_to_whisper(asr_calls, monkeypatch):
    monkeypatch.setenv("TONI_LANGUAGE", "ru")
    assert transcribe() == "привет"
    assert asr_calls == [{"generate_kwargs": {"language": "ru", "task": "transcribe"}}]


def test_language_is_auto_detected_when_unset(asr_calls, monkeypatch):
    monkeypatch.delenv("TONI_LANGUAGE", raising=False)
    transcribe()
    assert asr_calls == [{"generate_kwargs": {}}]
