"""CLI entry point for Toni the Book Maker."""

import os
import shutil
import wave
from multiprocessing import get_context
from pathlib import Path
from typing import Callable

import click
import numpy as np
from tqdm import tqdm

from toni import __version__
from toni.audio_encoder import (
    DEFAULT_CHAPTER_PATTERN,
    concatenate_with_ffmpeg,
    load_chunk_wav,
    save_chunk_wav,
    wav_duration_ms,
)
from toni.chunker import chunk_with_marks, split_chunk
from toni.lexicon import load_lexicon
from toni.qc import (
    MIN_CHECKED_SECONDS,
    Thresholds,
    calibration_median,
    expected_seconds,
    verdict,
    word_error_rate,
)
from toni.seed import chunk_seed, seed_everything
from toni.text_extractor import extract_text
from toni.text_normalization import normalization_enabled, normalize_speech_text
from toni.tts import get_engine, list_engines
from toni.work_manager import WorkManager, run_fingerprint


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


_warned_speed_ignored = False


def _speed_kwargs(engine, speed: float | None) -> dict:
    global _warned_speed_ignored
    if speed is None:
        return {}
    if engine.supports_speed:
        return {"speed": speed}
    if not _warned_speed_ignored:
        click.echo(
            f"Warning: engine '{engine.name}' does not support [slow]; speed ignored",
            err=True,
        )
        _warned_speed_ignored = True
    return {}


def _finish_chunk(
    work: "WorkManager",
    engine,
    chunk_id: str,
    text: str,
    audio: np.ndarray,
    seed: int,
) -> None:
    save_chunk_wav(audio, engine.sample_rate, work.get_chunk_audio_path(chunk_id))
    work.publish_audio(chunk_id, text)
    work.set_chunk_status(chunk_id, "completed", seed=seed)


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
        seed = chunk_seed(work.load_manifest().seed, text, work.get_retries(chunk_id))
        seed_everything(seed)
        audio = engine.generate(
            text,
            voice_sample=voice_file,
            **_speed_kwargs(engine, work.get_chunk_speed(chunk_id)),
        )
        _finish_chunk(work, engine, chunk_id, text, audio, seed)
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


def _process_batch(
    work: "WorkManager",
    engine,
    ids: list[str],
    voice_file: Path | None,
    max_retries: int,
    verbose: bool,
) -> None:
    if len(ids) == 1:
        _process_chunk_recursive(work, engine, ids[0], voice_file, max_retries, 0, verbose, [])
        return
    texts = [work.load_chunk_text(cid) for cid in ids]
    seed = chunk_seed(work.load_manifest().seed, texts[0], work.get_retries(ids[0]))
    seed_everything(seed)
    try:
        audios = engine.generate_batch(
            texts,
            voice_sample=voice_file,
            **_speed_kwargs(engine, work.get_chunk_speed(ids[0])),
        )
    except Exception as e:
        if verbose:
            click.echo(f"\nBatch {ids} failed, rendering per chunk: {str(e)[:100]}")
        for cid in ids:
            _process_chunk_recursive(work, engine, cid, voice_file, max_retries, 0, verbose, [])
        return
    for cid, text, audio in zip(ids, texts, audios):
        _finish_chunk(work, engine, cid, text, audio, seed)


def _batches(work: "WorkManager", pending: list[str], width: int) -> list[list[str]]:
    by_speed: dict[float | None, list[str]] = {}
    for cid in pending:
        by_speed.setdefault(work.get_chunk_speed(cid), []).append(cid)
    batches = []
    for ids in by_speed.values():
        ordered = sorted(ids, key=lambda cid: len(work.load_chunk_text(cid)))
        batches += [ordered[i : i + width] for i in range(0, len(ordered), width)]
    return batches


def qc_pass(
    work: "WorkManager",
    transcriber: Callable[[np.ndarray, int], str],
    thresholds: Thresholds,
    qc_retries: int,
    max_retries: int,
    expected: Callable[[str, float | None], float],
    sample_rate: int,
    language: str | None = None,
) -> tuple[int, int, int]:
    heard = []
    for cid in work.get_unchecked_chunks():
        text = work.load_chunk_text(cid)
        audio = load_chunk_wav(work.get_chunk_audio_path(cid))
        seconds = expected(text, work.get_chunk_speed(cid))
        hypothesis = transcriber(audio, sample_rate)
        if normalization_enabled():
            hypothesis = normalize_speech_text(hypothesis, language)
        ratio = len(audio) / sample_rate / seconds if seconds else 1.0
        heard.append((cid, text, word_error_rate(text, hypothesis), ratio, seconds))

    median = calibration_median(
        [ratio for _, _, _, ratio, seconds in heard if seconds >= MIN_CHECKED_SECONDS]
        + _checked_ratios(work, expected)
    )
    checked = flipped = gave_up = 0
    for cid, text, wer, ratio, seconds in heard:
        result = verdict(wer, ratio, seconds, thresholds, median)
        retries = work.get_retries(cid)
        qc = {"wer": round(wer, 3), "ratio": round(ratio, 2), "attempts": retries, "verdict": result}
        checked += 1
        retry = result == "fail" and retries < qc_retries
        subs = split_chunk(text) if result == "fail" and not retry and cid.count("_") < max_retries else []
        splitting = len(subs) > 1
        work.set_chunk_status(cid, "pending" if retry else "completed", qc=qc)
        if retry or splitting:
            work.evict_cache(cid, text)
        else:
            work.publish_qc(cid, text, qc)
        if result == "fail":
            click.echo(f"QC fail {cid}: wer={wer:.2f} ratio={ratio:.2f} attempt={retries}")
        if retry:
            work.increment_retries(cid)
            flipped += 1
        elif splitting:
            for i, sub in enumerate(subs):
                work.add_sub_chunk(cid, f"{cid}_{i}", sub)
            flipped += 1
        elif result == "fail":
            gave_up += 1
    return checked, flipped, gave_up


