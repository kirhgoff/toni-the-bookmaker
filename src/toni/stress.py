"""Russian word-stress preprocessor.

Marks stressed vowels in Russian text using silero-stress, so that engines
which honour explicit stress (e.g. ESpeech-TTS-1) stop guessing homographs.
"""

import re
from typing import Literal

MarkerStyle = Literal["plus", "combining"]

_COMBINING_ACUTE = "́"

_accentor = None


def _load_accentor():
    global _accentor
    if _accentor is None:
        try:
            from silero_stress import load_accentor
        except ImportError:
            raise ImportError(
                "silero-stress is not installed. Install it with: uv sync --extra stress"
            )
        _accentor = load_accentor()
    return _accentor


def mark_stress(text: str, marker: MarkerStyle = "plus") -> str:
    """Return `text` with Russian word stress marked in the given style.

    'plus' puts a '+' before the stressed vowel (what ESpeech-TTS-1 honours).
    'combining' appends a combining acute accent (U+0301) after it instead.
    """
    plus_marked = _load_accentor()(text)
    if marker == "plus":
        return plus_marked
    if marker == "combining":
        return re.sub(r"\+(.)", lambda m: m.group(1) + _COMBINING_ACUTE, plus_marked)
    raise ValueError(f"Unknown stress marker style: {marker!r}")


def _demo() -> None:
    global _accentor
    _accentor = lambda text: text.replace("привет", "прив+ет")
    assert mark_stress("привет") == "прив+ет"
    assert mark_stress("привет", marker="combining") == "прив" + _COMBINING_ACUTE + "ет"
    _accentor = None
    print("stress: ok")


if __name__ == "__main__":
    _demo()
