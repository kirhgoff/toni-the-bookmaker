import sys
import types

import numpy as np
import pytest

from toni.tts.omni import OmniVoiceEngine


class FakeModel:
    def __init__(self, compiled_breaks: bool = False):
        self.llm = "eager"
        self.compiled_breaks = compiled_breaks

    def generate(self, **kwargs):
        if self.compiled_breaks and self.llm == "compiled":
            raise RuntimeError("triton exploded")
        return [np.zeros(10, dtype=np.float32) for _ in kwargs["text"]]


@pytest.fixture
def cuda_engine(monkeypatch):
    import torch

    monkeypatch.setenv("TONI_OMNI_COMPILE", "1")
    monkeypatch.setitem(sys.modules, "triton", types.ModuleType("triton"))
    monkeypatch.setattr(torch, "compile", lambda module: "compiled")
    engine = OmniVoiceEngine()
    monkeypatch.setattr(engine, "_resolve_device", lambda: "cuda")
    return engine


def test_flag_off_does_not_compile(cuda_engine, monkeypatch) -> None:
    monkeypatch.delenv("TONI_OMNI_COMPILE")
    cuda_engine._model = FakeModel()
    cuda_engine._compile_llm()
    assert cuda_engine._model.llm == "eager"


def test_no_cuda_does_not_compile(cuda_engine, monkeypatch) -> None:
    monkeypatch.setattr(cuda_engine, "_resolve_device", lambda: "mps")
    cuda_engine._model = FakeModel()
    cuda_engine._compile_llm()
    assert cuda_engine._model.llm == "eager"


def test_no_triton_does_not_compile(cuda_engine, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "triton", None)
    cuda_engine._model = FakeModel()
    cuda_engine._compile_llm()
    assert cuda_engine._model.llm == "eager"


def test_compiled_run_works(cuda_engine) -> None:
    cuda_engine._model = FakeModel()
    cuda_engine._compile_llm()
    assert cuda_engine._model.llm == "compiled"
    assert len(cuda_engine.generate_batch(["a", "b"])) == 2
    assert cuda_engine._model.llm == "compiled"


def test_failing_compiled_run_retries_eagerly_once(cuda_engine, capsys) -> None:
    cuda_engine._model = FakeModel(compiled_breaks=True)
    cuda_engine._compile_llm()
    assert len(cuda_engine.generate_batch(["a"])) == 1
    assert cuda_engine._model.llm == "eager"
    assert "using eager mode" in capsys.readouterr().err
    assert len(cuda_engine.generate_batch(["a"])) == 1


def test_numbered_cuda_device_compiles(cuda_engine, monkeypatch) -> None:
    monkeypatch.setattr(cuda_engine, "_resolve_device", lambda: "cuda:1")
    cuda_engine._model = FakeModel()
    cuda_engine._compile_llm()
    assert cuda_engine._model.llm == "compiled"


def test_numbered_cuda_device_sizes_batches_by_that_device(monkeypatch) -> None:
    import torch

    asked = []
    monkeypatch.setenv("TONI_OMNI_DEVICE", "cuda:1")
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda device: asked.append(device) or (20 * 2**30, 0))
    assert OmniVoiceEngine().batch_width() == 8
    assert asked == ["cuda:1"]
