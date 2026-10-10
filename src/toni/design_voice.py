"""Design a narrator voice once: generate one fixed sentence from the voice description."""

import os
from pathlib import Path

import click

from toni.audio_encoder import save_chunk_wav
from toni.seed import seed_everything
from toni.text_normalization import base_language

SENTENCES = {
    "en": "The old lighthouse keeper climbed the winding stairs every evening, "
    "and the quiet sea answered him with a slow, steady rhythm of waves.",
    "ru": "Старый смотритель маяка каждый вечер поднимался по винтовой лестнице, "
    "а тихое море отвечало ему мерным, спокойным шумом волн.",
}


def design_voice(language: str, seed: int, out: Path, text_out: Path) -> None:
    from toni.tts import get_engine

    sentence = SENTENCES[base_language(language)]
    os.environ["TONI_LANGUAGE"] = language
    engine = get_engine("omni")
    engine.load()
    seed_everything(seed)
    audio = engine.generate(sentence)
    engine.unload()
    save_chunk_wav(audio, engine.sample_rate, out)
    text_out.write_text(sentence, encoding="utf-8")


@click.command()
@click.option("--out", type=click.Path(path_type=Path), required=True, help="Reference WAV to write.")
@click.option("--text-out", type=click.Path(path_type=Path), required=True, help="Transcript to write.")
@click.option("--language", default="en", help=f"One of: {', '.join(SENTENCES)}.")
@click.option("--seed", type=int, default=0, help="Change it to draw a different narrator.")
def main(out: Path, text_out: Path, language: str, seed: int) -> None:
    if base_language(language) not in SENTENCES:
        raise click.BadParameter(f"no design sentence for '{language}'", param_hint="--language")
    design_voice(language, seed, out, text_out)


if __name__ == "__main__":
    main()
