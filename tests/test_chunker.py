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
        ("So did I. Then we left.", ["So did I.", "Then we left."]),
        ("The answer was no. She left.", ["The answer was no.", "She left."]),
        ("Take vitamin C. Next day.", ["Take vitamin C.", "Next day."]),
        ("— Кто? — Я. Потом ушёл.", ["— Кто? — Я.", "Потом ушёл."]),
        ("Plan B. Then.", ["Plan B.", "Then."]),
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
    assert chunks[-1].endswith(".")
    assert all(len(chunk) <= 61 for chunk in chunks)


def test_clause_cut_keeps_its_clause_mark():
    text = "alpha beta gamma, delta epsilon zeta, eta theta iota"
    chunks = chunk_text(text, max_chars=30)
    assert chunks[0].endswith(",")


def test_decimal_comma_is_not_a_clause_boundary():
    chunks = chunk_text("aaaa 3,14 bbbb", max_chars=10)
    assert any("3,14" in chunk for chunk in chunks)


def test_short_heading_is_left_alone():
    assert chunk_text("CHAPTER 1\n\nIt began.") == ["CHAPTER 1", "It began."]


def test_word_boundary_cuts_end_with_a_clause_mark_and_the_last_piece_with_a_full_stop():
    chunks = chunk_text(" ".join(["word"] * 40), max_chars=60)
    assert all(chunk.endswith(",") for chunk in chunks[:-1])


def test_sentence_boundary_pieces_keep_the_full_stop():
    chunks = chunk_text(" ".join(["One two three four."] * 6), max_chars=45)
    assert len(chunks) > 1
    assert all(chunk.endswith(".") for chunk in chunks)


def test_unspeakable_chunk_merges_into_the_next_when_the_previous_is_full():
    assert chunk_text("Hello there.\n\n—\n\nNext one.", max_chars=13) == ["Hello there.", "— Next one."]


def test_chunks_keep_their_pre_normalisation_text_for_chapter_detection():
    from toni.chunker import chunk_with_marks

    chunks = chunk_with_marks("Глава 12\n\nАня взяла 3 яблока.", language="ru", lexicon={"аня": "Ан+я"})
    assert [(c.raw_text, c.text) for c in chunks] == [
        ("Глава 12", "Глава двенадцать"),
        ("Аня взяла 3 яблока.", "Ан+я взяла три яблока."),
    ]


@pytest.mark.parametrize(
    "separator, heading, pattern",
    [("* * *", "CHAPTER 2", r"^\s*CHAPTER"), ("* * *", "Глава 14", r"^Глава \d+")],
)
def test_scene_break_carried_into_the_next_chunk_keeps_its_heading_detectable(separator, heading, pattern):
    import re

    from toni.chunker import chunk_with_marks

    filler = "x" * 30
    chunks = chunk_with_marks(f"{filler}\n\n{separator}\n\n{heading}", max_chars=len(filler))
    assert [c.raw_text for c in chunks] == [filler, heading]
    assert chunks[1].text == f"{separator} {heading}"
    assert re.match(pattern, chunks[1].raw_text)
