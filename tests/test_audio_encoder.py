import wave
from pathlib import Path

import numpy as np
import pytest

from toni.audio_encoder import build_chapters, pause_after


def write_wav(path: Path, ms: int, sample_rate: int = 24000) -> Path:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.zeros(sample_rate * ms // 1000, dtype=np.int16).tobytes())
    return path


def test_pause_after_sentence_end_or_heading_is_full():
    assert pause_after("Он ушел.", 500) == 500
    assert pause_after("Правда?»", 500) == 500
    assert pause_after("CHAPTER 1", 500) == 500
    assert pause_after(None, 500) == 500


def test_pause_after_mid_sentence_is_short():
    assert pause_after("что пора бы, пожалуй,", 500) == 125
    assert pause_after("холодным голосом -", 500) == 125
    assert pause_after("сказал он;", 500) == 125


def test_build_chapters_offsets_use_variable_pauses(tmp_path):
    paths = [write_wav(tmp_path / f"{i}.wav", 1000) for i in range(3)]
    texts = ["CHAPTER 1", "cut mid-sentence,", "CHAPTER 2. Text."]
    chapters, total = build_chapters(paths, texts, pause_ms=400)
    assert [start for start, _ in chapters] == [0, 1000 + 400 + 1000 + 100]
    assert total == 3000 + 400 + 100


@pytest.mark.parametrize(
    "text,detected",
    [
        ("Part One", True),
        ("CHAPTER XII", True),
        ("Глава 1", True),
        ("ЧАСТЬ вторая", True),
        ("эпилог", True),
        ("Part of the problem was that nobody had told the old man anything at all.", False),
        ("Book lovers rejoice", True),
        ("Главный герой не спал всю ночь, потому что думал о долгой дороге домой.", False),
    ],
)
def test_default_chapter_pattern(tmp_path, text, detected):
    paths = [write_wav(tmp_path / "0.wav", 100)]
    chapters, _ = build_chapters(paths, [text], pause_ms=400)
    assert bool(chapters) is detected


def test_custom_chapter_pattern_still_respected(tmp_path):
    paths = [write_wav(tmp_path / "0.wav", 100)]
    chapters, _ = build_chapters(paths, ["Act 1"], pause_ms=400, pattern=r"^Act\b")
    assert chapters == [(0, "Act 1")]
