"""Text chunking for TTS processing."""

import re
from dataclasses import dataclass

from toni.lexicon import apply_lexicon
from toni.pause_tags import MAX_PAUSE_MS, parse_pause_tags
from toni.text_normalization import normalization_enabled, normalize_speech_text

ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "vs", "etc",
    "e.g", "i.e", "a.m", "p.m", "vol", "ch", "fig",
    "т.е", "т.д", "т.п", "г", "гг", "ул", "проф",
})
INITIAL = re.compile(r"[A-ZА-ЯЁ]")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+(?=[\"«\'(\u2014-]?\+?[^\W\d_a-zа-яё])")
CLAUSE_MARK = r"(?:(?<!\d)[,:]|[,:](?!\d)|[;\-—])"
TERMINAL_PUNCTUATION = re.compile(r"[.!?…,:;\-—][\"»”\')\]]*$")
SPEAKABLE = re.compile(r"\w")


@dataclass
class Chunk:
    text: str
    pause_ms: int = 0
    speed: float | None = None
    raw_text: str = ""


def chunk_text(
    text: str,
    max_chars: int = 500,
    language: str | None = None,
    lexicon: dict[str, str] | None = None,
) -> list[str]:
    """chunk_with_marks without the pacing metadata."""
    return [chunk.text for chunk in chunk_with_marks(text, max_chars, language, lexicon)]


def chunk_with_marks(
    text: str,
    max_chars: int = 500,
    language: str | None = None,
    lexicon: dict[str, str] | None = None,
) -> list[Chunk]:
    """Chunk text, honouring [pause] and [slow] tags as per-chunk metadata."""
    chunks: list[Chunk] = []
    for segment in parse_pause_tags(text):
        pieces = _chunk_plain(segment.text, max_chars, language, lexicon)
        chunks.extend(Chunk(spoken, speed=segment.speed, raw_text=raw) for raw, spoken in pieces)
        if pieces:
            chunks[-1].pause_ms = segment.pause_ms
        elif chunks:
            chunks[-1].pause_ms = min(chunks[-1].pause_ms + segment.pause_ms, MAX_PAUSE_MS)
    return chunks


def _chunk_plain(
    text: str,
    max_chars: int = 500,
    language: str | None = None,
    lexicon: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Split text into (pre-normalisation text, spoken text) chunks suitable for TTS processing.

    Chunks are split at sentence boundaries when possible, respecting
    the maximum character limit. Paragraph breaks are preserved.

    Args:
        text: The input text to chunk.
        max_chars: Maximum characters per chunk.
        language: Language code; enables numbers, years and abbreviations to be
            spoken out unless TONI_NORMALIZE=0.
        lexicon: Pronunciation respellings applied after normalisation.

    Returns:
        List of (raw text, spoken text) pairs; raw text is what chapter
        headings are detected on.
    """
    if not text.strip():
        return []

    chunks: list[tuple[str, str]] = []
    for raw in split_into_paragraphs(normalize_text(text)):
        raw = raw.strip()
        if not raw:
            continue
        spoken = _speak(raw, language, lexicon)
        if len(spoken) <= max_chars:
            chunks.append((raw, spoken))
            continue
        pieces = [
            end_with_punctuation(piece) for piece in split_paragraph(spoken, max_chars)
        ]
        chunks.extend((raw if index == 0 else piece, piece) for index, piece in enumerate(pieces))

    return merge_unspeakable(chunks, max_chars)


def _speak(text: str, language: str | None, lexicon: dict[str, str] | None) -> str:
    if normalization_enabled():
        text = normalize_speech_text(text, language)
    return apply_lexicon(text, lexicon or {})


def end_with_punctuation(chunk: str, mark: str = ".") -> str:
    """Give a piece cut from a long paragraph a terminal mark for finished intonation."""
    return chunk if TERMINAL_PUNCTUATION.search(chunk) else chunk + mark


def merge_unspeakable(
    chunks: list[tuple[str, str]], max_chars: int
) -> list[tuple[str, str]]:
    """Fold chunks with no letters or digits into the previous or next chunk; drop them if neither fits."""
    merged: list[tuple[str, str]] = []
    carry: tuple[str, str] | None = None
    for raw, spoken in chunks:
        if not SPEAKABLE.search(spoken):
            if merged and len(merged[-1][1]) + len(spoken) + 1 <= max_chars:
                merged[-1] = (f"{merged[-1][0]} {raw}", f"{merged[-1][1]} {spoken}")
            elif carry:
                carry = (f"{carry[0]} {raw}", f"{carry[1]} {spoken}")
            else:
                carry = (raw, spoken)
            continue
        if carry and len(carry[1]) + len(spoken) + 1 <= max_chars:
            spoken = f"{carry[1]} {spoken}"
        carry = None
        merged.append((raw, spoken))
    return merged


def split_chunk(text: str, max_chars: int | None = None) -> list[str]:
    """Split a single chunk into smaller pieces for retry.

    This is used when TTS generation fails on a chunk. It splits
    the text roughly in half at a sentence boundary.

    Args:
        text: The text to split.
        max_chars: Optional max chars per sub-chunk. If None, splits in half.

    Returns:
        List of smaller text chunks (usually 2).
    """
    text = text.strip()
    if not text:
        return []

    if max_chars is not None and len(text) <= max_chars:
        return [text]

    sentences = split_into_sentences(text)

    if len(sentences) <= 1:
        if max_chars is not None:
            return split_long_sentence(text, max_chars)
        mid = len(text) // 2
        space_pos = text.rfind(" ", 0, mid)
        if space_pos > 0:
            return [text[:space_pos].strip(), text[space_pos:].strip()]
        return [text]

    mid_idx = len(sentences) // 2
    first_half = " ".join(sentences[:mid_idx])
    second_half = " ".join(sentences[mid_idx:])

    result = []
    if first_half.strip():
        result.append(first_half.strip())
    if second_half.strip():
        result.append(second_half.strip())

    return result if result else [text]


def normalize_text(text: str) -> str:
    """Normalize text for TTS processing.

    - Replaces multiple spaces with single space
    - Normalizes line endings
    - Removes excessive blank lines
    """
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_into_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs."""
    return re.split(r"\n\s*\n", text)


def split_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Split a single paragraph into sentence-aware chunks."""
    sentences = split_into_sentences(paragraph)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            chunks.extend(split_long_sentence(sentence, max_chars))
        elif len(current_chunk) + len(sentence) + 1 <= max_chars:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping abbreviations like "Mr." or "т. е." intact."""
    sentences = []
    start = 0
    for boundary in SENTENCE_BOUNDARY.finditer(text):
        if not ends_with_abbreviation(text[start:boundary.start()], text[boundary.end():]):
            sentences.append(text[start:boundary.start()])
            start = boundary.end()
    sentences.append(text[start:])
    return [s.strip() for s in sentences if s.strip()]


def _is_initial(word: str) -> bool:
    return word.endswith(".") and bool(INITIAL.fullmatch(word.lstrip("\"«'(").rstrip(".")))


def ends_with_abbreviation(sentence: str, following: str = "") -> bool:
    if not sentence.endswith("."):
        return False
    words = sentence.split()
    candidates = [words[-1], "".join(words[-2:])]
    if any(word.lstrip("\"«'(").rstrip(".").lower() in ABBREVIATIONS for word in candidates):
        return True
    next_words = following.split()
    return _is_initial(words[-1]) and (
        (len(words) > 1 and _is_initial(words[-2])) or (bool(next_words) and _is_initial(next_words[0]))
    )


def split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Split a sentence that exceeds max_chars at clause boundaries."""
    clause_pattern = CLAUSE_MARK
    parts = re.split(f"({clause_pattern})", sentence)

    chunks = []
    current = ""

    for i, part in enumerate(parts):
        if re.match(clause_pattern, part):
            current += part
        elif len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                chunks.append(current.strip())
            if len(part) > max_chars:
                words = part.split()
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 <= max_chars:
                        current = current + " " + word if current else word
                    else:
                        if current:
                            chunks.append(end_with_punctuation(current.strip(), ","))
                        current = word
            else:
                current = part

    if current:
        chunks.append(current.strip())

    return chunks
