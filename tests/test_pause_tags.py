from pathlib import Path

import pytest

from toni.chunker import chunk_text, chunk_with_marks
from toni.cli import _speed_kwargs
from toni.work_manager import WorkManager


def marks(text):
    return [(c.text, c.pause_ms, c.speed) for c in chunk_with_marks(text)]


def test_pause_tag_splits_and_records_default_pause():
    assert marks("Before. [pause] After.") == [("Before.", 350, None), ("After.", 0, None)]


def test_pause_duration_in_ms_and_seconds_is_clamped():
    assert marks("A. [pause 800ms] B.")[0][1] == 800
    assert marks("A. [pause 2s] B.")[0][1] == 2000
    assert marks("A. [pause 99s] B.")[0][1] == 10_000


def test_consecutive_pauses_add_up():
    assert marks("A. [pause 100ms][pause 200ms] B.")[0][1] == 300


def test_slow_passage_carries_speed_and_tags_are_never_spoken():
    result = marks("Fast one. [slow]Slow one.[/slow] Fast again.")
    assert result == [("Fast one.", 0, None), ("Slow one.", 0, 0.85), ("Fast again.", 0, None)]
    assert "[" not in " ".join(chunk_text("Fast one. [slow]Slow one.[/slow] Fast again."))


def test_pause_digits_are_not_normalised_into_words():
    assert marks("A. [pause 800ms] B.")[0][0] == "A."


def test_malformed_tags_stay_as_text_with_a_warning():
    with pytest.warns(UserWarning, match="Malformed"):
        assert chunk_text("Hello [pause soon] there.") == ["Hello [pause soon] there."]
    with pytest.warns(UserWarning, match="Malformed"):
        assert chunk_text("Hello [/slow] there.") == ["Hello [/slow] there."]


def test_unclosed_slow_warns_and_runs_to_the_end():
    with pytest.warns(UserWarning, match="never closed"):
        assert marks("[slow]All of it.") == [("All of it.", 0, 0.85)]


def test_leading_pause_with_nothing_before_it_is_dropped():
    assert marks("[pause] Start.") == [("Start.", 0, None)]


class FakeEngine:
    name = "fake"

    def __init__(self, supports_speed):
        self.supports_speed = supports_speed


def test_speed_goes_to_engines_that_support_it_and_warns_once_for_others(capsys):
    assert _speed_kwargs(FakeEngine(True), 0.85) == {"speed": 0.85}
    assert _speed_kwargs(FakeEngine(True), None) == {}
    assert _speed_kwargs(FakeEngine(False), 0.85) == {}
    assert _speed_kwargs(FakeEngine(False), 0.85) == {}
    assert capsys.readouterr().err.count("does not support [slow]") == 1


def test_manifest_stays_compatible_and_split_chunk_pause_follows_last_sub_chunk(tmp_path: Path):
    work = WorkManager(tmp_path / "book.mp3", work_base=tmp_path / "work")
    work.setup()
    work.init_manifest(
        input_file=Path("in.txt"), output_file=Path("book.mp3"), model="omni",
        voice_file=None, sample_rate=24000, chunk_pause_ms=0, total_chunks=3,
        chunk_marks=[{"pause_ms": 800, "speed": 0.85}, {}, {"pause_ms": 100}],
    )
    work.add_sub_chunk("0", "0_0", "a")
    work.add_sub_chunk("0", "0_1", "b")

    assert work.get_extra_pauses(["0_0", "0_1", "1", "2"]) == [0, 800, 0, 100]
    assert work.get_chunk_speed("0_1") == 0.85
    assert work.get_chunk_speed("1") is None

    legacy = {"status": "pending"}
    work._manifest.chunks["1"] = legacy
    work.save_manifest()
    assert work.get_extra_pauses(["1"]) == [0]


@pytest.mark.parametrize("tag, expected_ms", [("[PAUSE]", 350), ("[Pause 1s]", 1000), ("[ pause ]", 350), ("[pause 2 S]", 2000)])
def test_tag_variants_in_case_and_spacing_parse_and_are_not_spoken(tag, expected_ms):
    result = marks(f"A. {tag} B.")
    assert result == [("A.", expected_ms, None), ("B.", 0, None)]


def test_slow_tag_variants_parse():
    assert marks("A. [ SLOW ]B.[ /Slow ] C.") == [("A.", 0, None), ("B.", 0, 0.85), ("C.", 0, None)]


def test_pause_after_an_unspeakable_segment_is_not_lost():
    result = marks("Hello [pause] — [pause 2s] world.")
    assert result == [("Hello", 2350, None), ("world.", 0, None)]
