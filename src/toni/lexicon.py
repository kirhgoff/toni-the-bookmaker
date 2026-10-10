"""Per-book pronunciation lexicon: `term = respelling` lines, `#` comments."""

import re
from pathlib import Path


def load_lexicon(path: Path) -> dict[str, str]:
    lexicon: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        term, separator, respelling = line.partition("=")
        if separator and term.strip() and respelling.strip():
            lexicon[term.strip().casefold()] = respelling.strip()
    return lexicon


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    if not lexicon:
        return text
    terms = sorted(lexicon, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: lexicon[match.group(0).casefold()], text)
