import zipfile
from pathlib import Path

import pytest

from toni import text_extractor
from toni.text_extractor import extract_text

CONTAINER = (
    '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<manifest>
<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
<item id="copy" href="copyright.xhtml" media-type="application/xhtml+xml"/>
<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="note" href="note.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine><itemref idref="cover"/><itemref idref="copy"/><itemref idref="nav"/>
<itemref idref="c1"/><itemref idref="note"/><itemref idref="c2"/></spine>
</package>"""
NAV = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol>
<li><a href="ch1.xhtml">The Beginning</a></li><li><a href="ch2.xhtml">Chapter Two</a></li>
</ol></nav></body></html>"""
BODY = "word " * 450


def page(body: str, epub_type: str = "") -> str:
    attribute = f' epub:type="{epub_type}"' if epub_type else ""
    return (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        f"<head><title>ignored</title></head><body{attribute}>{body}</body></html>"
    )


def build_epub(path: Path, extra: dict[str, bytes] | None = None) -> Path:
    files = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/content.opf": OPF.encode(),
        "OEBPS/nav.xhtml": NAV.encode(),
        "OEBPS/cover.xhtml": page("<p>Cover words</p>", "cover").encode(),
        "OEBPS/copyright.xhtml": page("<p>All rights reserved</p>", "copyright-page").encode(),
        "OEBPS/ch1.xhtml": page(f"<h1>Chapter One</h1><p>Café &amp; tea.</p><p>{BODY}</p>").encode(),
        "OEBPS/note.xhtml": page("<p>Short untagged note.</p>").encode(),
        "OEBPS/ch2.xhtml": page(f"<p>{BODY}</p>").encode(),
    }
    files.update(extra or {})
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def test_epub_follows_spine_and_drops_front_matter(tmp_path):
    text = extract_text(build_epub(tmp_path / "book.epub"))
    assert "Cover words" not in text
    assert "All rights reserved" not in text
    assert "Short untagged note" not in text
    assert text.startswith("Chapter One\n\nCafé & tea.")
    assert text.index("Chapter One") < text.index("Chapter Two")


def test_epub_titles_become_detectable_headings(tmp_path):
    from toni.audio_encoder import DEFAULT_CHAPTER_PATTERN
    import re

    text = extract_text(build_epub(tmp_path / "book.epub"))
    headings = [line for line in text.split("\n\n") if re.match(DEFAULT_CHAPTER_PATTERN, line)]
    assert headings == ["Chapter One", "Chapter Two"]


def test_epub_non_utf8_declared_encoding_is_decoded(tmp_path):
    chapter = page("<h1>Chapter One</h1><p>café</p>" + f"<p>{BODY}</p>")
    chapter = '<?xml version="1.0" encoding="ISO-8859-1"?>' + chapter
    epub = build_epub(tmp_path / "book.epub", {"OEBPS/ch1.xhtml": chapter.encode("latin-1")})
    assert "café" in extract_text(epub)


def test_epub_entry_cap_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(text_extractor, "MAX_ENTRY_BYTES", 1000)
    with pytest.raises(ValueError, match="exceeds"):
        extract_text(build_epub(tmp_path / "book.epub"))


def test_epub_total_cap_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(text_extractor, "MAX_TOTAL_BYTES", 1000)
    with pytest.raises(ValueError, match="expands"):
        extract_text(build_epub(tmp_path / "book.epub"))


def test_not_a_zip_is_rejected(tmp_path):
    bogus = tmp_path / "book.epub"
    bogus.write_text("nope")
    with pytest.raises(ValueError, match="Not a valid EPUB"):
        extract_text(bogus)
