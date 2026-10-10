import re
import statistics
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

CHAR_SCRIPTS = re.compile(r"[฀-๿぀-ヿ㐀-䶿一-鿿豈-﫿]")
DEFAULT_WEIGHT_PER_SECOND = 20.0
MIN_CHECKED_SECONDS = 4.0
MIN_CALIBRATION_SAMPLES = 5


@dataclass
class Thresholds:
    wer: float = 0.25
    ratio_min: float = 0.6
    ratio_max: float = 1.6


def normalise(text: str) -> list[str]:
    text = "".join(" " if unicodedata.category(c) == "Pd" else c for c in text.lower().replace("+", ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if unicodedata.category(c)[0] not in "MPS")
    return list(text.replace(" ", "")) if CHAR_SCRIPTS.search(text) else text.split()


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = normalise(reference), normalise(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


@lru_cache(maxsize=None)
def _weigh():
    try:
        from omnivoice.utils.duration import RuleDurationEstimator
    except ImportError:
        return lambda text: float(len(text))
    return RuleDurationEstimator().calculate_total_weight


def expected_seconds(
    text: str,
    ref_text: str | None = None,
    ref_seconds: float | None = None,
    speed: float = 1.0,
) -> float:
    rate = (
        _weigh()(ref_text) / ref_seconds
        if ref_text and ref_seconds
        else DEFAULT_WEIGHT_PER_SECOND
    )
    return _weigh()(text) / rate / speed


def calibration_median(ratios: list[float]) -> float | None:
    return statistics.median(ratios) if len(ratios) >= MIN_CALIBRATION_SAMPLES else None


def verdict(
    wer: float, ratio: float, expected: float, t: Thresholds, median: float | None = None
) -> str:
    # OmniVoice stretches estimates under ~50 tokens, so short chunks always read long
    judged = ratio / median if median else ratio
    duration_ok = expected < MIN_CHECKED_SECONDS or t.ratio_min <= judged <= t.ratio_max
    return "pass" if wer <= t.wer and duration_ok else "fail"
