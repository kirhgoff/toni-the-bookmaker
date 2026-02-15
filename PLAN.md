# Toni the Book Maker - Project Plan

A CLI tool that converts PDF/text files to MP3 audiobooks using Text-to-Speech models with a pluggable TTS backend system.

## Tech Stack

- **Python** with **uv** for dependency management
- **Click** for CLI
- **PyMuPDF** for PDF extraction
- **pydub + ffmpeg** for MP3 encoding
- **Pocket TTS** as default (Kani TTS 2 as optional)

## Model Comparison

| Feature | Kani TTS 2 | Pocket TTS |
|---------|------------|------------|
| Size | 400M params | 100M params |
| Sample Rate | 22kHz | 24kHz |
| Requirements | GPU (3GB VRAM) | CPU only |
| Voice Cloning | Yes | Yes |
| Installation | `pip install kani-tts-2` | `pip install pocket-tts` |
| Streaming | No | Yes |

## Project Structure

```
toni-the-book-maker/
├── pyproject.toml
├── src/
│   └── toni/
│       ├── __init__.py
│       ├── cli.py                 # CLI commands
│       ├── text_extractor.py      # PDF/text file reading
│       ├── audio_encoder.py       # WAV→MP3 + concatenation
│       ├── chunker.py             # Split text into TTS-friendly chunks
│       └── tts/
│           ├── __init__.py        # TTS registry/factory
│           ├── base.py            # Abstract TTSEngine protocol
│           ├── pocket.py          # Pocket TTS implementation
│           └── kani.py            # Kani TTS 2 implementation
├── run.sh                         # Main entry point
├── install.sh                     # Setup dependencies
└── .python-version                # Pin Python version (3.12)
```

## Implementation Tasks

### 1. Project Initialization
- Create `pyproject.toml` with uv configuration
- Define core dependencies: `click`, `pymupdf`, `pydub`
- Define optional dependencies: `pocket-tts`, `kani-tts-2`
- Create `install.sh` to run `uv sync`

### 2. TTS Abstraction Layer (`src/toni/tts/`)

**`base.py`**: Define `TTSEngine` protocol/abstract class
```python
class TTSEngine(Protocol):
    def generate(self, text: str, voice_sample: Path | None = None) -> np.ndarray
    def sample_rate(self) -> int
    def max_chunk_length(self) -> int  # chars or seconds
```

**`pocket.py`**: Implement Pocket TTS adapter
**`kani.py`**: Implement Kani TTS 2 adapter
**`__init__.py`**: Factory function to get engine by name

### 3. Text Processing (`src/toni/`)

**`text_extractor.py`**: 
- `extract_from_pdf(path) -> str`
- `extract_from_text(path) -> str`
- Auto-detect format by extension

**`chunker.py`**:
- Split text into chunks respecting sentence boundaries
- Configurable max chunk size (default: ~500 chars for safe TTS processing)
- Handle paragraph breaks intelligently

### 4. Audio Pipeline (`src/toni/audio_encoder.py`)
- Concatenate multiple audio arrays
- Add small pauses between chunks (configurable)
- Convert to MP3 using pydub
- Progress callback support

### 5. CLI (`src/toni/cli.py`)

```bash
toni --input book.pdf --output audiobook.mp3 [--voice voice.wav] [--model pocket|kani]
```

Options:
- `--input` / `-i`: PDF or text file (required)
- `--output` / `-o`: Output MP3 path (default: `<input_name>.mp3`)
- `--voice` / `-v`: Optional voice sample WAV file
- `--model` / `-m`: TTS model to use (default: `pocket`)
- `--chunk-pause`: Pause duration between chunks in ms (default: 500)
- `--verbose`: Show progress

### 6. Shell Scripts

**`install.sh`**:
```bash
#!/bin/bash
uv sync
# Check for ffmpeg
```

**`run.sh`**:
```bash
#!/bin/bash
uv run python -m toni.cli "$@"
```

## Dependencies Summary

**Core (always installed):**
- `click` - CLI framework
- `pymupdf` - PDF extraction  
- `pydub` - Audio processing
- `numpy` - Audio array handling

**Model-specific (optional groups - mutually exclusive due to numpy version conflicts):**
- `[pocket]`: `pocket-tts` (requires numpy>=2)
- `[kani]`: `kani-tts-2`, `transformers` (requires numpy<2)

## Workflow

```
Input File (PDF/TXT)
        ↓
   Text Extraction (PyMuPDF)
        ↓
   Text Chunking (sentence-aware)
        ↓
   TTS Generation (loop through chunks)
        ↓
   Audio Concatenation (with pauses)
        ↓
   MP3 Encoding (pydub/ffmpeg)
        ↓
   Output MP3
```

## Notes

1. **ffmpeg requirement**: Users need ffmpeg installed for MP3 encoding. The `install.sh` script will check and warn if missing.

2. **Voice cloning**: Both models support voice cloning. Pass a WAV file via `--voice` to use a custom voice.

3. **Long documents**: Text is chunked to avoid TTS limits. Pocket TTS handles long inputs natively, but we'll chunk for consistency and progress reporting.

4. **Extensibility**: Adding a new TTS model requires:
   - Create `src/toni/tts/newmodel.py` implementing `TTSEngine`
   - Register in `src/toni/tts/__init__.py`
   - Add optional dependency group in `pyproject.toml`
