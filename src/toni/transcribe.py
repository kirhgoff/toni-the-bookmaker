"""Transcribe a voice reference clip with Whisper.

Run once during preparation so render workers never load the ASR model:
OmniVoice pulls Whisper large-v3-turbo (~1.6GB) into every process that
clones a voice without a supplied transcript.
"""

import os
import sys
from pathlib import Path
from typing import Callable

import click
import numpy as np
import soundfile as sf


def load_transcriber(device: str | None = None) -> Callable[[np.ndarray, int], str]:
    import torch
    from transformers import pipeline
    from transformers.models.whisper.tokenization_whisper import TO_LANGUAGE_CODE

    from toni.text_normalization import base_language

    if device is None:
        device = (
            "mps" if torch.backends.mps.is_available()
            else "cuda" if torch.cuda.is_available()
            else "cpu"
        )
    asr = pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-large-v3-turbo",
        device=device,
        torch_dtype=torch.float32 if device == "cpu" else torch.float16,
    )
    language = base_language(os.environ.get("TONI_LANGUAGE"))
    generate_kwargs = (
        {"language": language, "task": "transcribe"} if language in TO_LANGUAGE_CODE.values() else {}
    )

    def transcribe(waveform: np.ndarray, sample_rate: int) -> str:
        return asr(
            {"raw": waveform, "sampling_rate": sample_rate},
            return_timestamps=len(waveform) > 30 * sample_rate,
            generate_kwargs=generate_kwargs,
        )["text"].strip()

    return transcribe


def transcribe_reference(audio_path: Path, device: str = "cpu") -> str:
    """Return the transcript of a reference clip."""
    transcriber = load_transcriber(device)
    waveform, sample_rate = sf.read(audio_path, dtype="float32")
    if waveform.ndim > 1:
        waveform = waveform.mean(axis=1)
    return transcriber(waveform, sample_rate)


@click.command()
@click.argument("audio", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None,
              help="Write the transcript here instead of stdout.")
@click.option("--device", default="cpu", help="Device for the ASR model.")
def main(audio: Path, output: Path | None, device: str) -> None:
    """Transcribe AUDIO and print the text."""
    try:
        text = transcribe_reference(audio, device)
    except ImportError:
        raise SystemExit("transformers is not installed. Install an engine extra, e.g.: uv sync --extra omni")

    if output:
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
