import wave
from pathlib import Path

import numpy as np
import pytest

from toni.audio_encoder import (
    build_chapters,
    concatenate_with_ffmpeg,
    gap_after,
    pause_after,
    trim_edges,
)


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


SR = 24000


def tone(ms: int) -> np.ndarray:
    t = np.arange(SR * ms // 1000) / SR
    return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_trim_edges_keeps_margin_and_interior():
    gap = np.zeros(SR // 2, dtype=np.float32)
    audio = np.concatenate([np.zeros(SR), tone(300), gap, tone(300), np.zeros(SR)])
    trimmed = trim_edges(audio, SR)
    margin = int(0.04 * SR)
    expected = len(tone(300)) * 2 + len(gap) + 2 * margin
    assert abs(len(trimmed) - expected) < 100


def test_trim_edges_all_silent_is_safe():
    assert len(trim_edges(np.zeros(SR, dtype=np.float32), SR)) <= int(0.04 * SR)
    assert len(trim_edges(np.zeros(0, dtype=np.float32), SR)) == 0


def test_gap_after_paragraph_uses_paragraph_pause():
    assert gap_after("Он ушел.", True, 500, 1000) == 1000
    assert gap_after("Он ушел.", False, 500, 1000) == 500
    assert gap_after("сказал он,", False, 500, 1000) == 125


def test_build_chapters_paragraph_boundary_gets_paragraph_pause(tmp_path):
    paths = [write_wav(tmp_path / f"{i}.wav", 1000) for i in range(3)]
    texts = ["Some text.", "More text.", "CHAPTER 2"]
    chapters, total = build_chapters(
        paths,
        texts,
        pause_ms=400,
        paragraph_ends=[False, True, False],
        paragraph_pause_ms=800,
    )
    assert chapters == [(2000 + 400 + 800, "CHAPTER 2")]
    assert total == 3000 + 400 + 800


def test_concat_inserts_paragraph_silence(tmp_path):
    paths = [write_wav(tmp_path / f"{i}.wav", 500) for i in range(2)]
    concatenate_with_ffmpeg(
        paths,
        tmp_path / "out.mp3",
        24000,
        pause_ms=200,
        paragraph_ends=[True, False],
        paragraph_pause_ms=400,
    )
    assert (tmp_path / "silence_400.wav").exists()
    assert not (tmp_path / "silence_200.wav").exists()
