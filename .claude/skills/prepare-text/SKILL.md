---
name: prepare-text
description: Turn a book PDF or text file, usually an OCR'd scan, into a clean UTF-8 source text ready for narration - extraction, encoding, front and back matter, page numbers, hyphenation, paragraph rejoining, chapter headings. Use when the user says "prepare the text", "clean the text", "clean up this PDF", "OCR", or asks to get a book ready for recording.
---

# Prepare text for narration

1. **Ground rule: never quote book text in your reply.** Inspect it in tool output only, and report line numbers, counts and shapes instead, e.g. `sed -E 's/[0-9]/#/g; s/[a-z]/a/g'` to see a line's structure without its words.
2. **Extract.**
   ```bash
   pdftotext -layout BOOK.pdf BOOK.txt
   file BOOK.txt   # must say UTF-8
   ```
   `-layout` keeps indentation, which is how paragraph starts are detected later. If `file` doesn't say UTF-8, convert: `iconv -f CP1251/KOI8-R/WINDOWS-1252 -t UTF-8 BOOK.txt -o BOOK.txt`. Hand the driver a `.txt`; its own `.pdf` input path is broken (`prepareSource` in `src/record/prep.ts` reads the PDF as text).
3. **Find the slice.** Front matter to drop — cover OCR garbage, author bio, "Also by", copyright page, dedication, trade-mark notice — ends where the story begins:
   ```bash
   grep -nE "^ *([IVXLC]+|CHAPTER|Chapter|PART|Part)\b *$" BOOK.txt | head
   ```
   Back matter to drop — ads, order form, price list, back-cover blurb — starts after the story ends:
   ```bash
   grep -nE "^ *(THE END|ORDER|Please send|\$[0-9])" BOOK.txt
   tail -n 60 BOOK.txt | cut -c1-40   # inspect in tool output only
   ```
4. **Clean.**
   ```bash
   uv run python -m toni.clean_pdf_text BOOK.txt -o BOOK.clean.txt --from N --to M [--heading '[IVXL]+|Ill|xvm']
   ```
   Per line: strips form feeds and soft hyphens; drops centered page numbers; strips page numbers glued mid-line or leading a line; a line whose stripped text fullmatches `--heading` becomes its own `Chapter N.` paragraph; a line indented at or past the paragraph indent (auto-detected from the file, or `--indent`) starts a new paragraph; a trailing hyphen glues onto a lowercase continuation line; runs of spaces collapse to one.

   Read the stderr heading list it prints. OCR-garbled numerals (`Ill`, `xvm`, `1V`) mean extend `--heading` with the exact garbage seen. A jump in the roman sequence (`III` then `Chapter 4` where `IV` should have been `Chapter 4`) means a chapter heading is missing from the scan — tell the user and let them decide before recording.

   Headings become `Chapter N.` on purpose: a bare `I` clashes with the pronoun in any chapter regex, and `Chapter N.` matches the driver's default chapter pattern (`DEFAULT_CHAPTER_PATTERN` in `src/toni/audio_encoder.py`) and reads well aloud.
5. **Book-specific leftovers.** Grep, inspect the surrounding context, then fix with `sed -i ''`:
   - Printer signature marks, e.g. `[A-Z0-9]\.[0-9] ?— ?[0-9]+( [0-9]{1,3})?`
   - Running heads (title or author in caps): `^[0-9]+ +[A-Z ]+$`
   - Leftover numeric tokens: `grep -nE "(^| )[0-9]{1,3}( |$)" BOOK.clean.txt | grep -v ": *Chapter"`, then read the surrounding words with `grep -oE '.{15}\bN\b.{15}'` before deleting anything — years, counts and prices are legitimate.
6. **Verify.**

   | Check | Command | Expected |
   |---|---|---|
   | Heading count | `grep -cE '^Chapter [0-9]+\.$' BOOK.clean.txt` | matches what you expect |
   | No double spaces | `grep -c "  " BOOK.clean.txt` | 0 |
   | No bare page numbers | `grep -cE '^[0-9]{1,3}$' BOOK.clean.txt` | 0 |
   | No spurious chapter starts | `grep -nE "^(Part\|Book\|Section\|PART\|BOOK\|SECTION)\b" BOOK.clean.txt` | empty — the driver's default chapter regex would turn these paragraphs into chapters |
   | Word count | `wc -w BOOK.clean.txt` vs `wc -w BOOK.txt` | within ~5% |
   | Encoding | `file BOOK.clean.txt` | UTF-8 |
7. **Hand off.**
   ```bash
   scripts/record_audiobook.sh -i BOOK.clean.txt -n <name> ...
   ```
   The driver copies it to `<library>/<name>/source.txt`. If `source.txt` already exists for that name, it's reused as-is (`src/record/index.ts` logs "Source already prepared, reusing" and skips re-copying) — replace it explicitly when re-preparing the same book.
