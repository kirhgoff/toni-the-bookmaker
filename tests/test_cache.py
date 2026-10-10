from conftest import TEXT, requires_ffmpeg, run_toni

CHUNKS = TEXT.split("\n\n")
THREE = "\n\n".join(CHUNKS[:3])


@requires_ffmpeg
def test_edit_rerenders_only_changed_chunk(fake, tmp_path) -> None:
    cache = tmp_path / "cache"
    run_toni(tmp_path / "a", THREE, "--cache-dir", str(cache))
    assert len(fake.takes) == 3

    edited = "\n\n".join([CHUNKS[0], "Second edited line.", CHUNKS[2]])
    work = run_toni(tmp_path / "b", edited, "--cache-dir", str(cache))
    assert len(fake.takes) == 4
    assert fake.takes[3][0] == "Second edited line."
    chunks = work.load_manifest().chunks
    assert chunks["0"]["reused"] is True
    assert "reused" not in chunks["1"]

    run_toni(tmp_path / "c", THREE, "--cache-dir", str(cache), "--seed", "1")
    assert len(fake.takes) == 7


@requires_ffmpeg
def test_qc_fail_evicts_cache_entry(fake, tmp_path) -> None:
    fake.bad_takes = {CHUNKS[1]: 1}
    cache = tmp_path / "cache"
    work = run_toni(tmp_path, THREE, "--cache-dir", str(cache))
    assert len(list(cache.glob("*.wav"))) == 3
    key = work.load_manifest().chunks["1"]["key"]
    assert (cache / f"{key}.wav").exists()
