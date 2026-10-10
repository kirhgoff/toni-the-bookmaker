"""Text extraction from PDF, EPUB and text files."""

import argparse
import html
import posixpath
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree


def extract_text(file_path: Path) -> str:
    """Extract text from a file based on its extension.

    Args:
        file_path: Path to the input file (PDF or text).

    Returns:
        Extracted text content.

    Raises:
        ValueError: If the file format is not supported.
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return extract_from_pdf(file_path)
    elif suffix == ".epub":
        return extract_from_epub(file_path)
    elif suffix in (".txt", ".text", ".md", ".markdown"):
        return extract_from_text(file_path)
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            "Supported formats: .pdf, .epub, .txt, .text, .md"
        )


def extract_from_pdf(file_path: Path) -> str:
    """Extract text from a PDF file using PyMuPDF.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text content with page breaks preserved.
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("pymupdf is not installed. Install it with: uv sync")

    text_parts = []

    with fitz.open(file_path) as doc:
        for page_num, page in enumerate(doc):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def extract_from_text(file_path: Path) -> str:
    """Extract text from a plain text file.

    Args:
        file_path: Path to the text file.

    Returns:
        File content as string.
    """
    return file_path.read_text(encoding="utf-8")


MAX_ENTRY_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_UNTAGGED_FRONT_MATTER_WORDS = 400
FRONT_MATTER_TYPES = {"cover", "copyright-page", "toc", "titlepage"}
XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "blockquote", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
HEADING_TAGS = {"h1", "h2", "h3"}
SKIPPED_TAGS = {"script", "style", "head"}
CONTAINER_PATH = "META-INF/container.xml"


class _TextBlocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.epub_types: set[str] = set()
        self._parts: list[str] = []
        self._block_tag = "p"
        self._skip_depth = 0

    def _flush(self) -> None:
        text = " ".join("".join(self._parts).split())
        if text:
            self.blocks.append((self._block_tag, text))
        self._parts = []
        self._block_tag = "p"

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        if tag in ("body", "section"):
            self.epub_types.update((dict(attrs).get("epub:type") or "").split())
        if tag in BLOCK_TAGS:
            self._flush()
            self._block_tag = tag

    def handle_endtag(self, tag):
        if tag in SKIPPED_TAGS:
            self._skip_depth = max(self._skip_depth - 1, 0)
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def close(self):
        super().close()
        self._flush()


