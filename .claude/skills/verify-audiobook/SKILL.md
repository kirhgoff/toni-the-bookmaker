---
name: verify-audiobook
description: Check a rendered audiobook (.m4b or .mp3) and fix what is wrong - decode errors, loudness, chapters, duration, missing text, long pauses. Use when a render finishes, when the user asks to verify, check, or QA an audiobook, or says it is too quiet, has no chapters, is too short, or sounds off.
---

# Verify an audiobook

The driver already does this after every render, so a `Done:` line implies it passed: the file is decoded end to end with `ffmpeg -xerror`, its integrated loudness is measured, and it's re-encoded through two-pass `loudnorm` to -18 LUFS / -2 dBTP (chapters and metadata kept) whenever it's more than 2 LU off target, via a temp file and an atomic rename. An m4b with zero chapters gets a warning in the log.

For a file rendered before this existed, or any file you're unsure about:
```bash
scripts/normalize_audiobook.sh BOOK.m4b
```
It prints the measurement and only re-encodes when off target — safe to run repeatedly.

## Remaining checks

| Check | Command | Fix |
|---|---|---|
| Decode failure | message says "does not decode cleanly" | Delete `<name>.m4b` from the run folder and re-run the identical record command — only the encode repeats (see record-audiobook "Re-mastering without re-rendering"). |
| Loudness spot check | `ffmpeg -ss 1:00:00 -t 60 -i BOOK.m4b -af volumedetect -f null -` at a few offsets | Speech mean should sit around -25 dB; if not, re-run `normalize_audiobook.sh`. |
| Chapters | `ffprobe -v error -show_chapters -of json BOOK.m4b \| jq -r '.chapters[].tags.title'` vs `grep -cE '^Chapter [0-9]+\.$' source.txt` | Extra titles usually mean a paragraph starting with Part/Book/Section was matched — tighten `-c`. None means the heading style wasn't covered — pass `-c`. Either way, fix by re-mastering. |
| Missing text | `grep -c "chunks failed" render.log` | Failed chunks aren't retried on resume (`get_pending_chunks` in `src/toni/work_manager.py` only returns chunks marked `pending`, not `failed`). To retry, set their status to `pending` in `work/manifest.json` (local: the run folder; remote: under the host's workdir) and re-run. Otherwise tell the user which chunk texts are missing, in `work/chunks/<id>.txt`. |
| Duration sanity | hours vs `wc -w source.txt` / 150 / 60 | More than 25% short usually means missing chunks — see "Missing text" above. |
| Long pauses | `ffmpeg -i BOOK.m4b -af silencedetect=n=-40dB:d=2 -f null - 2>&1 \| grep -c silence_start` | A high count means re-master with a lower `-p`. |
| Listening spot check | `ffmpeg -ss 0:30:00 -t 20 -i BOOK.m4b clip.wav` at a few offsets | You can't listen — hand the clips to the user. |
