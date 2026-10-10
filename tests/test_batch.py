from conftest import TEXT, requires_ffmpeg, run_toni

CHUNKS = [line for line in TEXT.split("\n\n")]


@requires_ffmpeg
def test_batches_render_every_chunk_once_in_length_order(fake, tmp_path) -> None:
    fake.width = 2
    work = run_toni(tmp_path, TEXT)
    assert sorted(t for t, _ in fake.takes) == sorted(CHUNKS)
    assert [len(b) for b in fake.batches] == [2, 2]
    lengths = [len(t) for batch in fake.batches for t in batch]
    assert lengths == sorted(lengths)
    assert work.get_all_audio_chunks_ordered() == ["0", "1", "2", "3", "4"]
    assert (tmp_path / "book.mp3").exists()
    assert "seed" in work.load_manifest().chunks["0"]


@requires_ffmpeg
def test_auto_width_is_asked_after_the_model_is_loaded(fake, tmp_path) -> None:
    fake.width = 2
    run_toni(tmp_path, TEXT)
    assert fake.width_asked_while_loaded == [True]


@requires_ffmpeg
def test_failing_batch_falls_back_per_chunk(fake, tmp_path) -> None:
    fake.width = 2
    fake.fail_texts = {CHUNKS[3]}
    work = run_toni(tmp_path, TEXT)
    chunks = work.load_manifest().chunks
    assert chunks["3"]["status"] == "split"
    assert chunks["3_0"]["status"] == chunks["3_1"]["status"] == "completed"
    assert len(fake.batches) == 2
    partner = next(b for b in fake.batches if CHUNKS[3] in b)
    other = next(t for t in partner if t != CHUNKS[3])
    assert [t for t, _ in fake.takes].count(other) == 1


def test_batches_never_mix_speeds(tmp_path) -> None:
    from pathlib import Path

    from toni.cli import _batches
    from toni.work_manager import WorkManager

    work = WorkManager(tmp_path / "book.mp3", tmp_path / "work")
    work.setup()
    work.init_manifest(input_file=Path("in.txt"), output_file=Path("book.mp3"), model="omni",
                       voice_file=None, sample_rate=24000, chunk_pause_ms=0, total_chunks=4,
                       chunk_marks=[{}, {"speed": 0.85}, {}, {"speed": 0.85}])
    for i in range(4):
        work.save_chunk_text(str(i), "x" * (i + 1))
    assert _batches(work, ["0", "1", "2", "3"], 2) == [["0", "2"], ["1", "3"]]


def test_negative_batch_is_rejected(fake, tmp_path) -> None:
    from click.testing import CliRunner

    from toni.cli import main

    (tmp_path / "b.txt").write_text("Hello there.")
    result = CliRunner().invoke(main, ["-i", str(tmp_path / "b.txt"), "--batch", "-1"])
    assert result.exit_code == 2 and "--batch" in result.output
