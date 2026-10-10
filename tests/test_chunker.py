from toni.chunker import chunk_paragraphs, chunk_text


def test_chunk_paragraphs_flags_paragraph_ends():
    text = "One. Two.\n\nThree."
    assert chunk_paragraphs(text) == [("One. Two.", True), ("Three.", True)]


def test_chunk_paragraphs_flags_only_last_piece_of_long_paragraph():
    text = "Aaaa aaaa. Bbbb bbbb. Cccc cccc."
    flags = [ends for _, ends in chunk_paragraphs(text, max_chars=12)]
    assert flags == [False, False, True]


def test_chunk_text_unchanged():
    assert chunk_text("One.\n\nTwo.") == ["One.", "Two."]
