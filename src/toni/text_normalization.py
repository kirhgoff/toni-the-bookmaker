"""Conservative, idempotent text normalisation applied before chunking."""

import os
import re

from num2words import num2words

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PUNCTUATION_RUN = re.compile(r"([^\w\s])\1{3,}")
MAX_DIGITS = 9

ABBREVIATIONS = {
    "en": {
        "mr": "Mister", "mrs": "Missus", "ms": "Miss", "dr": "Doctor",
        "prof": "Professor", "capt": "Captain", "col": "Colonel",
        "gen": "General", "lt": "Lieutenant", "sgt": "Sergeant",
    },
    "ru": {
        "ул": "улица", "им": "имени", "проф": "профессор",
        "акад": "академик", "тов": "товарищ",
    },
}
DECIMAL_SEPARATOR = {"en": ".", "ru": ","}
GROUP_SEPARATOR = r"[ \u00a0\u202f]"
NUMBER_START = (
    r"(?<![\w.,:/\-$€£¥])"
    rf"(?<!\d{{3}}{GROUP_SEPARATOR})"
    rf"(?!(?<=\d{GROUP_SEPARATOR})\d{{3}}(?!\d))"
)
NUMBER_END = (
    r"(?!\w|%|[.,:/\-]\d)"
    rf"(?!(?<=\d{{3}}){GROUP_SEPARATOR}\d)"
    rf"(?!{GROUP_SEPARATOR}\d{{3}}(?!\d))"
)
SUFFIXED_NUMBER_END = {"ru": r"(?!-[^\W\d_])"}


def normalization_enabled() -> bool:
    return os.environ.get("TONI_NORMALIZE", "1") != "0"


def base_language(language: str | None) -> str | None:
    return language.lower().split("-")[0].split("_")[0] if language else None


def normalize_speech_text(text: str, language: str | None) -> str:
    lang = base_language(language)
    text = CONTROL_CHARS.sub("", text)
    text = PUNCTUATION_RUN.sub(lambda m: m.group(1) * 3, text)
    if lang in ABBREVIATIONS:
        text = _expand_abbreviations(text, ABBREVIATIONS[lang])
        text = _expand_decimals(text, lang)
        text = _expand_numbers(text, lang)
    return text


def _number_pattern(body: str, lang: str) -> re.Pattern:
    return re.compile(f"{NUMBER_START}{body}{NUMBER_END}{SUFFIXED_NUMBER_END.get(lang, '')}")


def _has_leading_zero(digits: str) -> bool:
    return len(digits) > 1 and digits.startswith("0")


def _expand_abbreviations(text: str, table: dict[str, str]) -> str:
    words = "|".join(re.escape(word) for word in table)
    pattern = re.compile(rf"(?<!\w)((?i:{words}))\.(?=\s+[A-ZА-ЯЁ])")

    def expand(match: re.Match) -> str:
        word = match.group(1)
        full = table[word.lower()]
        return (full[0].upper() if word[0].isupper() else full[0].lower()) + full[1:]

    return pattern.sub(expand, text)


def _expand_decimals(text: str, lang: str) -> str:
    separator = re.escape(DECIMAL_SEPARATOR[lang])
    pattern = _number_pattern(rf"(\d{{1,{MAX_DIGITS}}}){separator}(\d{{1,4}})", lang)

    def expand(match: re.Match) -> str:
        whole, fraction = match.groups()
        if _has_leading_zero(whole) or not fraction.strip("0"):
            return match.group(0)
        return num2words(float(f"{whole}.{fraction}"), lang=lang)

    return pattern.sub(expand, text)


def _expand_numbers(text: str, lang: str) -> str:
    if lang == "en":
        year = _number_pattern(r"(1[5-9]\d\d|20\d\d)", lang)
        text = year.sub(lambda m: num2words(int(m.group(1)), to="year"), text)

    def expand(match: re.Match) -> str:
        digits = match.group(1)
        return match.group(0) if _has_leading_zero(digits) else num2words(int(digits), lang=lang)

    return _number_pattern(rf"(\d{{1,{MAX_DIGITS}}})", lang).sub(expand, text)
