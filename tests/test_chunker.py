import pytest

from toni.chunker import chunk_text, split_into_sentences


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Mr. Smith left. Then he came back.", ["Mr. Smith left.", "Then he came back."]),
        ("Dr. Who met Prof. Plum at 5 p.m. Then they ate.", ["Dr. Who met Prof. Plum at 5 p.m. Then they ate."]),
        ("Он ушел, т. е. сбежал. Потом вернулся.", ["Он ушел, т. е. сбежал.", "Потом вернулся."]),
        ("Это было в 1812 г. Наполеон вошел в город.", ["Это было в 1812 г. Наполеон вошел в город."]),
        ("J. R. R. Tolkien wrote it. Then he left.", ["J. R. R. Tolkien wrote it.", "Then he left."]),
        ("Vol. II is out. Read it.", ["Vol. II is out.", "Read it."]),
        ("Я позвонил им. Они ответили.", ["Я позвонил им.", "Они ответили."]),
        ("Книги, журналы и др. Потом он ушел.", ["Книги, журналы и др.", "Потом он ушел."]),
        ("Pi is 3.14 roughly. Next point.", ["Pi is 3.14 roughly.", "Next point."]),
    ],
)
def test_split_into_sentences_respects_abbreviations(text, expected):
    assert split_into_sentences(text) == expected


def test_punctuation_only_paragraph_merges_into_previous_chunk():
    assert chunk_text("Hello there.\n\n…\n\nNext one.") == ["Hello there. …", "Next one."]


def test_leading_punctuation_only_paragraph_merges_into_next_chunk():
    assert chunk_text("—\n\nHello there.") == ["— Hello there."]


def test_pieces_cut_from_long_paragraph_end_with_punctuation():
    text = " ".join(["word"] * 40)
    chunks = chunk_text(text, max_chars=60)
    assert len(chunks) > 1
    assert all(chunk.endswith(".") for chunk in chunks)
    assert all(len(chunk) <= 61 for chunk in chunks)


def test_clause_cut_keeps_its_clause_mark():
    text = "alpha beta gamma, delta epsilon zeta, eta theta iota"
    chunks = chunk_text(text, max_chars=30)
    assert chunks[0].endswith(",")


def test_decimal_comma_is_not_a_clause_boundary():
    chunks = chunk_text("aaaa 3,14 bbbb", max_chars=10)
    assert not any(chunk.endswith(",") for chunk in chunks)
    assert any("3,14" in chunk for chunk in chunks)


def test_short_heading_is_left_alone():
    assert chunk_text("CHAPTER 1\n\nIt began.") == ["CHAPTER 1", "It began."]
