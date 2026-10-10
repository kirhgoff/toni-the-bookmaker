import pytest
from conftest import TEXT, requires_ffmpeg, run_toni

from toni.qc import Thresholds, expected_seconds, spoken_form, verdict, word_error_rate

CHUNKS = TEXT.split("\n\n")


@pytest.mark.parametrize("reference,hypothesis,expected", [
    ("a b c d", "a b c d", 0.0),
    ("a b c d", "a b d", 0.25),
    ("Прив+ет, мир!", "привет мир", 0.0),
    ("", "", 0.0),
    ("", "x", 1.0),
    ("你好世界", "你好世", 0.25),
    ("twenty-five dollars", "twenty five dollars", 0.0),
    ("a — b", "a b", 0.0),
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


LONG_PARAGRAPHS = [
    f"Chapter {name} begins here, and the narrator keeps talking about {topic} "
    "for long enough that the sentence takes several seconds to read aloud."
    for name, topic in zip("ABCDEF", ("rivers", "stones", "winter", "markets", "ships", "lanterns"))
]


@pytest.fixture
def long_chunks(fake, monkeypatch):
    monkeypatch.setattr(type(fake), "max_chunk_chars", property(lambda self: 400))
    assert all(expected_seconds(p) >= 4 for p in LONG_PARAGRAPHS)
    return "\n\n".join(LONG_PARAGRAPHS)


@requires_ffmpeg
def test_uniformly_slow_run_passes_by_self_calibration(fake, long_chunks, tmp_path) -> None:
    fake.base_stretch = 1.8
    work = run_toni(tmp_path, long_chunks)
    assert len(fake.takes) == len(LONG_PARAGRAPHS)
    assert all(c["qc"]["verdict"] == "pass" for c in work.load_manifest().chunks.values())
    assert work.load_manifest().chunks["0"]["qc"]["ratio"] == pytest.approx(1.8, abs=0.05)


@requires_ffmpeg
def test_outlier_against_run_median_fails(fake, long_chunks, tmp_path) -> None:
    fake.stretch = {LONG_PARAGRAPHS[2]: 3.0}
    work = run_toni(tmp_path, long_chunks)
    assert [t for t, _ in fake.takes].count(LONG_PARAGRAPHS[2]) == 3
    assert work.load_manifest().chunks["2"]["qc"]["verdict"] == "fail"
    assert work.load_manifest().chunks["1"]["qc"]["verdict"] == "pass"


@requires_ffmpeg
def test_hypothesis_is_normalised_like_the_chunk_text(fake, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(type(fake), "max_chunk_chars", property(lambda self: 400))
    cases = {
        "ru": ("В 1812 году было 3 дня.", "В 1812 году было 3 дня."),
        "en": ("Mr. Smith paid $25 on May 3rd, 1999.", "Mr. Smith paid $25 on May 3rd, 1999."),
    }
    for language, (source, heard) in cases.items():
        monkeypatch.setenv("TONI_LANGUAGE", language)
        fake.say = lambda text, heard=heard: heard
        before = len(fake.takes)
        work = run_toni(tmp_path / language, source)
        assert len(fake.takes) - before == 1
        assert work.load_manifest().chunks["0"]["qc"]["verdict"] == "pass"
        assert work.load_manifest().chunks["0"]["qc"]["wer"] == 0


@requires_ffmpeg
def test_asr_error_keeps_the_chunk_and_the_run(fake, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("toni.cli.MIN_CHECKED_SECONDS", 0.1)
    fake.asr_errors = {CHUNKS[2]}
    work = run_toni(tmp_path, TEXT)
    chunk = work.load_manifest().chunks["2"]
    assert chunk["qc"]["verdict"] == "error"
    assert chunk["status"] == "completed"
    assert [t for t, _ in fake.takes].count(CHUNKS[2]) == 1
    assert work.get_all_audio_chunks_ordered() == ["0", "1", "2", "3", "4"]


@requires_ffmpeg
def test_errored_chunk_is_checked_again_on_resume(fake, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("toni.cli.MIN_CHECKED_SECONDS", 0.1)
    fake.asr_errors = {CHUNKS[2]}
    work = run_toni(tmp_path, TEXT)
    assert work.load_manifest().chunks["2"]["qc"]["verdict"] == "error"
    fake.asr_errors = set()
    transcribed = fake.transcribed
    work = run_toni(tmp_path, TEXT)
    assert work.load_manifest().chunks["2"]["qc"]["verdict"] == "pass"
    assert fake.transcribed == transcribed + 1
    assert [t for t, _ in fake.takes].count(CHUNKS[2]) == 1


def test_median_is_clamped_to_the_ratio_window() -> None:
    assert verdict(0.0, 3.0, 10.0, Thresholds(), median=3.0) == "fail"
    assert verdict(0.0, 1.0, 10.0, Thresholds(), median=3.0) == "pass"


def test_ru_ordinal_dates_match_the_spoken_form(monkeypatch) -> None:
    monkeypatch.delenv("TONI_NORMALIZE", raising=False)
    reference = spoken_form("Он уехал 5-го мая.", "ru")
    assert word_error_rate(reference, spoken_form("Он уехал 5 мая.", "ru")) == 0.0
    assert word_error_rate(reference, spoken_form("Он уехал пять мая.", "ru")) == 0.0
