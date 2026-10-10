"""Inline pacing tags: `[pause]`, `[pause 800ms]`, `[slow]...[/slow]`."""

import re
import warnings
from dataclasses import dataclass

DEFAULT_PAUSE_MS = 350
MAX_PAUSE_MS = 10_000
SLOW_SPEED = 0.85

TAG_CANDIDATE = re.compile(r"\[/?(?:pause|slow)(?:\s[^\]]*)?\]")
PAUSE_TAG = re.compile(r"\[pause(?:\s+(\d+(?:\.\d+)?)\s*(ms|s))?\]")


@dataclass
class Segment:
    text: str
    speed: float | None = None
    pause_ms: int = 0


def parse_pause_tags(text: str) -> list[Segment]:
    segments: list[Segment] = []
    buffer = ""
    slow = False
    position = 0

    def flush(pause_ms: int = 0) -> None:
        nonlocal buffer
        if buffer.strip():
            segments.append(Segment(buffer, SLOW_SPEED if slow else None, pause_ms))
        elif pause_ms and segments:
            segments[-1].pause_ms = min(segments[-1].pause_ms + pause_ms, MAX_PAUSE_MS)
        buffer = ""

    for match in TAG_CANDIDATE.finditer(text):
        tag = match.group(0)
        pause = PAUSE_TAG.fullmatch(tag)
        opens_slow = tag == "[slow]" and not slow
        closes_slow = tag == "[/slow]" and slow
        if not (pause or opens_slow or closes_slow):
            warnings.warn(f"Malformed pacing tag left as text: {tag}")
            continue
        buffer += text[position:match.start()]
        position = match.end()
        if pause:
            flush(_pause_ms(pause))
        else:
            flush()
            slow = opens_slow
    buffer += text[position:]
    if slow:
        warnings.warn("[slow] is never closed; slowing down to the end of the text")
    flush()
    return segments


def _pause_ms(match: re.Match) -> int:
    amount, unit = match.groups()
    if amount is None:
        return DEFAULT_PAUSE_MS
    milliseconds = float(amount) * (1000 if unit == "s" else 1)
    return min(round(milliseconds), MAX_PAUSE_MS)
