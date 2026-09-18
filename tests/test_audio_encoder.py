import wave
from pathlib import Path

import numpy as np

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
