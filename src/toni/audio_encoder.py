"""Audio encoding and concatenation utilities."""

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


def save_as_mp3(
    audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
    bitrate: str = "192k",
    progress_callback: Callable[[float], None] | None = None,
) -> None:
    """Save audio array as MP3 file using pydub.

    Args:
        audio: Audio data as float32 numpy array.
        sample_rate: Sample rate in Hz.
        output_path: Path to save the MP3 file.
        bitrate: MP3 bitrate (e.g., "128k", "192k", "320k").
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
    import wave

    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())
