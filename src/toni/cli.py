"""CLI entry point for Toni the Book Maker."""

import os
import shutil
from multiprocessing import Pool
from pathlib import Path

import click
from tqdm import tqdm

from toni import __version__
from toni.audio_encoder import concatenate_with_ffmpeg, save_chunk_wav
from toni.chunker import chunk_text, split_chunk
from toni.text_extractor import extract_text
from toni.tts import get_engine, list_engines
from toni.work_manager import WorkManager


def get_default_workers() -> int:
    """Get default number of workers (half of CPU cores, minimum 1)."""
    return max(1, (os.cpu_count() or 2) // 2)


_worker_engine = None
_worker_voice_file: Path | None = None
_worker_work_dir: str | None = None


def _init_worker(model: str, voice_file_str: str | None, work_dir_str: str) -> None:
    """Initialize TTS engine in worker process.

    This runs once per worker process when the Pool is created.
    The engine is stored in module-level globals for reuse across chunks.
    """
    global _worker_engine, _worker_voice_file, _worker_work_dir
    from toni.tts import get_engine

    _worker_engine = get_engine(model)
    _worker_engine.load()
    _worker_voice_file = Path(voice_file_str) if voice_file_str else None
    _worker_work_dir = work_dir_str


def _process_chunk_in_worker(args: tuple) -> tuple[str, bool, list[str]]:
    """Process a single chunk in a worker process.

    Args:
        args: Tuple of (chunk_id, max_depth, verbose)

    Returns:
        Tuple of (chunk_id, success, list of generated audio chunk ids)
    """
    chunk_id, max_depth, verbose = args

    work = WorkManager.from_existing(_worker_work_dir)
    generated_ids = []

    success = _process_chunk_recursive(
        work=work,
        engine=_worker_engine,
        chunk_id=chunk_id,
        voice_file=_worker_voice_file,
        max_depth=max_depth,
        current_depth=0,
        verbose=verbose,
        generated_ids=generated_ids,
    )

    return chunk_id, success, generated_ids


def _process_chunk_recursive(
    work: "WorkManager",
    engine,
    chunk_id: str,
    voice_file: Path | None,
    max_depth: int,
    current_depth: int,
    verbose: bool,
    generated_ids: list[str],
) -> bool:
    """Process a chunk with depth-based retry limiting.

    When a chunk fails and current_depth < max_depth, it splits the chunk
    and recursively processes sub-chunks with current_depth + 1.

    Args:
        work: WorkManager instance
        engine: TTS engine instance
        chunk_id: ID of the chunk to process
        voice_file: Optional voice sample path
        max_depth: Maximum split depth (from --max-retries CLI option)
        current_depth: Current recursion depth (0 for original chunks)
        verbose: Whether to print verbose output
        generated_ids: List to append generated audio chunk IDs to

    Returns:
        True if chunk (and all sub-chunks) processed successfully
    """
    text = work.load_chunk_text(chunk_id)

    try:
        audio = engine.generate(text, voice_sample=voice_file)
        audio_path = work.get_chunk_audio_path(chunk_id)
        save_chunk_wav(audio, engine.sample_rate, audio_path)
        work.set_chunk_status(chunk_id, "completed")
        generated_ids.append(chunk_id)
        return True

    except Exception as e:
        error_msg = str(e)
        if verbose:
            click.echo(
                f"\nChunk {chunk_id} failed (depth={current_depth}): {error_msg[:100]}"
            )

        if current_depth < max_depth:
            if verbose:
                click.echo(
                    f"Splitting chunk {chunk_id} (depth {current_depth} -> {current_depth + 1}, max={max_depth})..."
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
                    success = _process_chunk_recursive(
                        work=work,
                        engine=engine,
                        chunk_id=sub_id,
                        voice_file=voice_file,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        verbose=verbose,
                        generated_ids=generated_ids,
                    )
                    if not success:
                        all_success = False

                return all_success

        work.set_chunk_status(chunk_id, "failed", error=error_msg)
        return False


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

    for chunk_id in tqdm(pending, desc="Processing", unit="chunk"):
        generated_ids: list[str] = []
        _process_chunk_recursive(
            work=work,
            engine=engine,
            chunk_id=chunk_id,
            voice_file=voice_file,
            max_depth=max_retries,
            current_depth=0,
            verbose=verbose,
            generated_ids=generated_ids,
        )

    engine.unload()


def process_chunks_parallel(
    work: WorkManager,
    model: str,
    voice_file: Path | None,
    max_retries: int,
    workers: int,
    verbose: bool,
) -> None:
    """Process chunks in parallel using multiprocessing.Pool.

    Each worker process loads its own TTS model instance to avoid
    thread-safety issues with shared model state.
    """
    pending = work.get_pending_chunks()
    total = len(pending)

    if verbose:
        click.echo(f"Processing {total} chunks with {workers} worker processes")

    voice_file_str = str(voice_file) if voice_file else None
    work_dir_str = str(work.work_dir)

    tasks = [(chunk_id, max_retries, verbose) for chunk_id in pending]

    completed = 0
    failed = 0

    with Pool(
        processes=workers,
        initializer=_init_worker,
        initargs=(model, voice_file_str, work_dir_str),
    ) as pool:
        results = pool.imap_unordered(_process_chunk_in_worker, tasks)

        for chunk_id, success, generated_ids in tqdm(
            results, total=total, desc="Processing", unit="chunk"
        ):
            if success:
                completed += 1
            else:
                failed += 1

    if verbose:
        click.echo(
            f"\nParallel processing complete: {completed} succeeded, {failed} failed"
        )


if __name__ == "__main__":
    main()