def _decode_markup(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    declared = re.search(rb"""(?:encoding|charset)\s*=\s*["']?([\w-]+)""", data[:1024])
    encoding = declared.group(1).decode("ascii") if declared else "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_entry(archive: zipfile.ZipFile, name: str) -> bytes:
    if name not in archive.namelist():
        raise ValueError(f"not a valid EPUB: {name} is missing")
    with archive.open(name) as entry:
        data = entry.read(MAX_ENTRY_BYTES + 1)
    if len(data) > MAX_ENTRY_BYTES:
        raise ValueError(f"EPUB entry {name} exceeds {MAX_ENTRY_BYTES // 2**20} MB")
    return data


def _check_archive_size(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if any(info.file_size > MAX_ENTRY_BYTES for info in infos):
        raise ValueError(f"EPUB entry exceeds {MAX_ENTRY_BYTES // 2**20} MB")
    if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
        raise ValueError(f"EPUB expands beyond {MAX_TOTAL_BYTES // 2**20} MB")


def _resolve(base_dir: str, href: str) -> str:
    return posixpath.normpath(posixpath.join(base_dir, unquote(href.split("#")[0])))


def _parse_markup(archive: zipfile.ZipFile, name: str):
    markup = _decode_markup(_read_entry(archive, name))
    markup = re.sub(
        r"&([A-Za-z][A-Za-z0-9]*);",
        lambda m: m.group(0) if m.group(1) in XML_ENTITIES else (
            "" if html.unescape(m.group(0)) == m.group(0) else html.unescape(m.group(0))
        ),
        markup,
    )
    return ElementTree.fromstring(markup)


def _epub_types(element) -> set[str]:
    return {
        token
        for key, value in element.attrib.items()
        if _local(key) == "type"
        for token in value.split()
    }


def _link_text(link) -> str:
    return " ".join("".join(link.itertext()).split())


def _navigation(archive: zipfile.ZipFile, items: dict, spine_toc_id) -> tuple[dict[str, str], set[str]]:
    titles: dict[str, str] = {}
    front_matter: set[str] = set()
    nav = next((i for i in items.values() if "nav" in i["properties"]), None)
    ncx = items.get(spine_toc_id) if spine_toc_id else None
    if nav:
        front_matter.add(nav["path"])
        base = posixpath.dirname(nav["path"])
        for element in _parse_markup(archive, nav["path"]).iter():
            if _local(element.tag) != "nav":
                continue
            kinds = _epub_types(element)
            for link in element.iter():
                if _local(link.tag) != "a" or not link.get("href"):
                    continue
                target = _resolve(base, link.get("href"))
                if "toc" in kinds:
                    titles.setdefault(target, _link_text(link))
                if "landmarks" in kinds and _epub_types(link) & FRONT_MATTER_TYPES:
                    front_matter.add(target)
    elif ncx:
        base = posixpath.dirname(ncx["path"])
        for point in _parse_markup(archive, ncx["path"]).iter():
            if _local(point.tag) != "navPoint":
                continue
            label = next((e for e in point.iter() if _local(e.tag) == "text"), None)
            content = next((e for e in point.iter() if _local(e.tag) == "content"), None)
            if label is not None and content is not None and content.get("src"):
                titles.setdefault(_resolve(base, content.get("src")), _link_text(label))
    return titles, front_matter


def _guide_front_matter(root, opf_dir: str) -> set[str]:
    return {
        _resolve(opf_dir, reference.get("href"))
        for reference in root.iter()
        if _local(reference.tag) == "reference"
        and reference.get("href")
        and reference.get("type") in FRONT_MATTER_TYPES
    }


def extract_epub(file_path: Path) -> tuple[str, list[str]]:
    """Narratable text in spine order, plus the section titles in reading order."""
    try:
        archive = zipfile.ZipFile(file_path)
    except zipfile.BadZipFile as error:
        raise ValueError(f"Not a valid EPUB: {file_path}") from error

    with archive:
        _check_archive_size(archive)
        container = ElementTree.fromstring(_read_entry(archive, CONTAINER_PATH))
        rootfile = next((e for e in container.iter() if _local(e.tag) == "rootfile"), None)
        if rootfile is None or not rootfile.get("full-path"):
            raise ValueError("not a valid EPUB: container.xml names no package file")
        opf_path = rootfile.get("full-path")
        opf_dir = posixpath.dirname(opf_path)
        opf = ElementTree.fromstring(_read_entry(archive, opf_path))

        items = {
            e.get("id"): {
                "path": _resolve(opf_dir, e.get("href")),
                "properties": (e.get("properties") or "").split(),
            }
            for e in opf.iter()
            if _local(e.tag) == "item" and e.get("href")
        }
        spine = next(e for e in opf.iter() if _local(e.tag) == "spine")
        spine_paths = [
            items[ref.get("idref")]["path"]
            for ref in spine
            if _local(ref.tag) == "itemref" and ref.get("idref") in items
        ]
        titles, landmark_skipped = _navigation(archive, items, spine.get("toc"))
        skipped = landmark_skipped | _guide_front_matter(opf, opf_dir)
        first_listed = next((i for i, path in enumerate(spine_paths) if path in titles), len(spine_paths))
        present = set(archive.namelist())

        sections: list[str] = []
        section_titles: list[str] = []
        for index, path in enumerate(spine_paths):
            if path not in present:
                print(f"warning: spine item {path} is missing from the EPUB, skipped", file=sys.stderr)
                continue
            parser = _TextBlocks()
            parser.feed(_decode_markup(_read_entry(archive, path)))
            parser.close()
            blocks = parser.blocks
            if path in skipped or parser.epub_types & FRONT_MATTER_TYPES:
                continue
            words = sum(len(text.split()) for _, text in blocks)
            if index < first_listed and titles and words <= MAX_UNTAGGED_FRONT_MATTER_WORDS:
                continue
            if not blocks:
                continue
            if blocks[0][0] in HEADING_TAGS:
                title = blocks[0][1]
                blocks = blocks[1:]
            else:
                title = titles.get(path, "")
            lines = [text for _, text in blocks]
            if title:
                section_titles.append(title)
                lines.insert(0, title)
            sections.append("\n\n".join(lines))

    return "\n\n".join(sections), section_titles


def extract_from_epub(file_path: Path) -> str:
    return extract_epub(file_path)[0]


def chapter_titles_path(text_path: Path) -> Path:
    return text_path.with_name(text_path.name + ".chapters.txt")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract narratable text from a book file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.suffix.lower() == ".epub":
        text, titles = extract_epub(args.input)
        if titles:
            chapter_titles_path(args.output).write_text("\n".join(titles) + "\n", encoding="utf-8")
    else:
        text = extract_text(args.input)
    args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
