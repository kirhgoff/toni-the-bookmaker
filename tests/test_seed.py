from conftest import requires_ffmpeg, run_toni

from toni.seed import chunk_seed


def test_chunk_seed_table() -> None:
    assert chunk_seed(0, "a", 0) == chunk_seed(0, "a", 0)
    assert chunk_seed(0, "a", 1) != chunk_seed(0, "a", 0)
    assert chunk_seed(0, "b", 0) != chunk_seed(0, "a", 0)
    assert 0 <= chunk_seed(2**40, "x", 7) < 2**31


@requires_ffmpeg
def test_same_text_gets_same_rng_regardless_of_position(fake, tmp_path) -> None:
    text = "Same little line.\n\nOther line here.\n\nSame little line."
    work = run_toni(tmp_path, text)
    same = [rng for t, rng in fake.takes if t == "Same little line."]
    other = [rng for t, rng in fake.takes if t == "Other line here."]
    assert len(same) == 2 and same[0] == same[1]
    assert other[0] != same[0]
    manifest = work.load_manifest()
    assert manifest.chunks["0"]["seed"] == manifest.chunks["2"]["seed"]
    assert manifest.seed == 0

    run_toni(tmp_path / "again", text, "--seed", "5")
    assert [rng for t, rng in fake.takes[3:] if t == "Same little line."][0] != same[0]
