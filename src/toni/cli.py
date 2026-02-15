"""CLI entry point for Toni the Book Maker."""

from pathlib import Path

import click

from toni import __version__
from toni.audio_encoder import concatenate_from_files, save_as_mp3, save_chunk_wav
from toni.chunker import chunk_text, split_chunk
from toni.text_extractor import extract_text
from toni.tts import get_engine, list_engines
from toni.work_manager import WorkManager


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
    "--work-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom work directory base. Defaults to ./work/",
)
@click.option(
    "--max-retries",
    type=int,
    default=2,
    help="Max retries for failed chunks (with auto-split).",
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
    work_dir: Path | None,
    max_retries: int,
    verbose: bool,
) -> None:
    """Generate audiobook from PDF or text file.

    Features:
    - Auto-resume: If a previous run exists, automatically continues from where it stopped
    - Auto-retry: Failed chunks are automatically split and retried
    - Work directory: All intermediate files are saved for inspection and recovery

    Examples:

        toni -i book.pdf -o audiobook.mp3

        toni -i story.txt --voice my_voice.wav --model pocket

        toni -i document.pdf -m kani --bitrate 320k
    """
    if output_file is None:
        output_file = input_file.with_suffix(".mp3")

    work_base = work_dir if work_dir else Path("./work")
    work = WorkManager(output_file, work_base)

    if verbose:
        click.echo(f"Input: {input_file}")
        click.echo(f"Output: {output_file}")
        click.echo(f"Model: {model}")
        click.echo(f"Work directory: {work.work_dir}")
        if voice_file:
            click.echo(f"Voice: {voice_file}")

    resuming = work.has_existing_run()
    if resuming:
        click.echo(f"Found existing run in {work.work_dir}, resuming...")
        manifest = work.load_manifest()
        progress = work.get_progress_summary()
        click.echo(
            f"Progress: {progress['completed']}/{progress['total']} completed, "
            f"{progress['failed']} failed, {progress['pending']} pending"
        )
    else:
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

        click.echo("Setting up work directory...")
        work.setup()
        manifest = work.init_manifest(
            input_file=input_file,
            output_file=output_file,
            model=model,
            voice_file=voice_file,
            sample_rate=engine.sample_rate,
            chunk_pause_ms=chunk_pause,
            total_chunks=total_chunks,
        )

        for i, chunk in enumerate(chunks):
            work.save_chunk_text(str(i), chunk)

        click.echo(f"Saved {total_chunks} text chunks to {work.chunks_dir}")

    engine = get_engine(manifest.model)
    engine.load()

    pending_chunks = work.get_pending_chunks()
    if not pending_chunks:
        click.echo("No pending chunks to process.")
    else:
        click.echo(f"Processing {len(pending_chunks)} chunks...")
        process_chunks(
            work=work,
            engine=engine,
            voice_file=Path(manifest.voice_file) if manifest.voice_file else None,
            max_retries=max_retries,
            verbose=verbose,
        )

    progress = work.get_progress_summary()
    click.echo(
        f"\nProcessing complete: {progress['completed']} completed, "
        f"{progress['failed']} failed, {progress['split']} split"
    )

    if progress["failed"] > 0:
        failed_chunks = work.get_failed_chunks()
        click.echo(
            f"Warning: {len(failed_chunks)} chunks failed: {failed_chunks[:10]}..."
        )

    audio_chunk_ids = work.get_all_audio_chunks_ordered()
    if not audio_chunk_ids:
        click.echo("Error: No audio chunks generated. Cannot create output file.")
        return

    click.echo(f"Concatenating {len(audio_chunk_ids)} audio chunks...")
    audio_paths = [work.get_chunk_audio_path(cid) for cid in audio_chunk_ids]
    full_audio = concatenate_from_files(
        audio_paths,
        sample_rate=manifest.sample_rate,
        pause_ms=manifest.chunk_pause_ms,
    )

    click.echo("Encoding to MP3...")
    save_as_mp3(
        full_audio,
        sample_rate=manifest.sample_rate,
        output_path=output_file,
        bitrate=bitrate,
    )

    duration_seconds = len(full_audio) / manifest.sample_rate
    duration_minutes = duration_seconds / 60

    click.echo(
        f"\nDone! Generated {duration_minutes:.1f} minutes of audio: {output_file}"
    )
    click.echo(f"Work directory preserved at: {work.work_dir}")


def process_chunks(
    work: WorkManager,
    engine,
    voice_file: Path | None,
    max_retries: int,
    verbose: bool,
) -> None:
    """Process all pending chunks with retry logic."""
    pending = work.get_pending_chunks()
    total = len(pending)

    with click.progressbar(
        pending,
        length=total,
        label="Processing",
        show_percent=True,
        show_pos=True,
    ) as progress:
        for chunk_id in progress:
            process_single_chunk(
                work=work,
                engine=engine,
                chunk_id=chunk_id,
                voice_file=voice_file,
                max_retries=max_retries,
                verbose=verbose,
            )


def process_single_chunk(
    work: WorkManager,
    engine,
    chunk_id: str,
    voice_file: Path | None,
    max_retries: int,
    verbose: bool,
    current_retry: int = 0,
) -> bool:
    """Process a single chunk with error handling and retry.

    Returns True if successful, False otherwise.
    """
    text = work.load_chunk_text(chunk_id)

    try:
        audio = engine.generate(text, voice_sample=voice_file)
        audio_path = work.get_chunk_audio_path(chunk_id)
        save_chunk_wav(audio, engine.sample_rate, audio_path)
        work.set_chunk_status(chunk_id, "completed")
        return True

    except Exception as e:
        error_msg = str(e)
        if verbose:
            click.echo(f"\nChunk {chunk_id} failed: {error_msg[:100]}")

        retries = work.get_retries(chunk_id)
        if retries < max_retries:
            if verbose:
                click.echo(
                    f"Splitting chunk {chunk_id} for retry ({retries + 1}/{max_retries})..."
                )

            sub_texts = split_chunk(text)
            if len(sub_texts) > 1:
                sub_ids = []
                for i, sub_text in enumerate(sub_texts):
                    sub_id = f"{chunk_id}_{i}"
                    sub_ids.append(sub_id)
                    work.add_sub_chunk(chunk_id, sub_id, sub_text)

                all_success = True
                for sub_id in sub_ids:
                    success = process_single_chunk(
                        work=work,
                        engine=engine,
                        chunk_id=sub_id,
                        voice_file=voice_file,
                        max_retries=max_retries,
                        verbose=verbose,
                        current_retry=current_retry + 1,
                    )
                    if not success:
                        all_success = False

                return all_success
            else:
                work.increment_retries(chunk_id)
                work.set_chunk_status(chunk_id, "failed", error=error_msg)
                return False
        else:
            work.set_chunk_status(chunk_id, "failed", error=error_msg)
            return False


if __name__ == "__main__":
    main()
