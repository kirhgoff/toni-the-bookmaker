import numpy as np

from toni.tts.espeech import tighten_silence

SR = 24000


def tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def quiet_runs_ms(audio: np.ndarray) -> list[int]:
    quiet = np.abs(audio) <= 0.005
    runs, run = [], 0
    for q in quiet:
        run = run + 1 if q else (runs.append(run) or 0) if run else 0
    if run:
        runs.append(run)
    return [round(r / SR * 1000) for r in runs]


def test_edges_are_trimmed_and_long_gaps_capped():
    audio = np.concatenate([silence(1.0), tone(0.5), silence(1.2), tone(0.5), silence(0.8)])
    tightened = tighten_silence(audio, SR)
    runs = quiet_runs_ms(tightened)
    assert runs[0] <= 50 and runs[-1] <= 50
    assert max(runs) <= 300
    assert len(tightened) < len(audio)


def test_short_gaps_are_left_alone():
    audio = np.concatenate([tone(0.5), silence(0.2), tone(0.5)])
    assert len(tighten_silence(audio, SR)) == len(audio)


def test_pure_silence_is_bounded():
    assert len(tighten_silence(silence(3.0), SR)) <= int(0.3 * SR)
