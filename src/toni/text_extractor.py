"""Text extraction from PDF and text files."""

from pathlib import Path


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
    elif suffix in (".txt", ".text", ".md", ".markdown"):
        return extract_from_text(file_path)
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            "Supported formats: .pdf, .txt, .text, .md"
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
