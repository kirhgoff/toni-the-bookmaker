"""Per-book pronunciation lexicon: `term = respelling` lines, `#` comment lines."""

import re
import warnings
from pathlib import Path


def load_lexicon(path: Path) -> dict[str, str]:
    lexicon: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term, separator, respelling = line.partition("=")
        if separator and term.strip() and respelling.strip():
            lexicon[term.strip().lower()] = respelling.strip()
        else:
            warnings.warn(f"Ignoring unparseable lexicon line: {line}")
    return lexicon


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    table = {term.lower(): respelling for term, respelling in lexicon.items()}
    if not table:
        return text
    terms = sorted(table, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)")
    lowered = "".join(char.lower() for char in text)
    origin = [index for index, char in enumerate(text) for _ in char.lower()]
    pieces: list[str] = []
    position = 0
    for match in pattern.finditer(lowered):
        start, end = origin[match.start()], origin[match.end() - 1] + 1
        pieces.append(text[position:start] + table[match.group(0)])
        position = end
    return "".join(pieces) + text[position:]
