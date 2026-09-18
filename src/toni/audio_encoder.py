"""Audio encoding and concatenation utilities."""

import contextlib
import re
import subprocess
import wave
from pathlib import Path
from typing import Callable

import numpy as np


def concatenate_audio(
    audio_chunks: list[np.ndarray],
    sample_rate: int,
    pause_ms: int = 500,
) -> np.ndarray:
    """Concatenate audio chunks with pauses between them.

    Args:
        audio_chunks: List of audio arrays (float32, mono).
        sample_rate: Sample rate in Hz.
        pause_ms: Duration of pause between chunks in milliseconds.

    Returns:
        Concatenated audio as a single numpy array.
    """
    if not audio_chunks:
        return np.array([], dtype=np.float32)

    pause_samples = int(sample_rate * pause_ms / 1000)
    silence = np.zeros(pause_samples, dtype=np.float32)

    parts = []
    for i, chunk in enumerate(audio_chunks):
        parts.append(chunk)
        if i < len(audio_chunks) - 1:
            parts.append(silence)

    return np.concatenate(parts)


def concatenate_from_files(
    audio_paths: list[Path],
    sample_rate: int,
    pause_ms: int = 500,
) -> np.ndarray:
    """Concatenate audio from WAV files with pauses between them.

    Args:
        audio_paths: List of paths to WAV files.
        sample_rate: Expected sample rate in Hz.
        pause_ms: Duration of pause between chunks in milliseconds.

    Returns:
        Concatenated audio as a single numpy array.
    """
    if not audio_paths:
        return np.array([], dtype=np.float32)

    pause_samples = int(sample_rate * pause_ms / 1000)
    silence = np.zeros(pause_samples, dtype=np.float32)

    parts = []
    for i, path in enumerate(audio_paths):
        audio = load_chunk_wav(path)
        parts.append(audio)
        if i < len(audio_paths) - 1:
            parts.append(silence)

    return np.concatenate(parts)


DEFAULT_CHAPTER_PATTERN = (
    r"^\s*(PART|BOOK|CHAPTER|SECTION|PROLOGUE|EPILOGUE"
    r"|Part|Book|Chapter|Section|Prologue|Epilogue)\b"
)

CHAPTERED_FORMATS = {".m4b", ".m4a", ".mp4"}


def wav_duration_ms(path: Path) -> int:
    """Read a WAV's duration from its header without decoding it."""
    with contextlib.closing(wave.open(str(path), "rb")) as wf:
        return round(wf.getnframes() / wf.getframerate() * 1000)


def build_chapters(
    audio_paths: list[Path],
    chunk_texts: list[str],
    pause_ms: int,
    pattern: str = DEFAULT_CHAPTER_PATTERN,
) -> tuple[list[tuple[int, str]], int]:
    """Locate chapter starts by timing the chunks whose text is a heading.

    Offsets come from actual WAV durations rather than estimates, so they
    stay correct even when a chunk was split and re-rendered.

    Returns:
        (chapters as (start_ms, title), total duration in ms)
    """
    heading = re.compile(pattern)
    chapters: list[tuple[int, str]] = []
    offset = 0

    for index, (audio_path, text) in enumerate(zip(audio_paths, chunk_texts)):
        title = " ".join((text or "").split())
        if title and heading.match(title):
            if not chapters or chapters[-1][1] != title[:120]:
                chapters.append((offset, title[:120]))
        offset += wav_duration_ms(audio_path)
        if index < len(audio_paths) - 1:
            offset += pause_ms

    return chapters, offset


