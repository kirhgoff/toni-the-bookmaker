#!/usr/bin/env python3
"""Standalone smoke test for the OmniVoice TTS model (not wired into toni)."""

import argparse
import time
from pathlib import Path

import soundfile as sf
import torch
from omnivoice import OmniVoice
from omnivoice.models.omnivoice import OmniVoiceGenerationConfig

SAMPLE_RATE = 24000

TEXT = """
Арслан поднял меня, с пола, повернул к себе лицом и взял меня за руки, и в прямом смысле посадил на член гарика. Гарик только подправил свой член, и я сел на него... Он взял мои попку в руки, и начал на саживат на свой член... Опустая меня до самого упора и поднимая на головку.. Спереди подошел Арслан и вставил свой член мне в рот... Меня долбили во все мои дырки два мужественных кавказца, сегодня я был их соской и сучкой.. Они имели меня как только хотели.. Вдоволь напрыгался я на члене. Арслан снял меня с Гарика, повернул попкой к себе, так что я сидел на гарике к нему лицом, сидел у него на руках, а Арслан вошел в меня сзади, и с остервенением тращал меня на всю длину своего члена.... Потом они сжили меня.. Я был в объятиях двух кавказских зверей, один из которых откровенно имел меня в мою попку... Я уже не чувствовал боли, я просто хотел чтоб это продолжалось вечно...
"""

INSTRUCT = "male, middle-aged, low pitch"

VALID_INSTRUCT_ITEMS = (
    "male, female, child, teenager, young adult, middle-aged, elderly, "
    "very low pitch, low pitch, moderate pitch, high pitch, very high pitch, whisper, "
    "american/australian/british/canadian/chinese/indian/japanese/korean/portuguese/russian accent"
)


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    return "mps" if torch.backends.mps.is_available() else "cpu"


def pick_dtype(device: str) -> torch.dtype:
    return torch.float32 if device == "cpu" else torch.float16


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "mps", "cuda"],
        help="fall back to cpu if mps output sounds wrong",
    )
    parser.add_argument("--output", type=Path, default=Path("omnivoice_test.wav"))
    parser.add_argument("--text-file", type=Path, default=None)
    parser.add_argument("--ref-audio", type=Path, default=None)
    parser.add_argument("--ref-text", default=None)
    parser.add_argument(
        "--instruct",
        default=INSTRUCT,
        help=f"comma-separated, closed vocabulary: {VALID_INSTRUCT_ITEMS}",
    )
    parser.add_argument("--language", default="ru")
    parser.add_argument("--num-step", type=int, default=32)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--normalize-text", action="store_true")
    args = parser.parse_args()

    device = resolve_device(args.device)

    text = args.text_file.read_text(encoding="utf-8") if args.text_file else TEXT
    text = " ".join(text.split())
    if not text:
        raise SystemExit("No text to synthesize")

    print(f"Loading OmniVoice on {device}...")
    started = time.perf_counter()
    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        device_map=device,
        dtype=pick_dtype(device),
    )
    print(f"Loaded in {time.perf_counter() - started:.1f}s")

    kwargs = {
        "text": text,
        "language": args.language,
        "speed": args.speed,
        "normalize_text": args.normalize_text,
        "generation_config": OmniVoiceGenerationConfig(num_step=args.num_step),
    }
    if args.ref_audio:
        kwargs["ref_audio"] = str(args.ref_audio)
        if args.ref_text:
            kwargs["ref_text"] = args.ref_text
    elif args.instruct:
        kwargs["instruct"] = args.instruct

    print(f"Generating {len(text)} chars...")
    started = time.perf_counter()
    audio = model.generate(**kwargs)
    elapsed = time.perf_counter() - started

    samples = audio[0]
    sf.write(args.output, samples, SAMPLE_RATE)
    duration = len(samples) / SAMPLE_RATE
    print(f"Wrote {args.output} — {duration:.1f}s audio in {elapsed:.1f}s (RTF {elapsed / duration:.2f})")


if __name__ == "__main__":
    main()
