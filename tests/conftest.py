import random
import shutil
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from toni.cli import main
from toni.qc import expected_seconds
from toni.tts.base import TTSEngine
from toni.work_manager import WorkManager

SR = 8000
requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

TEXT = "First little line here.\n\nSecond little line here.\n\nThird line.\n\nFourth line is here.\n\nFifth."


def seconds_for(text: str) -> float:
    return expected_seconds(text)


class FakeEngine(TTSEngine):
    def __init__(self):
        self.takes: list[tuple[str, int]] = []
        self.batches: list[list[str]] = []
        self.width = 1
        self.fail_texts: set[str] = set()
        self.bad_takes: dict[str, int] = {}
        self.transcribed = 0

    name = property(lambda self: "fake")
    sample_rate = property(lambda self: SR)
    max_chunk_chars = property(lambda self: 40)

    def load(self) -> None:
        pass

    def batch_width(self) -> int:
        return self.width

    def _take(self, text: str) -> np.ndarray:
        if text in self.fail_texts:
            raise RuntimeError(f"boom: {text}")
        n = len(self.takes)
        self.takes.append((text, random.getrandbits(32)))
        length = int(seconds_for(text) * SR) // 1000 * 1000 + 1000 + n
        return np.full(length, 0.1, dtype=np.float32)

    def generate(self, text, voice_sample=None, progress_callback=None):
        return self._take(text)

    def generate_batch(self, texts, voice_sample=None, **kwargs):
        self.batches.append(list(texts))
        if any(t in self.fail_texts for t in texts):
            raise RuntimeError("batch boom")
        return [self._take(t) for t in texts]


    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        self.transcribed += 1
        n = len(audio) % 1000
        text = self.takes[n][0]
        earlier = sum(1 for t, _ in self.takes[:n] if t == text)
        return "" if earlier < self.bad_takes.get(text, 0) else text


@pytest.fixture
def fake(monkeypatch) -> FakeEngine:
    engine = FakeEngine()
    for target in ("toni.cli.get_engine", "toni.tts.get_engine", "toni.tts.registry.get_engine"):
        monkeypatch.setattr(target, lambda name: engine)
    monkeypatch.setattr("toni.transcribe.load_transcriber", lambda device=None: engine.transcribe)
    return engine


def run_toni(tmp_path: Path, text: str, *args: str, output: str = "book.mp3") -> WorkManager:
    tmp_path.mkdir(exist_ok=True)
    src = tmp_path / "book.txt"
    src.write_text(text, encoding="utf-8")
    result = CliRunner().invoke(main, [
        "-i", str(src), "-o", str(tmp_path / output), "-m", "pocket", "--workers", "1",
        "--work-dir", str(tmp_path / "work"), *args], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return WorkManager(tmp_path / output, tmp_path / "work")
