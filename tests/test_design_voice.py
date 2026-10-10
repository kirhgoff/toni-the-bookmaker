import wave

from click.testing import CliRunner

from toni.design_voice import SENTENCES, main


def test_writes_wav_and_exact_sentence(fake, tmp_path) -> None:
    out, text_out = tmp_path / "voice_ref.wav", tmp_path / "voice_ref.txt"
    result = CliRunner().invoke(main, ["--out", str(out), "--text-out", str(text_out), "--language", "ru"])
    assert result.exit_code == 0, result.output
    assert text_out.read_text(encoding="utf-8") == SENTENCES["ru"]
    assert [t for t, _ in fake.takes] == [SENTENCES["ru"]]
    with wave.open(str(out)) as wf:
        assert wf.getnframes() > 0


def test_same_seed_same_draw_different_seed_differs(fake, tmp_path) -> None:
    def draw(seed: str) -> int:
        args = ["--out", str(tmp_path / "a.wav"), "--text-out", str(tmp_path / "a.txt"), "--seed", seed]
        assert CliRunner().invoke(main, args).exit_code == 0
        return fake.takes[-1][1]

    assert draw("3") == draw("3")
    assert draw("4") != draw("3")


def test_rejects_language_without_sentence(fake, tmp_path) -> None:
    args = ["--out", str(tmp_path / "a.wav"), "--text-out", str(tmp_path / "a.txt"), "--language", "de"]
    assert CliRunner().invoke(main, args).exit_code != 0
    assert fake.takes == []
