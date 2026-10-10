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


@requires_ffmpeg
def test_slow_tag_added_to_cached_paragraph_rerenders_it(fake, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("toni.cli._warned_speed_ignored", False)
    cache = tmp_path / "cache"
    run_toni(tmp_path / "a", THREE, "--cache-dir", str(cache), "--no-qc")
    assert len(fake.takes) == 3

    slowed = f"{CHUNKS[0]}\n\n[slow]{CHUNKS[1]}[/slow]\n\n{CHUNKS[2]}"
    run_toni(tmp_path / "b", slowed, "--cache-dir", str(cache), "--no-qc")
    assert [t for t, _ in fake.takes[3:]] == [CHUNKS[1]]


@requires_ffmpeg
def test_chunk_pause_change_rerenders_cached_chunks(fake, tmp_path) -> None:
    cache = tmp_path / "cache"
    run_toni(tmp_path / "a", THREE, "--cache-dir", str(cache), "--no-qc", "--chunk-pause", "500")
    run_toni(tmp_path / "b", THREE, "--cache-dir", str(cache), "--no-qc", "--chunk-pause", "800")
    assert len(fake.takes) == 6


@requires_ffmpeg
def test_gave_up_chunk_keeps_its_verdict_and_is_not_rerendered(fake, tmp_path) -> None:
    fake.bad_takes = {CHUNKS[1]: 9}
    cache = tmp_path / "cache"
    args = ("--cache-dir", str(cache), "--qc-retries", "1", "--max-retries", "0")
    run_toni(tmp_path / "a", THREE, *args)
    assert [t for t, _ in fake.takes].count(CHUNKS[1]) == 2
    assert len(list(cache.glob("*.qc.json"))) == 3
    takes, transcribed = len(fake.takes), fake.transcribed

    work = run_toni(tmp_path / "b", THREE, *args)
    assert (len(fake.takes), fake.transcribed) == (takes, transcribed)
    assert work.load_manifest().chunks["1"]["qc"]["verdict"] == "fail"
