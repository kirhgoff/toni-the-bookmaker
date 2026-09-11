"""Text chunking for TTS processing."""

import re


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    """Split text into chunks suitable for TTS processing.

    Chunks are split at sentence boundaries when possible, respecting
    the maximum character limit. Paragraph breaks are preserved.

    Args:
        text: The input text to chunk.
        max_chars: Maximum characters per chunk.

    Returns:
        List of text chunks.
    """
    if not text.strip():
        return []

    text = normalize_text(text)
    paragraphs = split_into_paragraphs(text)

    chunks = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
        else:
            chunks.extend(split_paragraph(paragraph, max_chars))

    return chunks


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
    """Split text into sentences using regex.

    Handles common abbreviations and edge cases.
    """
    sentence_pattern = r"(?<=[.!?…])\s+(?=[\"«\'(\u2014-]?[^\W\d_a-zа-яё])"
    sentences = re.split(sentence_pattern, text)
    return [s.strip() for s in sentences if s.strip()]


def split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Split a sentence that exceeds max_chars at clause boundaries."""
    clause_pattern = r"[,;:\-—]"
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
                            chunks.append(current.strip())
                        current = word
            else:
                current = part

    if current:
        chunks.append(current.strip())

    return chunks
