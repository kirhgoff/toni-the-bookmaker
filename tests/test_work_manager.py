import sys
from multiprocessing import Pool
from pathlib import Path

from toni.work_manager import WorkManager


def _mark_completed(args):
    work_dir, chunk_id = args
    work = WorkManager.from_existing(work_dir)
    work.get_chunk_audio_path(chunk_id).write_bytes(b"")
    work.set_chunk_status(chunk_id, "completed")


def test_concurrent_status_writes(tmp_path: Path) -> None:
    work = WorkManager(tmp_path / "book.mp3", work_base=tmp_path / "work")
    work.setup()
    work.init_manifest(input_file=Path("in.txt"), output_file=Path("book.mp3"),
                       model="omni", voice_file=None, sample_rate=24000,
                       chunk_pause_ms=0, total_chunks=40)

    ids = [str(i) for i in range(40)]
    with Pool(processes=8) as pool:
        pool.map(_mark_completed, [(str(work.work_dir), i) for i in ids])

    work._manifest = None
    got = work.get_all_audio_chunks_ordered()
    assert got == ids, f"lost {set(ids) - set(got)} of 40 chunk statuses"


def test_nested_splits_are_collected(tmp_path: Path) -> None:
    work = WorkManager(tmp_path / "book.mp3", work_base=tmp_path / "work")
    work.setup()
    work.init_manifest(input_file=Path("in.txt"), output_file=Path("book.mp3"),
                       model="omni", voice_file=None, sample_rate=24000,
                       chunk_pause_ms=0, total_chunks=1)

    work.add_sub_chunk("0", "0_0", "a")
    work.add_sub_chunk("0_0", "0_0_0", "a")
    work.add_sub_chunk("0_0", "0_0_1", "b")
    for leaf in ("0_0_0", "0_0_1"):
        work.get_chunk_audio_path(leaf).write_bytes(b"")
        work.set_chunk_status(leaf, "completed")

    work._manifest = None
    assert work.get_all_audio_chunks_ordered() == ["0_0_0", "0_0_1"]


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
