from conftest import requires_ffmpeg, run_toni

from toni.seed import chunk_seed


def test_chunk_seed_table() -> None:
    assert chunk_seed(0, "a", 0) == chunk_seed(0, "a", 0)
    assert chunk_seed(0, "a", 1) != chunk_seed(0, "a", 0)
    assert chunk_seed(0, "b", 0) != chunk_seed(0, "a", 0)
    assert 0 <= chunk_seed(2**40, "x", 7) < 2**31


@requires_ffmpeg
def test_same_text_gets_same_rng_regardless_of_position(fake, tmp_path) -> None:
    work = run_toni(tmp_path, "Same little line.\n\nOther line here.\n\nSame little line.")
    assert fake.takes[0][0] == fake.takes[2][0]
    assert fake.takes[0][1] == fake.takes[2][1]
    assert fake.takes[1][1] != fake.takes[0][1]
    manifest = work.load_manifest()
    assert manifest.chunks["0"]["seed"] == manifest.chunks["2"]["seed"]
    assert manifest.seed == 0

    first_sample = fake.takes[0][1]
    run_toni(tmp_path / "again", "Same little line.\n\nOther line here.\n\nSame little line.", "--seed", "5")
    assert fake.takes[3][1] != first_sample
