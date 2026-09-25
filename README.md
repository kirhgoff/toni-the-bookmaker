# Toni the Book Maker

Toni turns a text file or PDF into an audiobook. Feed it a book, optionally a
short sample of a voice, and it reads the whole thing out loud, cuts it into
chapters, and hands you back one finished audio file.

## Quick start

You'll need a few command-line tools first. On macOS, with [Homebrew](https://brew.sh) installed:

```bash
brew install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
brew install oven-sh/bun/bun
```

- **ffmpeg** does the audio trimming and encoding.
- **uv** manages the Python side (the TTS models themselves).
- **bun** runs the TypeScript side (the script that drives everything).

Then get the code and install the Python dependencies:

```bash
git clone https://github.com/kirhgoff/toni-the-bookmaker.git
cd toni-the-bookmaker
./install.sh
uv sync --extra omni
```

`install.sh` checks that `uv` and `ffmpeg` are present and installs the base
Python dependencies. The `uv sync --extra omni` step installs the actual
speech model — see [Choosing a voice](#choosing-a-voice) and
[Which engine](#which-engine) below for the alternatives.

Now record something:

```bash
scripts/record_audiobook.sh -i book.txt -v my_voice.wav -d
```

`-v my_voice.wav` clones a voice from that sample; drop it for a generic
narrator. `-d` runs the job in the background so it survives closing the
terminal or your Mac going to sleep — worth using, because a full novel takes
several hours.

Everything shows up in `~/Downloads/audiobooks/book/`. The book folder holds
the shared inputs; each render gets its own run folder, named by timestamp plus a
tag that says what the run was about (`-t`, or by default the engine and where it ran):

```
source.txt                   the cleaned text that was actually read
voice_ref.wav                 the trimmed voice sample
voice_ref.txt                 its transcript
2026-01-15-1430-omni-local/   one run
  book.m4b                 the finished audiobook, with chapters
  render.log               progress and any errors
  work/                     intermediate audio chunks (safe to delete once you're happy)
```

**Check progress** while it runs:

```bash
tail -f ~/Downloads/audiobooks/book/2026-01-15-1430-omni-local/render.log
```

**If it gets interrupted**, just run the exact same command again. If the
latest run folder with the same tag hasn't finished, it resumes there instead of starting over;
if the latest run already finished, a fresh run folder is created instead.

**How long it takes:** roughly 6 hours for a full-length novel on a Mac
(Apple Silicon), or about 2 hours if rendered on a remote GPU (see
[Remote rendering](#remote-gpu-rendering)). The progress bar's time estimate
is unreliable for the first while; it settles down as more chunks complete.

## Choosing a voice

Pass any short recording of a voice with `-v`. It doesn't need to be trimmed
yourself — the tool automatically cuts it down to a few seconds at a natural
pause (long samples make every single sentence of the audiobook slower to
generate, since the sample is replayed as a reference each time). It's also
transcribed once up front, so the actual narration doesn't need to keep
re-listening to figure out what the sample says.

If you don't pass `-v`, you get a synthesized narrator voice instead of a
clone. It's regenerated per worker process, so the voice can shift slightly
partway through — passing a sample avoids that.

## Languages

The default engine, `omni`, can narrate in any of 600+ languages — pass one
with `-l`, e.g. `-l ru` for Russian. `espeech` and `qwen` also support
Russian; `pocket` and `kani` only support English.

### Russian stress marking

Russian has no fixed stress rule, so a TTS model that cannot see the stressed
syllable in advance guesses, and gets it wrong on homographs (`з+амок` castle
vs `зам+ок` lock) and sometimes stresses the same word differently between
runs. `src/toni/stress.py` marks stress automatically with
[silero-stress](https://github.com/snakers4/silero-stress); install it with
`uv sync --extra stress` (or `--extra espeech`, which pulls it in). Only
`espeech` uses it today — it takes explicit `+`-before-vowel marks
(`прив+ет`) and applies them automatically to Russian text and reference
transcripts. `omni` ignores stress marks entirely, and `qwen` was trained
without them and does worse when given `+` notation, so neither is
stress-marked.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `-i, --input` | required | Source `.txt` or `.pdf` |
| `-v, --voice` | none | Voice sample to clone |
| `-n, --name` | input filename | Output folder name |
| `-t, --tag` | engine and host | Suffix for the run folder, e.g. `-t first-try` |
| `-o, --output-dir` | `~/Downloads/audiobooks` | Folder that holds all your books |
| `-w, --workers` | 2 | Parallel narration processes — don't raise this much, see [Troubleshooting](#troubleshooting) |
| `-b, --bitrate` | 64k | Audio bitrate |
| `-p, --pause` | 500 | Pause between sentences and chunks, in milliseconds |
| `-f, --format` | m4b | `m4b` (with chapters) or `mp3` (no chapters) |
| `-c, --chapters` | see below | Chapter heading pattern |
| `-l, --language` | en | Language code |
| `-m, --model` | omni | TTS engine: `omni`, `pocket`, `kani`, `espeech`, or `qwen` |
| `-H, --host` | none | Render on a remote GPU host instead of locally |
| `-d, --detach` | off | Run in the background |
| `-h, --help` | | Show this help |

Books land in `~/Downloads/audiobooks/<name>/` by default; change the folder
with `-o` or the `AUDIOBOOK_LIBRARY` environment variable.

## Remote GPU rendering

If you have access to a machine with an NVIDIA GPU, `-H <host>` sends the
actual narration there instead of running it on your Mac — it's noticeably
faster. Everything else (text cleanup, voice trimming) still happens locally;
only the slow part moves, and the finished book is copied back automatically.

The remote machine needs Docker or Podman with GPU access, and a container
image built from this repo:

```bash
podman build --build-arg EXTRA=omni -t toni:omni .
```

Hosts are defined in `hosts.local.json` at the repo root, which stays out of
git; copy `hosts.example.json` to get started.

## What's inside

- **Five speech engines**, each an optional Python dependency, only one
  installed at a time (see [Which engine](#which-engine)).
- **Whisper** (via the `omni` engine) transcribes your voice sample once, so
  the narration itself never needs to re-run speech recognition.
- **A text chunker** (`src/toni/chunker.py`) splits the book into
  sentence-sized pieces small enough for the speech model, and automatically
  re-splits and retries any piece that fails to generate.
- **ffmpeg**, driven from Python (`src/toni/audio_encoder.py`), stitches the
  generated pieces back together, detects chapter headings by pattern, and
  encodes the result as `.m4b` (with real chapter marks) or `.mp3`.
- **A Bun/TypeScript layer** (`src/record/`) is the part you actually run: it
  cleans up the source text, trims and transcribes the voice sample, can
  detach the job into the background, and can ship the job to a remote GPU
  machine over SSH.
- **Docker/Podman** package each engine as a container image so the remote
  GPU machine doesn't need Python set up by hand.

### Which engine

| Engine | Size | Languages | Runs on | Voice cloning | Licence |
|---|---|---|---|---|---|
| `omni` (OmniVoice, default) | 0.6B params | 600+, including Russian | Apple Silicon or NVIDIA GPU | Yes, from a short sample | code Apache-2.0, weights CC-BY-NC |
| `pocket` (Kyutai Pocket TTS) | 100M params | English only | CPU | Yes, from a short sample | MIT / CC-BY-4.0 |
| `kani` (Kani TTS 2) | 400M params | English only | NVIDIA GPU | Yes, via a speaker embedding | LFM 1.0 (free under $10M rev.) |
| `espeech` (ESpeech-TTS-1) | ~0.34B params | Russian only, stress-aware | Apple Silicon or NVIDIA GPU (unofficial MPS) | Yes, from a short sample + transcript | Apache-2.0 |
| `qwen` (Qwen3-TTS) | 1.7B params | 10, including Russian | NVIDIA GPU (CUDA-first; MPS/CPU untested) | Yes, from a short sample + transcript | Apache-2.0 |

## Project layout

```
src/
  toni/               Python — the speech models and audio pipeline
    cli.py            the underlying `toni` command
    tts/               registry.py, omni.py, pocket.py, kani.py, espeech.py, qwen.py
    stress.py          marks Russian word stress ahead of synthesis
    chunker.py         splits text into narratable pieces
    audio_encoder.py   stitches audio, embeds chapters, encodes output
    transcribe.py      transcribes a voice sample with Whisper
  record/             TypeScript — the one-command recorder you actually run
    index.ts           entry point, argument parsing
    prep.ts            text cleanup, voice sample trimming
    render.ts          runs the narration, locally or remotely
    hosts.ts           loads remote GPU hosts from hosts.local.json
scripts/
  record_audiobook.sh  thin wrapper around `bun src/record/index.ts`
```

There's also a lower-level way to run things directly, without the
convenience layer: `uv run python -m toni.cli -i book.txt -o book.mp3 -m
pocket`. It skips the automatic Gutenberg cleanup, voice trimming, and
chapter timing that `scripts/record_audiobook.sh` gives you for free, so
prefer the script unless you have a specific reason not to.

## Troubleshooting

- **No chapters appear in the output.** The chapter detector looks for lines
  starting with words like `CHAPTER` or `PART`. Check what your book actually
  uses (`grep -cE "^(PART|BOOK|CHAPTER|Chapter)\b" source.txt`) and pass your
  own pattern with `-c` if it comes back zero.
- **The time estimate looks wrong early on.** Per-chunk timing drifts as the
  run settles in; ignore the ETA for the first several minutes.
- **Don't raise `-w` (workers) much above 2.** Each worker loads its own copy
  of the speech model onto the same GPU or CPU, so more workers can make
  things slower, not faster.
- **"Done!" isn't proof the file is good** — the last step concatenates
  thousands of small audio pieces. Sanity-check it:
  ```bash
  ffmpeg -v error -i book.m4b -f null -    # silence means no corruption
  ffprobe -v error -print_format csv -show_chapters book.m4b | wc -l
  ```
- **It's extremely slow with no GPU or Apple Silicon.** CPU-only rendering is
  roughly 8 times slower — a full novel can take on the order of a week.
  Don't try this on a plain CPU server; use `-H` to render remotely instead.
