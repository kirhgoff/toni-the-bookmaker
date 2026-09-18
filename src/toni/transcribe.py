"""Transcribe a voice reference clip with Whisper.

Run once during preparation so render workers never load the ASR model:
OmniVoice pulls Whisper large-v3-turbo (~1.6GB) into every process that
clones a voice without a supplied transcript.
"""

import sys
from pathlib import Path

import click


def transcribe_reference(audio_path: Path, device: str = "cpu") -> str:
    """Return the transcript of a reference clip."""
    import torch
    from omnivoice import OmniVoice

    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        device_map=device,
        dtype=torch.float32 if device == "cpu" else torch.float16,
    )
    model.load_asr_model()
    return model.transcribe(str(audio_path)).strip()


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
        raise SystemExit("omnivoice is not installed. Install it with: uv sync --extra omni")

    if output:
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
