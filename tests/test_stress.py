import sys

from toni import stress


def _fake_accentor(text: str) -> str:
    return text.replace("привет", "прив+ет").replace("замок", "з+амок")


def test_plus_marker_passes_accentor_output_through(monkeypatch):
    monkeypatch.setattr(stress, "_load_accentor", lambda: _fake_accentor)
    assert stress.mark_stress("привет") == "прив+ет"


def test_combining_marker_moves_plus_after_the_vowel(monkeypatch):
    monkeypatch.setattr(stress, "_load_accentor", lambda: _fake_accentor)
    result = stress.mark_stress("привет замок", marker="combining")
    assert result == "прив" + "е" + "́" + "т" + " " + "з" + "а" + "́" + "мок"
    assert "+" not in result


def test_unknown_marker_style_raises(monkeypatch):
    monkeypatch.setattr(stress, "_load_accentor", lambda: _fake_accentor)
    try:
        stress.mark_stress("привет", marker="bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_accentor_is_loaded_lazily_and_cached(monkeypatch):
    calls = []

    def loader():
        calls.append(1)
        return _fake_accentor

    monkeypatch.setattr(stress, "_accentor", None)
    monkeypatch.setattr(stress, "_load_accentor", loader)
    stress.mark_stress("привет")
    assert calls == [1]


def test_missing_dependency_raises_clear_import_error(monkeypatch):
    monkeypatch.setattr(stress, "_accentor", None)
    monkeypatch.setitem(sys.modules, "silero_stress", None)
    try:
        stress._load_accentor()
        assert False, "expected ImportError"
    except ImportError as exc:
        assert "stress" in str(exc)
