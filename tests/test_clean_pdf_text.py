from toni.clean_pdf_text import clean

FIXTURE = [
    "                              II",
    "",
    "   It began quietly, and the villagers gathered near the compen-",
    "sated old machine, watching it hum and turn.",
    "It ran for hours without pause or complaint at all.",
    "",
    "\x0cThen somebody noticed a strange noise in the walls.",
    " " * 35 + "47",
    "The room grew quiet as the evening wore on," + " " * 8 + "112 and nobody dared to speak.",
    "Nobody moved until the lights came back on again.",
    "",
    "   The council met again to discuss the re­",
    "build of the old mill by the river.",
    "Everyone agreed it was worth the effort.",
]

EXPECTED_TEXT = (
    "Chapter 1.\n\n"
    "It began quietly, and the villagers gathered near the compensated old machine, "
    "watching it hum and turn. It ran for hours without pause or complaint at all. "
    "Then somebody noticed a strange noise in the walls. "
    "The room grew quiet as the evening wore on, and nobody dared to speak. "
    "Nobody moved until the lights came back on again.\n\n"
    "The council met again to discuss the rebuild of the old mill by the river. "
    "Everyone agreed it was worth the effort.\n"
)


def test_clean_headings_hyphenation_and_page_numbers():
    text, headings = clean(FIXTURE)
    assert headings == [(1, "II")]
    assert text == EXPECTED_TEXT
