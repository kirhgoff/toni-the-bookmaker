"""CLI entry point for Toni the Book Maker."""

from pathlib import Path

import click

from toni import __version__
from toni.audio_encoder import concatenate_audio, save_as_mp3
from toni.chunker import chunk_text
from toni.text_extractor import extract_text
from toni.tts import get_engine, list_engines


@click.command()
@click.option(
    "-i",
    "--input",
    "input_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Input PDF or text file.",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Output MP3 file. Defaults to <input_name>.mp3.",
)
@click.option(
    "-v",
    "--voice",
    "voice_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Voice sample WAV file for voice cloning.",
)
@click.option(
    "-m",
    "--model",
    type=click.Choice(list_engines()),
    default="pocket",
    help="TTS model to use.",
)
@click.option(
    "--chunk-pause",
    type=int,
    default=500,
    help="Pause duration between chunks in milliseconds.",
)
@click.option(
    "--bitrate",
    type=str,
    default="192k",
    help="MP3 bitrate (e.g., 128k, 192k, 320k).",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show detailed progress.",
)
@click.version_option(version=__version__)
def main(
    input_file: Path,
    output_file: Path | None,
    voice_file: Path | None,
    model: str,
    chunk_pause: int,
    bitrate: str,
    verbose: bool,
) -> None:
    """Generate audiobook from PDF or text file.

    Examples:

        toni -i book.pdf -o audiobook.mp3

        toni -i story.txt --voice my_voice.wav --model pocket

        toni -i document.pdf -m kani --bitrate 320k
    """
    if output_file is None:
        output_file = input_file.with_suffix(".mp3")

    if verbose:
        click.echo(f"Input: {input_file}")
        click.echo(f"Output: {output_file}")
        click.echo(f"Model: {model}")
        if voice_file:
            click.echo(f"Voice: {voice_file}")

    click.echo("Extracting text...")
    text = extract_text(input_file)

    if verbose:
        click.echo(f"Extracted {len(text)} characters")

    click.echo(f"Loading {model} TTS model...")
    engine = get_engine(model)
    engine.load()

    chunks = chunk_text(text, max_chars=engine.max_chunk_chars)
    total_chunks = len(chunks)

    if verbose:
        click.echo(f"Split into {total_chunks} chunks")

    click.echo("Generating audio...")
    audio_chunks = []

    with click.progressbar(
        enumerate(chunks),
        length=total_chunks,
        label="Processing",
        show_percent=True,
        show_pos=True,
    ) as progress:
        for i, chunk in progress:
            audio = engine.generate(chunk, voice_sample=voice_file)
            audio_chunks.append(audio)

    click.echo("Concatenating audio...")
    full_audio = concatenate_audio(
        audio_chunks,
        sample_rate=engine.sample_rate,
        pause_ms=chunk_pause,
    )

    click.echo("Encoding to MP3...")
    save_as_mp3(
        full_audio,
        sample_rate=engine.sample_rate,
        output_path=output_file,
        bitrate=bitrate,
    )

    duration_seconds = len(full_audio) / engine.sample_rate
    duration_minutes = duration_seconds / 60

    click.echo(
        f"Done! Generated {duration_minutes:.1f} minutes of audio: {output_file}"
    )


if __name__ == "__main__":
    main()