def write_ffmetadata(
    chapters: list[tuple[int, str]], total_ms: int, path: Path
) -> None:
    """Write chapter marks in ffmpeg's FFMETADATA format."""
    lines = [";FFMETADATA1"]
    for i, (start, title) in enumerate(chapters):
        end = chapters[i + 1][0] if i + 1 < len(chapters) else total_ms
        if end <= start:
            continue
        escaped = re.sub(r"([=;#\\])", r"\\\1", title)
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start}",
            f"END={end}",
            f"title={escaped}",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concatenate_with_ffmpeg(
    audio_paths: list[Path],
    output_path: Path,
    sample_rate: int,
    pause_ms: int = 500,
    bitrate: str = "64k",
    work_dir: Path | None = None,
    chunk_texts: list[str] | None = None,
    chapter_pattern: str = DEFAULT_CHAPTER_PATTERN,
) -> int:
    """Concatenate WAV files using ffmpeg concat demuxer and encode to MP3.

    This is more efficient for large numbers of files as it avoids
    loading all audio into memory.

    Args:
        audio_paths: List of paths to WAV files to concatenate.
        output_path: Path for the output MP3 file.
        sample_rate: Sample rate in Hz (for generating silence).
        pause_ms: Duration of pause between chunks in milliseconds.
        bitrate: MP3 bitrate. 64k is transparent for mono speech.
        work_dir: Directory to store temporary files. Uses output_path.parent if None.
        chunk_texts: Chunk texts, parallel to audio_paths, used to find chapter
            headings. Chapters are only embedded for .m4b/.m4a outputs.
        chapter_pattern: Regex matched against the start of each chunk's text.

    Returns:
        Number of chapters embedded.

    Raises:
        RuntimeError: If ffmpeg is not available or fails.
    """
    if not audio_paths:
        raise ValueError("No audio files to concatenate")

    if work_dir is None:
        work_dir = output_path.parent

    silence_path = work_dir / "silence.wav"
    concat_list_path = work_dir / "concat_list.txt"

    create_silence_wav(silence_path, sample_rate, pause_ms)

    with open(concat_list_path, "w") as f:
        for i, audio_path in enumerate(audio_paths):
            escaped_path = str(audio_path.absolute()).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
            if i < len(audio_paths) - 1:
                escaped_silence = str(silence_path.absolute()).replace("'", "'\\''")
                f.write(f"file '{escaped_silence}'\n")

    wants_chapters = output_path.suffix.lower() in CHAPTERED_FORMATS
    chapters: list[tuple[int, str]] = []
    if wants_chapters and chunk_texts:
        chapters, total_ms = build_chapters(
            audio_paths, chunk_texts, pause_ms, chapter_pattern
        )

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list_path)]

    if chapters:
        metadata_path = work_dir / "chapters.txt"
        write_ffmetadata(chapters, total_ms, metadata_path)
        cmd += ["-i", str(metadata_path), "-map_metadata", "1"]

    if wants_chapters:
        cmd += ["-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart"]
    else:
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]

    cmd += ["-ar", str(sample_rate), str(output_path)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is not installed or not in PATH. "
            "Install it with: brew install ffmpeg (macOS) or "
            "apt install ffmpeg (Linux)"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr}")

    return len(chapters)


def create_silence_wav(
    output_path: Path,
    sample_rate: int,
    duration_ms: int,
) -> None:
    """Create a WAV file containing silence.

    Args:
        output_path: Path to save the silence WAV file.
        sample_rate: Sample rate in Hz.
        duration_ms: Duration of silence in milliseconds.
    """
    num_samples = int(sample_rate * duration_ms / 1000)
    silence = np.zeros(num_samples, dtype=np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence.tobytes())


def save_chunk_wav(
    audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
) -> None:
    """Save a single audio chunk as WAV file.

    Args:
        audio: Audio data as float32 numpy array.
        sample_rate: Sample rate in Hz.
        output_path: Path to save the WAV file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())


def load_chunk_wav(input_path: Path) -> np.ndarray:
    """Load a WAV file as float32 numpy array.

    Args:
        input_path: Path to the WAV file.

    Returns:
        Audio data as float32 numpy array.
    """
    with wave.open(str(input_path), "rb") as wav_file:
        n_frames = wav_file.getnframes()
        audio_bytes = wav_file.readframes(n_frames)
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32767.0


def save_as_mp3(
    audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
    bitrate: str = "64k",
    progress_callback: Callable[[float], None] | None = None,
) -> None:
    """Save audio array as MP3 file using pydub.

    Args:
        audio: Audio data as float32 numpy array.
        sample_rate: Sample rate in Hz.
        output_path: Path to save the MP3 file.
        bitrate: MP3 bitrate. 64k is transparent for mono speech.
        progress_callback: Optional callback for progress updates.

    Raises:
        ImportError: If pydub is not installed.
        RuntimeError: If ffmpeg is not available.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub is not installed. Install it with: uv sync")

    if progress_callback:
        progress_callback(0.1)

    audio_int16 = (audio * 32767).astype(np.int16)

    if progress_callback:
        progress_callback(0.3)

    segment = AudioSegment(
        data=audio_int16.tobytes(),
        sample_width=2,
        frame_rate=sample_rate,
        channels=1,
    )

    if progress_callback:
        progress_callback(0.5)

    try:
        segment.export(
            str(output_path),
            format="mp3",
            bitrate=bitrate,
        )
    except Exception as e:
        if "ffmpeg" in str(e).lower() or "encoder" in str(e).lower():
            raise RuntimeError(
                "ffmpeg is not installed or not in PATH. "
                "Install it with: brew install ffmpeg (macOS) or "
                "apt install ffmpeg (Linux)"
            ) from e
        raise

    if progress_callback:
        progress_callback(1.0)


def save_as_wav(
    audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
) -> None:
    """Save audio array as WAV file.

    Args:
        audio: Audio data as float32 numpy array.
        sample_rate: Sample rate in Hz.
        output_path: Path to save the WAV file.
    """
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())
