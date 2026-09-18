import pytest

from toni.tts.registry import get_engine, list_engines


def test_list_engines_contains_all_five():
    assert set(list_engines()) == {"pocket", "kani", "omni", "espeech", "qwen"}


def test_get_engine_unknown_raises_value_error():
    with pytest.raises(ValueError):
        get_engine("nonexistent")
