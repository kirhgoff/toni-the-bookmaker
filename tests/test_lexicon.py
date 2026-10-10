from toni.chunker import chunk_text
from toni.lexicon import apply_lexicon, load_lexicon


def test_load_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "lexicon.txt"
    path.write_text("# names\n\nGandalf = Gand-alf  # wizard\nбезымянный\nBad =\n", encoding="utf-8")
    assert load_lexicon(path) == {"gandalf": "Gand-alf"}


def test_longest_term_wins():
    lexicon = {"york": "Yorrk", "new york": "Noo Yorrk"}
    assert apply_lexicon("I love New York and York.", lexicon) == "I love Noo Yorrk and Yorrk."


def test_replacements_are_not_reapplied():
    assert apply_lexicon("ab", {"ab": "ba", "ba": "xx"}) == "ba"


def test_matching_is_case_insensitive_on_word_boundaries():
    assert apply_lexicon("Zed, zedge", {"zed": "zehd"}) == "zehd, zedge"


def test_cyrillic_boundaries_and_stress_marks():
    lexicon = {"аня": "Ан+я"}
    assert apply_lexicon("Аня и баня, Анята", lexicon) == "Ан+я и баня, Анята"


def test_chunk_text_applies_lexicon_after_normalisation():
    chunks = chunk_text("Dr. Gandalf has 3 rings.", language="en", lexicon={"gandalf": "Gand-alf"})
    assert chunks == ["Doctor Gand-alf has three rings."]
