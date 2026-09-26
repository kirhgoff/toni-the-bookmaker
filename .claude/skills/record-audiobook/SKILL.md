---
name: record-audiobook
description: Record an audiobook from a text or PDF file using the toni TTS pipeline, optionally cloning a voice from a sample. Use when the user wants to generate, record, or produce an audiobook, narrate a book or text file, resume an interrupted audiobook render, or check on a running one.
---

# Record an audiobook

One script does everything. Do not perform its steps by hand. Render on the GPU host by default; the local Mac is the fallback.

## Steps

1. **Inspect the source.** `file BOOK.txt` must say UTF-8; older `.txt` files are often in a legacy encoding (KOI8-R, CP1251, Windows-1252), so convert first with `iconv`. Note the language and the chapter heading style (see [Chapters](#chapters)). For a PDF or an OCR'd scan, run the `prepare-text` skill first and pass the cleaned `.txt`.
2. **Check the GPU host.** Hosts live in the untracked `hosts.local.json` at the repo root (shape in `hosts.example.json`); the first entry is the default. Probe it:
   ```bash
   jq -r 'to_entries[0] | "\(.key) \(.value.ssh) \(.value.identity)"' hosts.local.json
   ssh -i ~/IDENTITY -o ConnectTimeout=5 SSH_TARGET true && echo reachable
   ```
3. **Render.** Reachable:
   ```bash
   scripts/record_audiobook.sh -i BOOK.txt -v VOICE.wav -l LANG -H HOST -d
   ```
   Unreachable, or the user asks for local: drop `-H HOST`. Set `-l` to the text's language every time; the default is `en`, and the default engine speaks whatever `-l` says.
4. **Confirm it started.** Wait for `Processing:` in `render.log`; a traceback before that means the run is dead (see [Remote rendering](#remote-gpu-rendering)).
5. **Verify the output** once `Done:` appears (see [Verifying output](#verifying-output)).

`-d` detaches the run so it survives the terminal, this session, and machine idle-sleep. A novel takes hours, so `-d` is almost always right.

Everything lands in `<output-dir>/<name>/` (default `~/Downloads/audiobooks`). The book folder holds the shared inputs; each render gets its own run folder named `<timestamp>-<tag>`, where the tag is `-t` or, by default, `<model>-<host or local>`:

```
source.txt                cleaned text actually narrated
voice_ref.wav              trimmed voice reference
voice_ref.txt              its transcript
2026-01-15-1430-omni-tomhat/   one run
  <name>.m4b                finished audiobook, with chapters
  render.log                progress and errors
  work/                      resumable chunk state (deletable when done)
```

## What the script handles automatically

Each of these was a manual step that went wrong at least once:

- **Project Gutenberg boilerplate** — header and license footer stripped. Left in, the narrator reads ~20 minutes of legalese.
- **Voice reference length** — trimmed at silence to ~7s. The reference is prepended as conditioning to *every* generation, so a 30s sample makes the whole render dramatically slower. The library recommends 3–10s.
- **Reference transcript** — transcribed once up front. Without it each worker process loads Whisper large-v3-turbo (~1.6 GB).
- **Bitrate** — 64k mono, matching commercial audiobooks.
- **Detached execution** — `nohup` + `caffeinate` so a closed session or idle Mac doesn't kill the job.
- **Chapters** — headings detected in the text and embedded as real chapter marks, with offsets computed from rendered audio durations.
- **Decode and loudness** — after the encode the book is decoded end to end and its integrated loudness measured; more than 2 LU off -18 LUFS (a -37 dB clone sample once produced a -39 dB book) and it's re-encoded through loudnorm with chapters kept.
- **Zero chapters** in an m4b are flagged in the log.

## Options

| Flag | Default | Notes |
|---|---|---|
| `-i` | required | Source `.txt` or `.pdf` |
| `-v` | none | Voice to clone. Omit for a designed voice — it re-rolls per worker, so pass a sample for a consistent narrator. |
| `-l` | en | Language of the text. Always set it. |
| `-H` | none | Remote GPU host from `hosts.local.json`. Use by default. |
| `-m` | omni | Engine. `omni` speaks 600+ languages; `espeech` and `qwen` also speak Russian; `pocket` and `kani` are English only. |
| `-n` | input stem | Output folder name |
| `-t` | `<model>-<host or local>` | Run folder suffix saying what the run was about, e.g. `-t slower-speed` |
| `-o` | `$AUDIOBOOK_LIBRARY` or `~/Downloads/audiobooks` | Library folder that holds all books |
| `-w` | 2 | Workers. Each loads its own model onto the same GPU; leave at 2. |
| `-b` | 64k | Bitrate |
| `-p` | 500 | Pause in ms between sentences and chunks; lower it if the narration drags |
| `-f` | m4b | `m4b` (AAC, chapters) or `mp3` (no chapters) |
| `-c` | see below | Chapter heading regex |
| `-d` | off | Detach |

## Checking on a run

```bash
tr '\r' '\n' < ~/Downloads/audiobooks/<name>/<run>/render.log | tail -5
pgrep -fl "record/index.ts"      # still alive?
```

The ETA is unreliable early on; per-chunk cost drifts upward as it settles.

## Resuming

Re-run the identical command. If the book's latest run folder with the same tag has no finished output yet, it's reused: the manifest is read, completed chunks are skipped, and rendering continues. If the latest run already finished, a fresh run folder is created instead — nothing is overwritten. Manifest writes are flock-protected and atomic, so interruption is safe.

## Verifying output

Decode and loudness are checked automatically after every render. For chapters, duration, failed chunks, and long pauses, use the `verify-audiobook` skill. `scripts/normalize_audiobook.sh BOOK.m4b` re-checks loudness for any existing file.

## Expectations

Chunk cost on an RTX 3080 Ti is roughly a third of Apple Silicon (RTF 0.112 vs 0.38). A 190k-word novel is ~7,000 chunks: ~2 hours remote, ~6 hours locally, producing ~18 hours of audio at ~520 MB. Russian chunks run slower than English (~9s each locally at 2 workers). CPU-only is 8× slower again, so never render on a CPU server.

## Chapters

`-c` (a regex, passed through as `--chapter-pattern`) is matched against the start of each chunk. The default covers `PART`/`BOOK`/`CHAPTER`/`SECTION`/`PROLOGUE`/`EPILOGUE` in either case. Check what the book uses before rendering:

```bash
grep -cE "^(PART|BOOK|CHAPTER|Chapter)\b" source.txt
```

Zero matches means no chapters will be embedded; find the book's own heading style and pass it. A single short story legitimately has zero.

## Re-mastering without re-rendering

Format, bitrate and chapters are decided at concatenation. Delete the finished `<name>.m4b` from the run folder (or switch `-f`), then re-run the command with the new flags: the run is picked up again and only the final encode repeats.

## Remote GPU rendering

`-H HOST` ships `source.txt` and the voice reference over rsync, runs the render in a `toni:<model>` container with the GPU, and downloads the book back into the same output folder. Prep stays local.

- Before the render the host runs its `leaseAcquire` command to free VRAM and takes a flock, so a second concurrent render exits with "GPU is busy".
- Images are built on the host from a checkout of this repo; after changing `src/` or the `Dockerfile`, rsync those over and rebuild:
  ```bash
  podman build --build-arg EXTRA=<model> -t toni:<model> .
  ```
- **Crash signature:** `Cannot re-initialize CUDA in forked subprocess` in `render.log` with `ForkPoolWorker` respawning. The worker pool must use the spawn start method (it does since commit 1cdeb53); an image built before that fix loops forever. Kill the local `record/index.ts` process, `podman rm -f toni-<name>` on the host, rebuild, re-run.
- **Stalled renders:** on the tomhat GPU host (12 GB VRAM, Windows/WSL) two workers once filled VRAM to 11.5 GB and generation silently slowed to ~760 s/chunk — WSL spills VRAM into shared system memory instead of failing. One worker (`-w 1`) ran at ~1.3 s/chunk. Signature: progress stuck, GPU at 100% util, VRAM near full. Fix: kill the local `record/index.ts` process, `podman rm -f toni-<name>` on the host (via the host's configured shell, e.g. `ssh ... 'wsl -d Ubuntu -- bash -s' <<'EOF'`), re-run with `-w 1` — completed chunks are kept. Also: if the host sleeps or reboots, SSH drops ("Operation timed out") and the local driver exits; re-run the identical command to resume.
