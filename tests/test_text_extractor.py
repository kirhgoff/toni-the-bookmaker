import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from toni import text_extractor
from toni.text_extractor import epub_cover, extract_epub, extract_text

CONTAINER = (
    '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<manifest>
<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
<item id="ded" href="dedication.xhtml" media-type="application/xhtml+xml"/>
<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
<item id="copy" href="copyright.xhtml" media-type="application/xhtml+xml"/>
<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="note" href="note.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine><itemref idref="ded"/><itemref idref="cover"/><itemref idref="copy"/><itemref idref="nav"/>
<itemref idref="c1"/><itemref idref="note"/><itemref idref="c2"/></spine>
</package>"""
NAV = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol>
<li><a href="copyright.xhtml">Copyright</a></li><li><a href="ch1.xhtml">The Beginning</a></li><li><a href="ch2.xhtml">Chapter Two</a></li>
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
        "OEBPS/dedication.xhtml": page("<p>For my mother.</p>").encode(),
        "OEBPS/cover.xhtml": page("<p>Cover words</p>", "cover").encode(),
        "OEBPS/copyright.xhtml": page(f"<p>All rights reserved</p><p>{BODY}</p>", "copyright-page").encode(),
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
    assert "For my mother" not in text
    assert "Short untagged note" in text
    assert text.startswith("Chapter One\n\nCafé & tea.")
    assert text.index("Chapter One") < text.index("Chapter Two")


def test_epub_titles_are_listed_and_narrated_bare(tmp_path):
    text, titles = extract_epub(build_epub(tmp_path / "book.epub"))
    assert titles == ["Chapter One", "Chapter Two"]
    assert text.split("\n\n")[0] == "Chapter One"
    assert "\n\nChapter Two\n\n" in text


def test_epub_titles_are_not_prefixed_or_translated(tmp_path):
    nav = NAV.replace("The Beginning", "3. The Flood").replace("Chapter Two", "Потоп")
    epub = build_epub(tmp_path / "book.epub", {"OEBPS/nav.xhtml": nav.encode()})
    text, titles = extract_epub(epub)
    assert titles == ["Chapter One", "Потоп"]
    assert "Chapter 2." not in text and "Глава" not in text


def test_epub_toc_title_is_kept_verbatim(tmp_path):
    nav = NAV.replace("The Beginning", "3. The Flood")
    chapter = page(f"<p>{BODY}</p>")
    epub = build_epub(tmp_path / "book.epub", {"OEBPS/nav.xhtml": nav.encode(), "OEBPS/ch1.xhtml": chapter.encode()})
    text, titles = extract_epub(epub)
    assert titles[0] == "3. The Flood"
    assert text.startswith("3. The Flood\n\n")


def test_epub3_landmarks_drop_toc_listed_front_matter(tmp_path):
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>'
        '<nav epub:type="toc"><ol><li><a href="cover.xhtml">Cover</a></li>'
        '<li><a href="copyright.xhtml">Copyright</a></li><li><a href="contents.xhtml">Contents</a></li>'
        '<li><a href="ch1.xhtml">The Beginning</a></li></ol></nav>'
        '<nav epub:type="landmarks"><ol><li><a epub:type="cover" href="cover.xhtml">Cover</a></li>'
        '<li><a epub:type="copyright-page" href="copyright.xhtml">Copyright</a></li>'
        '<li><a epub:type="toc" href="contents.xhtml">Contents</a></li></ol></nav></body></html>'
    )
    opf = OPF.replace(
        '<item id="note"',
        '<item id="contents" href="contents.xhtml" media-type="application/xhtml+xml"/><item id="note"',
    ).replace('<itemref idref="nav"/>', '<itemref idref="contents"/>')
    epub = build_epub(
        tmp_path / "book.epub",
        {
            "OEBPS/nav.xhtml": nav.encode(),
            "OEBPS/content.opf": opf.encode(),
            "OEBPS/cover.xhtml": page(f"<p>Cover words</p><p>{BODY}</p>").encode(),
            "OEBPS/copyright.xhtml": page(f"<p>All rights reserved</p><p>{BODY}</p>").encode(),
            "OEBPS/contents.xhtml": page(f"<p>Table of contents</p><p>{BODY}</p>").encode(),
        },
    )
    text = extract_text(epub)
    assert "Cover words" not in text
    assert "All rights reserved" not in text
    assert "Table of contents" not in text
    assert "Chapter One" in text


def test_epub2_guide_drops_toc_listed_front_matter(tmp_path):
    opf = OPF.replace("</package>", '<guide><reference type="copyright-page" href="legal.xhtml"/></guide></package>')
    opf = opf.replace('<item id="note"', '<item id="legal" href="legal.xhtml" media-type="application/xhtml+xml"/><item id="note"')
    opf = opf.replace('<itemref idref="nav"/>', '<itemref idref="legal"/>')
    nav = NAV.replace("</ol>", '<li><a href="legal.xhtml">Legal</a></li></ol>')
    epub = build_epub(
        tmp_path / "book.epub",
        {
            "OEBPS/content.opf": opf.encode(),
            "OEBPS/nav.xhtml": nav.encode(),
            "OEBPS/legal.xhtml": page(f"<p>Legal words</p><p>{BODY}</p>").encode(),
        },
    )
    assert "Legal words" not in extract_text(epub)


def test_epub_keeps_short_spine_items_after_the_first_toc_entry(tmp_path):
    text = extract_text(build_epub(tmp_path / "book.epub"))
    assert text.index("Short untagged note") > text.index("Chapter One")


def test_epub_nav_with_html_entities_parses(tmp_path):
    nav = NAV.replace("The Beginning", "The&nbsp;Beginning &amp; More")
    chapter = page(f"<p>{BODY}</p>")
    epub = build_epub(tmp_path / "book.epub", {"OEBPS/nav.xhtml": nav.encode(), "OEBPS/ch1.xhtml": chapter.encode()})
    assert extract_epub(epub)[1][0] == "The Beginning & More"


def test_epub_spine_item_missing_from_archive_is_skipped(tmp_path, capsys):
    epub = build_epub(tmp_path / "book.epub")
    stripped = tmp_path / "stripped.epub"
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(stripped, "w") as target:
        for info in source.infolist():
            if info.filename != "OEBPS/note.xhtml":
                target.writestr(info.filename, source.read(info.filename))
    assert "Chapter Two" in extract_text(stripped)
    assert "note.xhtml" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["META-INF/container.xml", "OEBPS/content.opf"])
def test_epub_without_container_or_package_is_a_clear_error(tmp_path, missing):
    epub = build_epub(tmp_path / "book.epub")
    stripped = tmp_path / "stripped.epub"
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(stripped, "w") as target:
        for info in source.infolist():
            if info.filename != missing:
                target.writestr(info.filename, source.read(info.filename))
    with pytest.raises(ValueError, match="not a valid EPUB"):
        extract_text(stripped)


def test_cli_writes_chapter_titles_sidecar(tmp_path):
    epub = build_epub(tmp_path / "book.epub")
    out = tmp_path / "source.txt"
    subprocess.run([sys.executable, "-m", "toni.text_extractor", str(epub), "-o", str(out)], check=True)
    assert (tmp_path / "source.txt.chapters.txt").read_text(encoding="utf-8").splitlines() == [
        "Chapter One",
        "Chapter Two",
    ]


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


PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"


def with_cover(tmp_path, opf_item: str, opf_meta: str = ""):
    opf = OPF.replace("<manifest>", f"<metadata>{opf_meta}</metadata><manifest>{opf_item}")
    return build_epub(tmp_path / "book.epub", {"OEBPS/content.opf": opf.encode(), "OEBPS/images/art.png": PNG_BYTES})


def test_epub3_cover_image_is_extracted(tmp_path):
    epub = with_cover(tmp_path, '<item id="img" href="images/art.png" properties="cover-image" media-type="image/png"/>')
    assert epub_cover(epub) == (".png", PNG_BYTES)


def test_epub2_meta_cover_is_extracted(tmp_path):
    epub = with_cover(
        tmp_path,
        '<item id="img" href="images/art.png" media-type="image/png"/>',
        '<meta name="cover" content="img"/>',
    )
    assert epub_cover(epub) == (".png", PNG_BYTES)


def test_epub_without_a_cover_declaration_has_no_cover(tmp_path):
    assert epub_cover(build_epub(tmp_path / "book.epub")) is None


def run_extractor(epub, out, *extra):
    subprocess.run([sys.executable, "-m", "toni.text_extractor", str(epub), "-o", str(out), *extra], check=True)


def test_cli_saves_the_epub_cover_only_when_the_book_folder_has_none(tmp_path):
    epub = with_cover(tmp_path, '<item id="img" href="images/art.png" properties="cover-image" media-type="image/png"/>')
    book = tmp_path / "library"
    book.mkdir()
    run_extractor(epub, book / "source.txt", "--cover-dir", str(book))
    assert (book / "cover.png").read_bytes() == PNG_BYTES
    (book / "cover.png").write_bytes(b"mine")
    run_extractor(epub, book / "source.txt", "--cover-dir", str(book))
    assert (book / "cover.png").read_bytes() == b"mine"
