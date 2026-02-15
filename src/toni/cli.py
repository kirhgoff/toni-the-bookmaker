"""CLI entry point for Toni the Book Maker."""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import click

from toni import __version__
from toni.audio_encoder import concatenate_with_ffmpeg, save_chunk_wav
from toni.chunker import chunk_text, split_chunk
from toni.text_extractor import extract_text
from toni.tts import get_engine, list_engines
from toni.work_manager import WorkManager


def get_default_workers() -> int:
    """Get default number of workers (half of CPU cores, minimum 1)."""
    return max(1, (os.cpu_count() or 2) // 2)


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
    "--workers",
    type=int,
    default=None,
    help=f"Number of parallel workers. Default: {get_default_workers()} (half of CPU cores).",
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
    workers: int | None,
    verbose: bool,
) -> None:
    """Generate audiobook from PDF or text file.

    Features:
    - Auto-resume: If a previous run exists, automatically continues from where it stopped
    - Auto-retry: Failed chunks are automatically split and retried
    - Parallel processing: Use --workers to process chunks in parallel
    - Work directory: All intermediate files are saved for inspection and recovery

    Examples:

        toni -i book.pdf -o audiobook.mp3

        toni -i story.txt --voice my_voice.wav --model pocket

        toni -i document.pdf --workers 4 --bitrate 320k
    """
    if output_file is None:
        output_file = input_file.with_suffix(".mp3")

    if workers is None:
        workers = get_default_workers()

    work_base = work_dir if work_dir else Path("./work")
    work = WorkManager(output_file, work_base)

    if verbose:
        click.echo(f"Input: {input_file}")
        click.echo(f"Output: {output_file}")
        click.echo(f"Model: {model}")
        click.echo(f"Workers: {workers}")
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

        voice_file_for_tts = work.get_copied_voice_path()
    else:
        click.echo("Extracting text...")
        text = extract_text(input_file)

        if verbose:
            click.echo(f"Extracted {len(text)} characters")

        click.echo(f"Loading {model} TTS model to get settings...")
        engine = get_engine(model)
        engine.load()

        chunks = chunk_text(text, max_chars=engine.max_chunk_chars)
        total_chunks = len(chunks)

        if verbose:
            click.echo(f"Split into {total_chunks} chunks")

        click.echo("Setting up work directory...")
        work.setup()

        click.echo("Copying input files to work directory...")
        copied_input = work.copy_input_file(input_file)
        copied_voice = work.copy_voice_file(voice_file) if voice_file else None

        manifest = work.init_manifest(
            input_file=input_file,
            output_file=output_file,
            model=model,
            voice_file=voice_file,
            sample_rate=engine.sample_rate,
            chunk_pause_ms=chunk_pause,
            total_chunks=total_chunks,
            copied_input=copied_input,
            copied_voice=copied_voice,
        )

        for i, chunk in enumerate(chunks):
            work.save_chunk_text(str(i), chunk)

        click.echo(f"Saved {total_chunks} text chunks to {work.chunks_dir}")

        voice_file_for_tts = copied_voice
        engine.unload()

    pending_chunks = work.get_pending_chunks()
    if not pending_chunks:
        click.echo("No pending chunks to process.")
    else:
        click.echo(
            f"Processing {len(pending_chunks)} chunks with {workers} worker(s)..."
        )

        if workers == 1:
            process_chunks_single(
                work=work,
                model=manifest.model,
                voice_file=voice_file_for_tts,
                max_retries=max_retries,
                verbose=verbose,
            )
        else:
            process_chunks_parallel(
                work=work,
                model=manifest.model,
                voice_file=voice_file_for_tts,
                max_retries=max_retries,
                workers=workers,
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

    click.echo(f"Concatenating {len(audio_chunk_ids)} audio chunks with ffmpeg...")
    audio_paths = [work.get_chunk_audio_path(cid) for cid in audio_chunk_ids]

    concatenate_with_ffmpeg(
        audio_paths=audio_paths,
        output_path=work.output_mp3_path,
        sample_rate=manifest.sample_rate,
        pause_ms=manifest.chunk_pause_ms,
        bitrate=bitrate,
        work_dir=work.work_dir,
    )

    if output_file.resolve() != work.output_mp3_path.resolve():
        click.echo(f"Copying output to {output_file}...")
        shutil.copy2(work.output_mp3_path, output_file)

    import wave

    total_duration_seconds = 0
    for audio_path in audio_paths:
        with wave.open(str(audio_path), "rb") as wf:
            total_duration_seconds += wf.getnframes() / wf.getframerate()

    duration_minutes = total_duration_seconds / 60

    click.echo(f"\nDone! Generated {duration_minutes:.1f} minutes of audio")
    click.echo(f"Output: {output_file}")
    click.echo(f"Work directory: {work.work_dir}")


def process_chunks_single(
    work: WorkManager,
    model: str,
    voice_file: Path | None,
    max_retries: int,
    verbose: bool,
) -> None:
    """Process all pending chunks sequentially with a single worker."""
    engine = get_engine(model)
    engine.load()

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


def process_chunks_parallel(
    work: WorkManager,
    model: str,
    voice_file: Path | None,
    max_retries: int,
    workers: int,
    verbose: bool,
) -> None:
    """Process chunks in parallel using ThreadPoolExecutor."""
    pending = work.get_pending_chunks()
    total = len(pending)

    chunk_batches = distribute_chunks(pending, workers)

    if verbose:
        click.echo(f"Distributing {total} chunks across {len(chunk_batches)} workers")
        for i, batch in enumerate(chunk_batches):
            click.echo(f"  Worker {i + 1}: {len(batch)} chunks")

    completed_count = 0
    failed_count = 0
    lock = Lock()

    def worker_fn(worker_id: int, chunk_ids: list[str]) -> dict:
        nonlocal completed_count, failed_count

        engine = get_engine(model)
        engine.load()

        results = {"completed": 0, "failed": 0}

        for chunk_id in chunk_ids:
            success = process_single_chunk(
                work=work,
                engine=engine,
                chunk_id=chunk_id,
                voice_file=voice_file,
                max_retries=max_retries,
                verbose=verbose,
            )

            with lock:
                if success:
                    completed_count += 1
                    results["completed"] += 1
                else:
                    failed_count += 1
                    results["failed"] += 1

        engine.unload()
        return results

    with click.progressbar(
        length=total,
        label="Processing",
        show_percent=True,
        show_pos=True,
    ) as progress_bar:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(worker_fn, i, batch): i
                for i, batch in enumerate(chunk_batches)
            }

            last_count = 0
            while futures:
                for future in list(futures.keys()):
                    if future.done():
                        del futures[future]

                current_count = completed_count + failed_count
                if current_count > last_count:
                    progress_bar.update(current_count - last_count)
                    last_count = current_count

                import time

                time.sleep(0.1)

            final_count = completed_count + failed_count
            if final_count > last_count:
                progress_bar.update(final_count - last_count)


def distribute_chunks(chunk_ids: list[str], num_workers: int) -> list[list[str]]:
    """Distribute chunk IDs evenly across workers.

    Args:
        chunk_ids: List of chunk IDs to distribute.
        num_workers: Number of workers.

    Returns:
        List of lists, where each inner list contains chunk IDs for one worker.
    """
    if not chunk_ids:
        return []

    num_workers = min(num_workers, len(chunk_ids))

    batches = [[] for _ in range(num_workers)]
    for i, chunk_id in enumerate(chunk_ids):
        batches[i % num_workers].append(chunk_id)

    return [batch for batch in batches if batch]


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