def _checked_ratios(work: "WorkManager", expected: Callable[[str, float | None], float]) -> list[float]:
    return [
        data["qc"]["ratio"]
        for cid, data in work.load_manifest().chunks.items()
        if "qc" in data
        and expected(work.load_chunk_text(cid), work.get_chunk_speed(cid)) >= MIN_CHECKED_SECONDS
    ]


def _reference_seconds(voice_file: Path | None) -> float | None:
    if voice_file is None:
        return None
    try:
        return wav_duration_ms(voice_file) / 1000
    except (wave.Error, EOFError):
        return None


def _chunk_marks(chunk) -> dict:
    marks = {}
    if chunk.pause_ms:
        marks["pause_ms"] = chunk.pause_ms
    if chunk.speed is not None:
        marks["speed"] = chunk.speed
    return marks


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
    "--lexicon",
    "lexicon_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Pronunciation lexicon: one 'term = respelling' per line, # comments.",
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
    default="64k",
    help="MP3 bitrate. 64k matches commercial audiobooks; "
    "MP3 at 24kHz mono cannot exceed 160k.",
)
@click.option(
    "--chapter-pattern",
    type=str,
    default=DEFAULT_CHAPTER_PATTERN,
    help="Regex matching chapter headings. Chapters are embedded for .m4b output.",
)
@click.option(
    "--work-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom work directory base. Defaults to ./work/",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Shared per-book chunk cache; defaults to <work-dir>/cache.",
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
    "--seed",
    type=int,
    default=0,
    envvar="TONI_SEED",
    help="Base seed; same seed and text give the same audio.",
)
@click.option(
    "--batch",
    type=int,
    default=0,
    envvar="TONI_BATCH",
    help="Chunks per model call for engines that batch (0 = auto, max 16). "
    "Batching runs in one process.",
)
@click.option(
    "--qc/--no-qc",
    default=True,
    envvar="TONI_QC",
    help="Transcribe each chunk back and regenerate ones that skip or garble text.",
)
@click.option(
    "--qc-wer",
    type=float,
    default=0.25,
    envvar="TONI_QC_WER",
    help="Fail a chunk when its word error rate exceeds this.",
)
@click.option(
    "--qc-ratio-min",
    type=float,
    default=0.6,
    envvar="TONI_QC_RATIO_MIN",
    help="Fail a chunk shorter than this fraction of its expected duration.",
)
@click.option(
    "--qc-ratio-max",
    type=float,
    default=1.6,
    envvar="TONI_QC_RATIO_MAX",
    help="Fail a chunk longer than this multiple of its expected duration.",
)
@click.option(
    "--qc-retries",
    type=int,
    default=2,
    envvar="TONI_QC_RETRIES",
    help="Regenerations per failing chunk before it is split.",
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
    lexicon_file: Path | None,
    model: str,
    chunk_pause: int,
    bitrate: str,
    chapter_pattern: str,
    work_dir: Path | None,
    cache_dir: Path | None,
    max_retries: int,
    workers: int | None,
    seed: int,
    batch: int,
    qc: bool,
    qc_wer: float,
    qc_ratio_min: float,
    qc_ratio_max: float,
    qc_retries: int,
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

    os.environ["TONI_PAUSE_MS"] = str(chunk_pause)

    if verbose:
        click.echo(f"Input: {input_file}")
        click.echo(f"Output: {output_file}")
        click.echo(f"Model: {model}")
        click.echo(f"Workers: {workers}")
        click.echo(f"Seed: {seed}")
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
        if bad := work.reset_invalid_audio():
            click.echo(f"Re-rendering {len(bad)} truncated chunks")
    else:
        click.echo("Extracting text...")
        text = extract_text(input_file)

        if verbose:
            click.echo(f"Extracted {len(text)} characters")

        engine = get_engine(model)

        chunks = chunk_with_marks(
            text,
            max_chars=engine.max_chunk_chars,
            language=os.environ.get("TONI_LANGUAGE"),
            lexicon=load_lexicon(lexicon_file) if lexicon_file else None,
        )
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
            chunk_marks=[_chunk_marks(chunk) for chunk in chunks],
            seed=seed,
            fingerprint=run_fingerprint(model, copied_voice, seed),
            cache_dir=cache_dir or work_base / "cache",
        )

        for i, chunk in enumerate(chunks):
            work.save_chunk_text(str(i), chunk.text)
            if chunk.raw_text != chunk.text:
                work.save_chunk_raw_text(str(i), chunk.raw_text)

        reused = sum(
            work.restore_from_cache(str(i), chunk.text) for i, chunk in enumerate(chunks)
        )
        click.echo(f"Reused {reused} chunks from cache")

        click.echo(f"Saved {total_chunks} text chunks to {work.chunks_dir}")

        voice_file_for_tts = copied_voice
        engine.unload()

    width = min(batch or get_engine(manifest.model).batch_width(), 16)
    if width > 1 and workers > 1:
        click.echo("Engine batches in one process; --workers ignored")

    thresholds = Thresholds(qc_wer, qc_ratio_min, qc_ratio_max)
    ref_text = os.environ.get("TONI_REF_TEXT")
    ref_seconds = _reference_seconds(voice_file_for_tts) if ref_text else None
    base_speed = float(os.environ.get("TONI_OMNI_SPEED") or 1.0)

    def expected(text: str, chunk_speed: float | None) -> float:
        return expected_seconds(text, ref_text, ref_seconds, base_speed * (chunk_speed or 1.0))

    totals = [0, 0, 0]
    while True:
        render_pending(
            work, manifest.model, voice_file_for_tts, max_retries, workers, width, verbose
        )
        if not qc or not work.get_unchecked_chunks():
            break
        try:
            from toni.transcribe import load_transcriber

            transcriber = load_transcriber(os.environ.get("TONI_OMNI_DEVICE"))
        except ImportError:
            click.echo("QC skipped: transformers is not installed (install an engine extra such as omni)")
            break
        click.echo("Checking chunks with ASR...")
        counts = qc_pass(
            work, transcriber, thresholds, qc_retries, max_retries, expected, manifest.sample_rate,
            os.environ.get("TONI_LANGUAGE"),
        )
        del transcriber
        totals = [a + b for a, b in zip(totals, counts)]
        if not counts[1]:
            break
    if qc:
        click.echo(
            f"QC: {totals[0]} checked, {totals[1]} regenerated, "
            f"{totals[2]} still failing after retries"
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
    chunk_texts = [work.load_chunk_text(cid) for cid in audio_chunk_ids]
    heading_texts = [work.load_chunk_heading_text(cid) for cid in audio_chunk_ids]

    work_output = work.work_dir / f"output{output_file.suffix or '.mp3'}"
    chapter_count = concatenate_with_ffmpeg(
        audio_paths=audio_paths,
        output_path=work_output,
        sample_rate=manifest.sample_rate,
        pause_ms=manifest.chunk_pause_ms,
        bitrate=bitrate,
        work_dir=work.work_dir,
        chunk_texts=chunk_texts,
        heading_texts=heading_texts,
        chapter_pattern=chapter_pattern,
        extra_pauses_ms=work.get_extra_pauses(audio_chunk_ids),
    )
    if chapter_count:
        click.echo(f"Embedded {chapter_count} chapters")

    if output_file.resolve() != work_output.resolve():
        click.echo(f"Copying output to {output_file}...")
        shutil.copy2(work_output, output_file)

    total_duration_seconds = 0
    for audio_path in audio_paths:
        with wave.open(str(audio_path), "rb") as wf:
            total_duration_seconds += wf.getnframes() / wf.getframerate()

    duration_minutes = total_duration_seconds / 60

    click.echo(f"\nDone! Generated {duration_minutes:.1f} minutes of audio")
    click.echo(f"Output: {output_file}")
    click.echo(f"Work directory: {work.work_dir}")


def render_pending(
    work: WorkManager,
    model: str,
    voice_file: Path | None,
    max_retries: int,
    workers: int,
    width: int,
    verbose: bool,
) -> None:
    pending = work.get_pending_chunks()
    if not pending:
        click.echo("No pending chunks to process.")
        return
    click.echo(
        f"Processing {len(pending)} chunks with {workers} worker(s), batch {width}..."
    )
    if workers == 1 or width > 1:
        process_chunks_single(work, model, voice_file, max_retries, verbose, width)
    else:
        process_chunks_parallel(work, model, voice_file, max_retries, workers, verbose)


def process_chunks_single(
    work: WorkManager,
    model: str,
    voice_file: Path | None,
    max_retries: int,
    verbose: bool,
    width: int = 1,
) -> None:
    """Process pending chunks in one process, `width` chunks per model call."""
    engine = get_engine(model)
    engine.load()

    pending = work.get_pending_chunks()

    with tqdm(total=len(pending), desc="Processing", unit="chunk") as bar:
        for ids in _batches(work, pending, width):
            _process_batch(work, engine, ids, voice_file, max_retries, verbose)
            bar.update(len(ids))

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

    with get_context("spawn").Pool(
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
