import pytest

from toni.chunker import chunk_text
from toni.lexicon import apply_lexicon, load_lexicon


def test_load_skips_comment_lines_and_blank_lines(tmp_path):
    path = tmp_path / "lexicon.txt"
    path.write_text("# names\n\nGandalf = Gand-alf\n", encoding="utf-8")
    assert load_lexicon(path) == {"gandalf": "Gand-alf"}


def test_load_warns_about_unparseable_lines(tmp_path):
    path = tmp_path / "lexicon.txt"
    path.write_text("Gandalf = Gand-alf\nбезымянный\nBad =\n", encoding="utf-8")
    with pytest.warns(UserWarning) as caught:
        assert load_lexicon(path) == {"gandalf": "Gand-alf"}
    assert len(caught) == 2


def test_load_reads_a_byte_order_mark_and_keeps_a_hash_inside_a_term(tmp_path):
    path = tmp_path / "lexicon.txt"
    path.write_bytes("\ufeffC# = see sharp\n".encode("utf-8"))
    assert load_lexicon(path) == {"c#": "see sharp"}


def test_keys_and_lookups_agree_on_case_folding(tmp_path):
    path = tmp_path / "lexicon.txt"
    path.write_text("Straße = Shtrah-seh\nİstanbul = Is-tan-bool\n", encoding="utf-8")
    lexicon = load_lexicon(path)
    assert apply_lexicon("Die Straße und İstanbul.", lexicon) == "Die Shtrah-seh und Is-tan-bool."


def test_apply_lexicon_accepts_unnormalised_keys():
    assert apply_lexicon("Hello Zed", {"Zed": "zehd"}) == "Hello zehd"


def test_longest_term_wins():
    lexicon = {"new": "Noo", "new york": "Noo Yorrk"}
    assert apply_lexicon("New York", lexicon) == "Noo Yorrk"


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


@pytest.mark.parametrize(
    "key, text, expected",
    [
        ("ΟΔΟΣ", "ΟΔΟΣ", "odos"),
        ("οδος", "ΟΔΟΣ", "odos"),
        ("ΟΔΟΣ", "οδος", "odos"),
        ("STRASSE", "Straße", "odos"),
        ("Straße", "STRASSE", "odos"),
    ],
)
def test_keys_and_text_fold_identically(key, text, expected):
    assert apply_lexicon(text, {key: "odos"}) == expected
