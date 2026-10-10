import pytest
from conftest import TEXT, requires_ffmpeg, run_toni

from toni.qc import Thresholds, verdict, word_error_rate

CHUNKS = TEXT.split("\n\n")


@pytest.mark.parametrize("reference,hypothesis,expected", [
    ("a b c d", "a b c d", 0.0),
    ("a b c d", "a b d", 0.25),
    ("Прив+ет, мир!", "привет мир", 0.0),
    ("", "", 0.0),
    ("", "x", 1.0),
    ("你好世界", "你好世", 0.25),
])
def test_word_error_rate_table(reference, hypothesis, expected) -> None:
    assert word_error_rate(reference, hypothesis) == expected


def test_verdict_skips_duration_for_short_chunks() -> None:
    assert verdict(0.0, 3.0, 2.0, Thresholds()) == "pass"
    assert verdict(0.0, 3.0, 10.0, Thresholds()) == "fail"
    assert verdict(0.3, 1.0, 10.0, Thresholds()) == "fail"


@requires_ffmpeg
def test_bad_take_is_regenerated_with_new_seed(fake, tmp_path) -> None:
    fake.bad_takes = {CHUNKS[1]: 1}
    work = run_toni(tmp_path, TEXT)
    retaken = [rng for t, rng in fake.takes if t == CHUNKS[1]]
    assert len(retaken) == 2 and retaken[0] != retaken[1]
    for i in (0, 2, 3, 4):
        assert [t for t, _ in fake.takes].count(CHUNKS[i]) == 1
    chunk = work.load_manifest().chunks["1"]
    assert chunk["retries"] == 1
    assert chunk["qc"]["verdict"] == "pass"
    assert chunk["qc"]["attempts"] == 1
    assert fake.transcribed == 6

    run_toni(tmp_path, TEXT)
    assert fake.transcribed == 6
    assert len(fake.takes) == 6


@requires_ffmpeg
def test_gives_up_then_splits(fake, tmp_path) -> None:
    fake.bad_takes = {CHUNKS[3]: 9}
    work = run_toni(tmp_path, TEXT, "--qc-retries", "1")
    assert [t for t, _ in fake.takes].count(CHUNKS[3]) == 2
    chunks = work.load_manifest().chunks
    assert chunks["3"]["status"] == "split"
    assert chunks["3"]["qc"]["verdict"] == "fail"
    assert chunks["3_0"]["qc"]["verdict"] == "pass"
    assert work.get_all_audio_chunks_ordered() == ["0", "1", "2", "3_0", "3_1", "4"]


@requires_ffmpeg
def test_no_qc_skips_asr(fake, tmp_path) -> None:
    work = run_toni(tmp_path, TEXT, "--no-qc")
    assert fake.transcribed == 0
    assert all("qc" not in c for c in work.load_manifest().chunks.values())
