import pytest

from toni.chunker import chunk_text
from toni.text_normalization import normalize_speech_text


@pytest.mark.parametrize(
    "text, language, expected",
    [
        ("It was 1812.", "en", ["It was eighteen twelve."]),
        ("She has 25 apples.", "en", ["She has twenty-five apples."]),
        ("Dr. Smith arrived.", "en", ["Doctor Smith arrived."]),
        ("Dr. smith arrived.", "en", ["Dr. smith arrived."]),
        ("Pi is 3.14.", "en", ["Pi is three point one four."]),
        ("Взял 25 яблок.", "ru", ["Взял двадцать пять яблок."]),
        ("В 1812 году.", "ru", ["В одна тысяча восемьсот двенадцать году."]),
        ("Проф. Иванов пришел.", "ru", ["Профессор Иванов пришел."]),
        ("Вышло 3,14 раза.", "ru", ["Вышло три целых четырнадцать сотых раза."]),
        ("Wait!!!!!!", "en", ["Wait!!!"]),
    ],
)
def test_chunk_text_speaks_numbers_and_abbreviations(text, language, expected):
    assert chunk_text(text, language=language) == expected


@pytest.mark.parametrize("text", ["1,000 units", "ID A12 and 12B", "code 007", "section 1.2.3", "5-6 or 12:30"])
def test_ambiguous_tokens_are_left_alone(text):
    assert normalize_speech_text(text, "en") == text


def test_control_characters_are_stripped():
    assert normalize_speech_text("a\x00b\x07c\nd", "en") == "abc\nd"


@pytest.mark.parametrize("language", ["en", "ru", None, "fr"])
def test_normalisation_is_idempotent(language):
    text = "In 1812, Dr. Smith had 25 apples and 3.14 pi!!!!! Проф. Иванов, 3,14."
    once = normalize_speech_text(text, language)
    assert normalize_speech_text(once, language) == once


def test_unsupported_language_only_cleans_punctuation():
    assert normalize_speech_text("Il a 25 ans!!!!!", "fr") == "Il a 25 ans!!!"


def test_normalisation_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TONI_NORMALIZE", "0")
    assert chunk_text("It was 1812.", language="en") == ["It was 1812."]


@pytest.mark.parametrize(
    "text",
    [
        "1-й раз", "до 25-го числа", "в 1990-х годах", "в 2-х томах", "5-летний мальчик",
        "2 000 рублей", "1 000 000 человек", "1 000 рублей", "1 000 рублей",
    ],
)
def test_russian_suffixed_numbers_and_spaced_thousands_are_left_alone(text):
    assert normalize_speech_text(text, "ru") == text


def test_english_hyphenated_numbers_are_still_spoken():
    assert normalize_speech_text("a 5-year-old", "en") == "a five-year-old"


@pytest.mark.parametrize(
    "text", ["$5", "£300", "€20 and ¥5", "50%", "10.5%", "a 1.0 version", "call 555 1234", "2 000 rubles"]
)
def test_numbers_the_tts_normaliser_owns_are_left_alone(text):
    assert normalize_speech_text(text, "en") == text


def test_plain_numbers_separated_by_a_space_are_still_spoken():
    assert normalize_speech_text("5 apples and 7 pears", "en") == "five apples and seven pears"


def test_russian_pronoun_im_is_not_expanded():
    assert normalize_speech_text("Я позвонил им. Они ответили.", "ru") == "Я позвонил им. Они ответили."
