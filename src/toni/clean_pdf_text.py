"""Turn `pdftotext -layout` output of a scanned book into narratable paragraphs."""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_HEADING = r"[IVXLC]+"
CENTERED_INDENT = 10
GLUED_PAGE_NUMBER = re.compile(r" {5,}\d{1,3}(?= |$)")
LEADING_PAGE_NUMBER = re.compile(r"^\d{2,3} (?=[a-z])")


def paragraph_indent(lines: list[str]) -> int:
    indents = Counter(len(line) - len(line.lstrip(" ")) for line in lines if line.strip())
    return indents.most_common(1)[0][0] + 2 if indents else 2


def clean(
    lines: list[str], heading: str = DEFAULT_HEADING, indent: int | None = None
) -> tuple[str, list[tuple[int, str]]]:
    heading_re = re.compile(heading)
    indent = paragraph_indent(lines) if indent is None else indent
    paragraphs: list[str] = []
    headings: list[tuple[int, str]] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            paragraphs.append(re.sub(r" {2,}", " ", " ".join(current)))
            current.clear()

    for number, raw in enumerate(lines, 1):
        line = raw.replace("\f", "").replace("­", "-")
        line = line.rstrip()
        text = line.strip()
        if not text:
            continue
        lead = len(line) - len(line.lstrip(" "))
        if heading_re.fullmatch(text):
            flush()
            headings.append((number, text))
            paragraphs.append(f"Chapter {len(headings)}.")
            continue
        if lead >= CENTERED_INDENT and len(text) <= 4:
            continue
        text = LEADING_PAGE_NUMBER.sub("", GLUED_PAGE_NUMBER.sub("", text))
        if lead >= indent:
            flush()
        if current and current[-1].endswith("-") and text[:1].islower():
            current[-1] = current[-1][:-1] + text
        else:
            current.append(text)
    flush()
    return "\n\n".join(paragraphs) + "\n", headings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="pdftotext -layout output, UTF-8")
    parser.add_argument("-o", "--output", type=Path, help="default: stdout")
    parser.add_argument("--from", dest="from_line", type=int, default=1, help="first line to keep (1-based)")
    parser.add_argument("--to", dest="to_line", type=int, help="last line to keep (inclusive)")
    parser.add_argument("--heading", default=DEFAULT_HEADING, help="regex a whole heading line must match")
    parser.add_argument("--indent", type=int, help="min leading spaces of a paragraph's first line (default: most common indent + 2)")
    args = parser.parse_args()

    lines = args.input.read_text(encoding="utf-8").splitlines()[args.from_line - 1 : args.to_line]
    text, headings = clean(lines, args.heading, args.indent)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    for count, (number, original) in enumerate(headings, 1):
        print(f"line {number + args.from_line - 1}: {original} -> Chapter {count}.", file=sys.stderr)
    print(f"{len(headings)} headings, {len(text.split())} words", file=sys.stderr)


if __name__ == "__main__":
    main()
