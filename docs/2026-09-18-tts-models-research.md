# Open-weight TTS for long-form audiobook narration — research, 2026-09-18

Scope: candidates for a fourth `toni` engine, judged on Russian + English long-form narration with
voice cloning, on Apple Silicon (MPS) and an RTX 3080 Ti 12 GB. Every factual claim carries a URL.
Where a figure is not published, this document says so rather than estimating.

---

## 1. Summary

**No model released since OmniVoice beats it on Russian, and the best available evidence says so
directly.** On MiniMax-Multilingual-24 — the only test set where two open models publish a Russian
row against shared baselines — OmniVoice scores **WER 2.233 / SIM-o 0.783** against Qwen3-TTS's
**3.212 / 0.792**, ElevenLabs 3.878 and MiniMax 4.281
([OmniVoice paper Table 3](https://arxiv.org/pdf/2604.00688),
[Qwen3-TTS report Table 6](https://arxiv.org/html/2601.15621v1)). OmniVoice also has 20,338 h of
Russian training audio, the largest disclosed pool of any open model
([languages.md](https://github.com/k2-fsa/OmniVoice/blob/master/docs/languages.md)).

**The real Russian defect is not the model — it is ударение.** OmniVoice ignores stress marks and
gives the *same word different stress on different generations*
([#129](https://github.com/k2-fsa/OmniVoice/issues/129), open, unanswered). Over a book that is a
recurring homograph error with no recourse. Fixing it is a text-preprocessing change, not an engine
swap: **`silero-stress`** (MIT, homograph F1 0.92) or **RUAccent** (MIT)
([silero-stress](https://github.com/snakers4/silero-stress), [RUAccent](https://github.com/Den4ikAI/ruaccent)).

**Top additions, in order:**
1. **A stress preprocessor** — biggest quality gain per unit of work, helps every engine.
2. **ESpeech-TTS-1** as the fourth engine: Apache-2.0, Russian-native, zero-shot cloning, honours
   `+` stress marks, and tops the only published Russian MOS table (NISQA 4.80–4.85, vs base XTTS
   2.85) ([RuASD Table 2](https://arxiv.org/html/2604.02374)). Installs through `f5-tts`, which is
   torch-2.8 clean.
3. **Qwen3-TTS** if the CC-BY-NC weights licence ever becomes a problem — Apache-2.0, Russian WER
   3.212 ([repo](https://github.com/QwenLM/Qwen3-TTS)).

**English: nothing clearly beats OmniVoice.** It leads IndexTTS2, CosyVoice3, Qwen3-TTS and F5-TTS
on LibriSpeech-PC (SIM-o 0.729 / WER 1.30) and Seed-en SIM-o
([paper Table 1](https://arxiv.org/pdf/2604.00688)). Arena preference boards rank Fish S2 Pro and
Breeze TTS 2 higher, but OmniVoice is not entered in either, so the comparison does not exist.

---

## 2. Comparison table

Serious candidates only. "—" means the figure is not stated in any primary source found.

| Model | License (commercial?) | Params | Languages / Russian | Cloning | VRAM | Speed | MPS | Long-form |
|---|---|---|---|---|---|---|---|---|
| **OmniVoice 0.2.1** (baseline) | code Apache-2.0; **weights CC-BY-NC** ❌ | 0.6B backbone / 0.8B total | 646 langs; **ru = 20,338 h, WER 2.233, FLEURS CER 1.10%** | ref 3–10 s | ~3.1–3.4 GB (3rd-party) | RTF 0.0319 @16 steps (H20) | ✅ official | no cross-chunk prosody; **stress uncontrollable** |
| **ESpeech-TTS-1** | **Apache-2.0** ✅ | ~0.34B (F5-TTS arch) | **Russian-native** | ref ≤12 s **+ ref text** | — | see F5-TTS | via F5-TTS fallback | `+` stress marks; NISQA MOS 4.80–4.85 |
| **Qwen3-TTS 12Hz** | **Apache-2.0** ✅ | 0.6B / 1.7B | 10 langs; **ru WER 3.212 / SIM 0.792** | ref 3 s | — | 97 ms first packet | "possible, not optimised" | 500-token (~40 s) default cap; no stress marks |
| **F5-TTS** (+ ru fine-tunes) | code MIT; **weights CC-BY-NC** ❌ | 335.8M | zh/en official; **ru via community FT** | ref ≤12 s **+ ref text** | — | RTF 0.15 @16 NFE (RTX 3090) | unofficial, fallback | 30 s/pass incl. prompt; duration heuristic drifts |
| **Chatterbox Multilingual v3** | **MIT** ✅ (watermarked output) | 0.5B | 23 langs; **ru CER ≈3–5%** | ref ~10 s | — (fits) | — | ✅ buggy (leak) | hallucinates past ~350 chars; ru accent drift after ~5 gens |
| **MOSS-TTS-LT-v1.5** | **Apache-2.0** ✅ | 4B | 31 langs incl. **ru** | 1 ref clip | — (8B fits 8 GB via GGUF) | 8B ≈45% realtime on 4090 | ❌ CUDA only | ✅ **designed for 1 h single-pass** |
| **Fun-CosyVoice3-0.5B-2512** | **Apache-2.0** ✅ | 0.5B | 9 langs incl. **ru**; CV3-Eval ru WER 6.77→3.79 (DiffRO) | ref ≤30 s (+text unless cross-lingual) | — | 150 ms streaming | partial; MLX ports exist | **repetition regression vs CosyVoice2** |
| **VoxCPM2** | **Apache-2.0** ✅ | 2B | **ru WER 5.21%** (CV3-eval) | short clip | — | — | ✅ | — |
| **ZONOS2** | MIT (repo) / Apache-2.0 (site) — conflicting | 8B total / ~900M active | 33+ langs; **ru = Tier 2** | ECAPA-TDNN embedding | **unknown — issue #8 unanswered** | "4× prior model" | ❌ Linux+CUDA | ❌ **600 tokens / ~1 min cap**; audible drift at joins |
| **Fish OpenAudio S1-mini** | CC-BY-NC-SA ❌, gated | 0.5B | 13 langs incl. ru | 10–30 s | fits 12 GB | 500%+ realtime on 3080 Ti | ❌ Linux/WSL | — |
| **Fish S2-Pro** | Fish Research Licence ❌ | 4.56B | 80+ langs; **ru = Tier 2** | 10–30 s | ❌ **24 GB** | RTF 0.195 (H200) | ❌ | — |
| **Higgs Audio V3** | **Research / non-commercial** ❌ (creator grant) | ~4B | 102 langs; ru in sub-5 WER tier | zero-shot, ref text helps | 8-bit ≈6–7 GB; bf16 ≈11 GB | RTF 0.147 (H100) | MLX port only | 8,192-token context |
| **IndexTTS-2.5** | bilibili MULA ✅* | ~0.8B | zh/en/ja/es/ar — **no ru** | 1 ref clip, no text | ✅ ~6 GB | RTF 0.207 (4090); ~90% realtime on 3080 Ti | unofficial PRs | most stable per 3rd-party audiobook tool |
| **VibeVoice 1.5B** | MIT + research-only card | ~3B actual | **en/zh only — ru unsupported** | ref audio | — | — | — | ✅ 64K ctx ≈ 90 min single pass |
| **Kokoro 82M** | **Apache-2.0** ✅ | 82M | 9 langs — **no ru** | ❌ fixed voice packs | CPU-capable | 35–100× realtime | ✅ w/ fallback | 510-token cap, **silent truncation** |
| **Kyutai Pocket TTS** (current) | MIT / CC-BY-4.0 (conflicting) | 100M | 6 langs — **no ru** | ✅ wav, ungated | CPU | ~6× realtime, M4 CPU | ✅ | ✅ streaming, "infinitely long" |
| **Kani TTS 2** (current) | **LFM 1.0** (free under $10M rev.) | 400M | per-lang ckpts; **no ru** | 10–20 s | ~3 GB | RTF ~0.2 (5080) | v1 MLX only | ~40 s / ~3000 tokens |
| **XTTS v2** | **CPML** ❌ non-commercial | ~467M (unverified) | 17 langs incl. ru | ref ~6 s | ~2 GB fp16 | — | ❌ wontfix hang | 250-char warning, 400-token assert; end-of-sentence hallucination |

\* bilibili MULA permits commercial use below 100M MAU / RMB 1B revenue.

**Ruled out on language (no Russian):** Dia/Dia2, Orpheus, Sesame CSM, MeloTTS, Kyutai TTS 1.6B,
Spark-TTS, Step-Audio EditX, Llasa, NVIDIA Magpie-Multilingual, Breeze TTS 2, Higgs Audio v2.

---

## 3. Per-model notes

### OmniVoice 0.2.1 — the baseline, and still the Russian leader

Latest release **0.2.1, 2026-07-16**; nothing since
([releases](https://api.github.com/repos/k2-fsa/OmniVoice/releases), [PyPI](https://pypi.org/pypi/omnivoice/json)).
Code is Apache-2.0 but **the weights are CC-BY-NC** "due to constraints from its training data
(e.g., Emilia)" ([HF card](https://huggingface.co/k2-fsa/OmniVoice)) — five open issues ask for
commercial terms. 0.6B Qwen3-0.6B-Base backbone, 0.8B with the Higgs tokenizer, 24 kHz, 3–10 s
reference ([README](https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/README.md)).

Benchmarks ([paper](https://arxiv.org/pdf/2604.00688)): LibriSpeech-PC SIM-o **0.729** / WER **1.30**
— best in its Table 1, ahead of IndexTTS2 (0.700/2.35), CosyVoice3 (0.694/1.59), Qwen3-TTS
(0.704/1.60) and F5-TTS (0.655/1.89). Seed-en SIM-o 0.741, Seed-zh WER 0.84. CMOS 0.44 / SMOS 3.80.
Russian: MiniMax-Multilingual-24 **WER 2.233 / SIM-o 0.783**; FLEURS-102 Russian **CER 1.10%** vs
ground truth 1.68% ([paper](https://arxiv.org/html/2604.00688v3)).

The README pins `torch==2.8.0+cu128` (CUDA) and `torch==2.8.0` (Apple Silicon) — exactly the current
environment — but PyPI metadata only says `torch>=2.4`, and
[#267](https://github.com/k2-fsa/OmniVoice/issues/267) reports resolvers pulling torch 2.14/2.11, so
keep the explicit pin. MPS is officially supported via `device_map="mps"`. VRAM is not published;
third-party measurement puts generation at ~3.1–3.4 GB
([smeltcore](https://smeltcore.com/recipes/omnivoice-on-rtx-4060-ti-16gb-zero-shot-voice-cloning-across-646-languages-with-room-to-spare/)).

Long-form issues that matter, all open:
[#129](https://github.com/k2-fsa/OmniVoice/issues/129) Russian stress uncontrollable and
non-deterministic; [#241](https://github.com/k2-fsa/OmniVoice/issues/241) no context preservation
across sentences; [#245](https://github.com/k2-fsa/OmniVoice/issues/245) sentence endings cut off;
[#248](https://github.com/k2-fsa/OmniVoice/issues/248) inconsistent speaking speed in ~10% of
generations; [#253](https://github.com/k2-fsa/OmniVoice/issues/253) voice-clone text dropout;
[#256](https://github.com/k2-fsa/OmniVoice/issues/256) click at t=0. No chunking guidance is
documented anywhere.

### ESpeech-TTS-1 — the recommended fourth engine

Russian-native, F5-TTS/DiT architecture, **Apache-2.0**
([HF](https://huggingface.co/ESpeech/ESpeech-TTS-1_RL-V2)). Variants: SFT-95k, SFT-256k, RL-V1,
RL-V2, Podcaster. Trained on the ESpeech corpora — **3,200 h of podcasts at 44.1 kHz with word-level
timestamps** ([dataset](https://huggingface.co/datasets/ESpeech/ESpeech-podcasts)) plus 800 h of
webinars.

It is the only Russian-native open model with **zero-shot cloning** (ref audio ≤12 s + ref text);
Silero, Vosk-TTS, TeraTTS and RHVoice are all fixed-voice
([silero-models](https://github.com/snakers4/silero-models), [vosk-tts](https://github.com/alphacep/vosk-tts),
[TeraTTS](https://github.com/Tera2Space/TeraTTS)).

Quality evidence is the [RuASD paper, arXiv:2604.02374, 2026-04-27](https://arxiv.org/html/2604.02374),
Table 2 — a 37-system Russian table (Whisper-medium CER, **NISQA-predicted** MOS, not human):
ESpeech RL-V1 **CER 0.04 / MOS 4.85**, Podcaster 0.04/4.81, SFT-95k 0.04/4.83, RL-V2 0.05/4.80.
For context in the same table: Vosk-TTS 0.02/4.81, GPT-SoVITS 0.02/4.74, XTTS ru-finetune 0.05/4.60,
**base XTTS-v2 0.04/2.85**, Silero 0.04/3.27, FishTTS 0.61/2.50, cloud SaluteSpeech 0.02/4.86.
The authors call these "objective dataset descriptors (sanity checks)", not a leaderboard — treat
accordingly, but it is the only Russian comparison of this breadth that exists.

Critically for a book: it takes **explicit `+` stress marks** (`прив+ет`) and ships RUAccent
integration for automatic placement. Output sample rate is not separately stated on the card; the
F5-TTS/Vocos stack it is built on is 24 kHz ([F5-TTS](https://github.com/SWivid/F5-TTS)).
VRAM and RTF for ESpeech specifically: **not stated in sources** — inherit F5-TTS's figures
(RTF 0.15 at 16 NFE on an RTX 3090, [paper](https://arxiv.org/abs/2410.06885)).

### Qwen3-TTS — the permissive-licence fallback

Open weights are real: released **2026-01-22, Apache-2.0**, five checkpoints (12Hz-1.7B in
Base/CustomVoice/VoiceDesign, 12Hz-0.6B in Base/CustomVoice)
([GitHub](https://github.com/QwenLM/Qwen3-TTS),
[HF](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)). 10 languages including Russian,
3-second cloning, 24 kHz output (the "12Hz" is token rate), `pip install -U qwen-tts`, torch
unpinned. Russian **WER 4.458 (0.6B) / 3.212 (1.7B)**, SIM 0.781/0.792
([arXiv:2601.15621](https://arxiv.org/html/2601.15621v1)).

Three caveats. MPS and CPU are "possible but not optimized" — CUDA is the supported path. Default
max output is **500 tokens ≈ 40 s**, and long reference audio can cause EOS hangs
([ocdevel](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning)). And it shares OmniVoice's
stress problem, worse: the maintainers' own discussion states "Qwen-tts was trained without using
stress marks, so … every word is pronounced incorrectly", with за́мок/замо́к and ко́мпас/компа́с
mispronounced; a user trying `+` notation reported the result was *worse*
([discussion #185](https://github.com/QwenLM/Qwen3-TTS/discussions/185), no official response).
The paper's >10-minute seamless long-speech results are for the **25Hz-1.7B variant, which was not
released**. On human-preference arena it does poorly despite the objective numbers: Elo 925.86,
rank 28/92 ([Artificial Analysis](https://artificialanalysis.ai/text-to-speech/models/qwen3-tts-vc-realtime),
observed 2026-09-18).

### F5-TTS and the Russian fine-tune ecosystem

Code MIT, **official weights CC-BY-NC-4.0** ([HF](https://huggingface.co/SWivid/F5-TTS)). 335.8M
params, 24 kHz via Vocos. Cloning needs ref audio **plus its transcript** (`--ref_text`; empty
auto-transcribes with Whisper at extra VRAM cost). Repo limits, verbatim: reference "<12s", and
"Currently support 30s for a single generation… including both prompt and output audio" — so ~18 s
of speech per pass ([infer README](https://raw.githubusercontent.com/SWivid/F5-TTS/main/src/f5_tts/infer/README.md)).

Long-form failure mode is duration prediction, not acoustics: there is no duration model, only a
character-ratio estimate, and [#811](https://github.com/SWivid/F5-TTS/issues/811) documents it
degrading from 0.051 s/char at 42 chars to 0.006 at 374 — "so fast that it is not inaudible", no
maintainer response. [#753](https://github.com/SWivid/F5-TTS/issues/753) reports runaway acceleration
over ~54 minutes of audio. **Pin ≥1.1.22 (2026-07-23)**, which fixed an N× `fix_duration` blow-up
across chunks ([PR #1309](https://github.com/SWivid/F5-TTS/pull/1309)). Also
[#85](https://github.com/SWivid/F5-TTS/issues/85) reference-audio phrases leaking into output over
long generations, [#474](https://github.com/SWivid/F5-TTS/issues/474) random word insertion.

Torch is clean — constraint is `torch>=2.0.0` and the README's own NVIDIA example installs
`torch==2.8.0+cu128`. MPS is unofficial: `PYTORCH_ENABLE_MPS_FALLBACK=1` is hardcoded in
`utils_infer.py`; [#875](https://github.com/SWivid/F5-TTS/issues/875) (Core ML/MLX) was closed with
no answer. Adoption is the strongest in its class: 15,240 stars, 984,345 HF downloads/30 d
(2026-09-18).

Russian fine-tunes, all derived from NC base weights:
[Misha24-10/F5-TTS_RUSSIAN](https://huggingface.co/Misha24-10/F5-TTS_RUSSIAN) (CC-BY-NC-4.0, ~5,000 h
RU+EN, includes a `F5TTS_v1_Base_accent_tune` checkpoint trained on 100% stress-marked data, ~56 k
downloads/30 d), [hotstone228/F5-TTS-Russian](https://huggingface.co/hotstone228/F5-TTS-Russian)
(CC-BY-NC-SA-4.0), [TVI/f5-tts-ru-accent](https://huggingface.co/TVI/f5-tts-ru-accent) (claims
CC-BY-4.0 and ships ONNX, but is a derivative of NC weights — legally murky). For a permissive
licence, ESpeech-TTS-1 is the cleaner route to the same architecture.

### Chatterbox Multilingual v3 — MIT, Russian, but torch-hostile

**MIT**, commercial use allowed, not gated; every output carries an imperceptible PerTh watermark
([GitHub](https://github.com/resemble-ai/chatterbox),
[v3 blog](https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages)).
0.5B Llama backbone, v3 released 2026-06-10 with training data grown 25.6k → 36.7k hours. It is one
of only two models in this survey with a **published Russian error rate: CER ≈3–5%**, mid-tier
(best Italian/German 0.20%, worst Vietnamese 75.21%).

Two blockers. First, `pyproject.toml` **hard-pins `torch==2.6.0` and `torchaudio==2.6.0`** for
Python <3.14, plus `transformers==5.2.0`
([pyproject](https://raw.githubusercontent.com/resemble-ai/chatterbox/master/pyproject.toml)) — a
direct conflict with torch 2.8.0 requiring an isolated venv. Second, Russian degrades over a long
run: [#360](https://github.com/resemble-ai/chatterbox/issues/360) (open, no maintainer reply) reports
an English accent creeping in after ~5 consecutive Russian generations with "stress patterns become
incorrect"; [#358](https://github.com/resemble-ai/chatterbox/issues/358) reports Russian numerals
switching language; [#424](https://github.com/resemble-ai/chatterbox/issues/424) reports
hallucination past ~350 chars. Russian is not among the six languages given a dedicated
single-language pack. MPS is supported in code but leaks memory
([#218](https://github.com/resemble-ai/chatterbox/issues/218)). Signals: 26.5k stars, Artificial
Analysis Elo 1019 / rank #70; TTS Arena V2 Elo 1479 (observed 2026-09-18).

### MOSS-TTS v1.5 / Local-Transformer-v1.5 — the only genuinely long-form Russian option

**Apache-2.0** across the whole family ([GitHub](https://github.com/OpenMOSS/MOSS-TTS)). 31 languages
with Russian explicitly in the table; language is passed as a tag. v1.5 is 8B, Local-Transformer-v1.5
is 4B at **48 kHz stereo** — the highest fidelity here. Uniquely, it is *designed* for the job: the
card claims "Ultra-long Speech Generation (up to 1 hour) … designed for extended narration" with
consistent identity, plus inline `[pause 3.2s]` control. MOSS-TTSD extends single-pass length to
1700 s.

Honest caveats. The maintainer notes 1-hour training clips "are indeed rare, with most concentrated
in the 3–30 minute range" ([#75](https://github.com/OpenMOSS/MOSS-TTS/issues/75)) — expect
minutes-scale reliability, not guaranteed hours. It is **slow**: the 8B runs at ~45% of realtime on
an RTX 4090 at batch 1, ~80% at batch 2
([tts-audiobook-tool](https://github.com/zeropointnine/tts-audiobook-tool)), and
[#41](https://github.com/OpenMOSS/MOSS-TTS/issues/41) reports a single sentence taking ~1 minute on a
3090. There is **no Metal backend** — [#37](https://github.com/OpenMOSS/MOSS-TTS/issues/37) confirms
CUDA only, with llama.cpp/GGUF the only Mac route. And it pins `torch==2.9.1`/`transformers==5.0.0`,
though a torch-free `[llama-cpp-onnx]` install path sidesteps that entirely. No Russian WER is
published. Third-party average WER 9.40 / SS 68.56 is the weakest WER in IndexTTS-2.5's table
([IndexTTS-2.5 README](https://github.com/index-tts/index-tts)).

### CosyVoice 3 — Apache-2.0 and Russian, but a stability regression

Only **Fun-CosyVoice3-0.5B-2512** was released (Apache-2.0); the paper's 1.5B is not public, and no
"3.5" weights exist in the HF org ([GitHub](https://github.com/QwenAudio/CosyVoice),
[HF](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)). CosyVoice **3** adds Russian to
the 9-language list; CosyVoice **2** does not support it — the CV3-Eval table marks CosyVoice 2 as
"–" for Russian, while CosyVoice 3 scores **WER 6.77 → 3.79 with DiffRO** (0.5B)
([arXiv:2505.17589](https://arxiv.org/html/2505.17589v2)). 24 kHz, reference ≤30 s.

The problem is [#1703](https://github.com/QwenAudio/CosyVoice/issues/1703): zero-shot clones
"动不动就把某些句子重复一遍，完全没有CosyVoice2-0.5B稳定" — repeat sentences, far less stable than
CosyVoice2 — and the suggested prompt-format fix is reported not to work. `requirements.txt` pins
`torch==2.3.1`. MPS support is partial ([PR #1869](https://github.com/QwenAudio/CosyVoice/pull/1869)
still open); `mlx-community` ports exist. The PyPI package named `cosyvoice` is third-party, not
official.

### Others, briefly

**VoxCPM2** — Apache-2.0, 2B, 48 kHz, MPS, torch ≥2.5.0 with no upper pin, Russian WER 5.21% on
CV3-eval ([GitHub](https://github.com/OpenBMB/VoxCPM)). Worse Russian WER than OmniVoice and
Qwen3-TTS but a clean licence and clean deps; a reasonable third fallback.

**ZONOS2** (2026-06-12) — Russian is Tier 2 of 33+ languages, 44.1 kHz, 8B total / ~900M active MoE
([README](https://raw.githubusercontent.com/Zyphra/Zonos2/main/README.md)). Licence is reported as
MIT on the repo and Apache-2.0 on [Zyphra's page](https://www.zyphra.com/our-work/zonos2) —
conflicting. Disqualifying for books: generation is capped at **600 tokens / ~1 minute**, and
[#10](https://github.com/Zyphra/ZONOS2/issues/10) states plainly that "adjacent chunks still shift
audibly in timbre/energy/pacing at joins… for chapter-length narration, inter-chunk drift is the
single largest remaining quality problem". Linux+CUDA only; VRAM unknown —
[#8](https://github.com/Zyphra/ZONOS2/issues/8) has gone unanswered since 2026-06-22.

**Fish OpenAudio S1-mini / S2-Pro** — best-placed Chinese-lab models on the arenas (S2 Pro #2
open-weight, Elo 1121; S1 Mini #7, Elo 1041, observed 2026-09-18). Russian is listed (Tier 2 for S2).
But S1-mini is CC-BY-NC-SA and gated, S2-Pro is under a research-only licence needing **24 GB VRAM**
([install docs](https://speech.fish.audio/install/)), and RuASD measures FishTTS Russian at
**CER 0.61 / MOS 2.50** — near the bottom of its table. Notably, `pyproject.toml` pins exactly
`torch==2.8.0`.

**Higgs Audio V3** (2026-06-04, 4B, Qwen3-4B backbone) — 102 languages with Russian in the sub-5
WER/CER tier, 24 kHz, macro-avg WER/CER 3.61 ([HF](https://huggingface.co/bosonai/higgs-tts-3-4b),
[LMSYS](https://www.lmsys.org/blog/2026-06-04-higgs-audio-v3-tts/)). Licence is **research and
non-commercial** with a Creator Use Grant that permits monetised creative output with attribution —
adequate for personal audiobooks, not for a product. Needs 8-bit to be comfortable on 12 GB (bf16
≈11 GB). No pip package; served via SGLang-Omni. Higgs **v2** has no Russian and needs 24 GB.

**IndexTTS-2.5** (2026-08-10) is technically the best fit — ~6 GB VRAM, pins `torch==2.8.*`,
RTF 0.207 on a 4090, and is singled out by a third-party audiobook tool as reliable enough to skip
Whisper validation — but it supports only zh/en/ja/es/ar. **No Russian**, so it is a non-starter
([HF](https://huggingface.co/IndexTeam/IndexTTS-2.5)).

**VibeVoice** is architecturally ideal (64K context ≈ 90 min single pass) and explicitly excludes
Russian: "trained only on English and Chinese data; outputs in other languages are unsupported and
may be unintelligible" ([card](https://huggingface.co/microsoft/VibeVoice-1.5B)). Microsoft also
pulled the TTS code in Sept 2025 and the 7B remains disabled; community mirrors carry it
([vibevoice-community](https://github.com/vibevoice-community/VibeVoice)).

**XTTS v2** should not be added. Weights are under the non-commercial CPML, Coqui shut down, MPS is a
*wontfix* hang ([#3649](https://github.com/coqui-ai/TTS/issues/3649)), stress control is a *wontfix*
bug ([#4435](https://github.com/coqui-ai/TTS/issues/4435)), and base Russian scores **MOS 2.85** in
RuASD — the worst naturalness tier. Coqui's own 2024 evaluation said "XTTS2 results are much worse
than I expected" on Russian ([alphacephei](https://alphacephei.com/nsh/2024/07/12/russian-tts.html)).

**Confirmed to have no Russian**, so not evaluated further: Kokoro (open since Feb 2025,
[#76](https://github.com/hexgrad/kokoro/issues/76)), Orpheus (multilingual release is zh/hi/ko/es/it/fr/de),
Dia and Dia2, Sesame CSM, MeloTTS (no `russian.py`; [#244](https://github.com/myshell-ai/MeloTTS/issues/244)
reports Russian training failing), Kyutai TTS 1.6B (en/fr), Kyutai Pocket TTS (6 languages), Kani TTS
(per-language checkpoints for de/es/ko/zh/ar/ja/ky — **no `-ru`**), Spark-TTS, Llasa,
NVIDIA Magpie-Multilingual (which also removed voice cloning "for security reasons"),
Breeze TTS 2 (the #1 open-weight arena entry — non-commercial, en/zh, Linux-only).

### Leaderboards — and why they do not settle this

Artificial Analysis Speech Arena, open weights, observed **2026-09-18**: Breeze TTS 2 (1207),
Fish S2 Pro (1121), Step Audio EditX (1099), Voxtral TTS (1074), Kokoro (1061), Magpie-Multilingual
(1060), OpenAudio S1 Mini (1041), Maya1 (1041), Higgs V3 (1037), Chatterbox (1019)
([source](https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights)).
TTS Arena V2, observed **2026-09-18**: OpenAudio S2 1525, OpenAudio S1 1508, Chatterbox 1479,
Kokoro 1477, NeuTTS Max 1439 ([API](https://tts-agi-tts-arena-v2.hf.space/api/leaderboard)).

**Neither board lists OmniVoice**, and neither lists Qwen3-TTS in TTS Arena V2. Both are dominated by
English and Chinese preference voting; **no Russian-language TTS arena or Elo board exists**. The
Soniqo 2026 voice-cloning benchmark excludes Russian too
([source](https://soniqo.audio/blog/voice-cloning-benchmarks)). For this project the published WER/SIM
tables and RuASD are the only usable evidence.

### The stress problem, in one place

This is the highest-leverage finding. Models that **cannot** control Russian stress, all with open
unaddressed issues: OmniVoice ([#129](https://github.com/k2-fsa/OmniVoice/issues/129) — U+0301 and
`+` both ignored, SSML `<phoneme>` ignored, same word stressed differently on each generation),
Qwen3-TTS ([#185](https://github.com/QwenLM/Qwen3-TTS/discussions/185)), XTTS v2
([#4435](https://github.com/coqui-ai/TTS/issues/4435), *wontfix*), Chatterbox
([#360](https://github.com/resemble-ai/chatterbox/issues/360)).

Models that **do**: the Russian F5-TTS family and ESpeech-TTS-1 (`+` before the stressed vowel), and
Silero, which does it automatically.

Preprocessors, both MIT: **[silero-stress](https://github.com/snakers4/silero-stress)** — homograph
F1 **0.92**, 94% per-word homograph accuracy, 94% dataset accuracy, 60–70% on unknown words, ~0.5 ms
per word on one CPU thread; and **[RUAccent](https://github.com/Den4ikAI/ruaccent)** — dictionary
plus neural fallback, no published accuracy metrics, and the de-facto front-end for the Russian
F5-TTS forks. A working precedent exists in
[rusvoice](https://github.com/ilyautov/rusvoice) (Apache-2.0), which packages RUAccent with a lint
step and reports marking 98.3% of multi-syllable words.

Context for why so many 2024–2026 flagships have weak Russian: **Emilia, the dominant open
multilingual TTS corpus, contains no Russian at all** (en/zh/de/fr/ja/ko only,
[arXiv:2501.15907](https://arxiv.org/abs/2501.15907)). Common Voice ru is small — 253.69 h validated
as of cv-corpus-26.0, 2026-06-12
([Mozilla Data Collective](https://mozilladatacollective.com/datasets/cmqinj9g500vsnr07qf4hmr3j)).
The models with real Russian trained on other data: OmniVoice (20,338 h) and ESpeech (3,200 h of
podcasts).

---

## 4. Integration notes for toni

The `TTSEngine` contract is `name`, `sample_rate`, `max_chunk_chars`, `load()`, and
`generate(text, voice_sample, progress_callback) -> float32 1-D numpy`
(`src/toni/tts/base.py`), with engines isolated by mutually-exclusive `uv` extras
(`pyproject.toml` `[tool.uv] conflicts`).

**Do the stress layer first, and not as an engine.** It is text-in/text-out, benefits `omni` today,
and does not touch the engine interface at all — a preprocessing step ahead of chunking. `silero-stress`
is MIT, ~0.5 ms/word on CPU, and has published homograph accuracy; RUAccent is the alternative. This
is one dependency and one function call, versus a whole engine for a smaller gain.

**Fit against the interface:**

| Candidate | Fits `generate()`? | `sample_rate` | `max_chunk_chars` | Notes |
|---|---|---|---|---|
| **ESpeech-TTS-1** | ✅ | 24000 | ~200 | needs ref **text**; reuse the `TONI_OMNI_REF_TEXT` + Whisper-fallback pattern from `omni.py` |
| **Qwen3-TTS** | ✅ | 24000 | ~300 | 3 s ref, no transcript; CUDA-first, so MPS parity with `omni` is unlikely |
| **VoxCPM2** | ✅ | 48000 | — | clean deps, MPS; weakest published Russian WER of the three |
| Chatterbox ML v3 | ✅ but | — (24 k reported) | ~300 | torch 2.6.0 pin forces a separate venv; keep chunks under the ~350-char hallucination threshold |
| MOSS-TTS-LT-v1.5 | ✅ | 48000 | large | no MPS; torch 2.9.1 unless the `[llama-cpp-onnx]` path is used |
| IndexTTS-2.5 / VibeVoice / Kokoro | n/a | | | no Russian |

**`pyproject.toml` sketch for the recommended pair** (ESpeech rides on the `f5-tts` package, which is
the only serious candidate that installs cleanly alongside the existing torch 2.8.0 pin):

```toml
[project.optional-dependencies]
espeech = [
    "f5-tts>=1.1.22",
    "torch==2.8.0",
    "torchaudio==2.8.0",
    "soundfile>=0.12.1",
]
qwen = [
    "qwen-tts",
    "torch==2.8.0",
    "torchaudio==2.8.0",
    "soundfile>=0.12.1",
]

[tool.uv]
conflicts = [
    [{ extra = "pocket" }, { extra = "kani" }, { extra = "omni" }, { extra = "espeech" }, { extra = "qwen" }],
]
```

The stress preprocessor is a base dependency, not an extra, since it helps every engine:
`"silero-stress"` (or `"ruaccent"`) in `[project].dependencies`.

**Torch 2.8.0 compatibility, consolidated** — the deciding practical constraint:

- **Clean** (no conflict): `f5-tts` (its own README installs torch 2.8.0+cu128), `qwen-tts`,
  `omnivoice` (README pins exactly 2.8.0), `voxcpm` (≥2.5.0), `moshi`/Kyutai (≥2.2,<2.10),
  `pocket-tts` (≥2.5), `kani-tts-2` (2.0+, but hard-pins `transformers==4.56.0`), `coqui-tts` (≥2.2),
  `kokoro` (unpinned), IndexTTS-2.5 (`torch==2.8.*`), Fish Speech (`torch==2.8.0`).
- **Conflicts, needs an isolated venv**: Chatterbox (`torch==2.6.0`), MOSS-TTS (`2.9.1`),
  Step-Audio EditX (≥2.9.1), ZONOS2 (`torchaudio==2.9.1`), CosyVoice (`2.3.1`), Spark-TTS (`2.5.1`),
  Dia (`2.6.0`), Sesame CSM (`2.4.0`), Orpheus (via `vllm==0.7.3` → `torch==2.5.1`), Llasa (via
  `xcodec2` → `2.5.0`).

**Two pipeline safeguards worth adding regardless of engine**, both cheap and both catching documented
failure modes: compare each chunk's output duration against a character-count expectation (catches
F5-TTS/ESpeech duration-heuristic acceleration, [#811](https://github.com/SWivid/F5-TTS/issues/811),
and OmniVoice's ~10% speed inconsistency, [#248](https://github.com/k2-fsa/OmniVoice/issues/248)); and
Whisper-transcribe each chunk and compare against the input (catches dropped words,
[#253](https://github.com/k2-fsa/OmniVoice/issues/253), and cut-off sentence endings,
[#245](https://github.com/k2-fsa/OmniVoice/issues/245)). The repo already ships `toni-transcribe`.

**Licence note.** OmniVoice weights are CC-BY-NC, as are F5-TTS's official weights and all the
Russian F5-TTS fine-tunes. If `toni` output is ever commercial, the Apache-2.0 Russian-capable set is
ESpeech-TTS-1, Qwen3-TTS, VoxCPM2, MOSS-TTS and Fun-CosyVoice3 — and Chatterbox under MIT.

---

## 5. Sources

**Baseline / OmniVoice**
https://github.com/k2-fsa/OmniVoice ·
https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/README.md ·
https://huggingface.co/k2-fsa/OmniVoice ·
https://github.com/k2-fsa/OmniVoice/blob/master/docs/languages.md ·
https://api.github.com/repos/k2-fsa/OmniVoice/releases · https://pypi.org/pypi/omnivoice/json ·
https://arxiv.org/pdf/2604.00688 · https://arxiv.org/html/2604.00688v3 ·
issues /129 /241 /245 /248 /253 /256 /265 /267 at https://github.com/k2-fsa/OmniVoice/issues ·
https://smeltcore.com/recipes/omnivoice-on-rtx-4060-ti-16gb-zero-shot-voice-cloning-across-646-languages-with-room-to-spare/

**Russian-specific**
https://arxiv.org/html/2604.02374 (RuASD) · https://alphacephei.com/nsh/2024/07/12/russian-tts.html ·
https://huggingface.co/ESpeech/ESpeech-TTS-1_RL-V2 ·
https://huggingface.co/datasets/ESpeech/ESpeech-podcasts ·
https://github.com/snakers4/silero-models · https://github.com/snakers4/silero-stress ·
https://github.com/Den4ikAI/ruaccent · https://github.com/ilyautov/rusvoice ·
https://github.com/alphacep/vosk-tts · https://github.com/alphacep/awesome-russian-speech ·
https://github.com/Tera2Space/TeraTTS · https://habr.com/en/articles/961930/ ·
https://huggingface.co/Misha24-10/F5-TTS_RUSSIAN · https://huggingface.co/hotstone228/F5-TTS-Russian ·
https://huggingface.co/TVI/f5-tts-ru-accent · https://huggingface.co/omogr/xtts-ru-ipa ·
https://arxiv.org/abs/2501.15907 (Emilia, no Russian) ·
https://mozilladatacollective.com/datasets/cmqinj9g500vsnr07qf4hmr3j · https://www.openslr.org/114/

**Models**
https://github.com/QwenLM/Qwen3-TTS · https://arxiv.org/html/2601.15621v1 ·
https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice ·
https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning ·
https://github.com/SWivid/F5-TTS · https://arxiv.org/abs/2410.06885 ·
https://raw.githubusercontent.com/SWivid/F5-TTS/main/src/f5_tts/infer/README.md ·
https://pypi.org/pypi/f5-tts/json · https://huggingface.co/SWivid/F5-TTS ·
https://github.com/resemble-ai/chatterbox ·
https://raw.githubusercontent.com/resemble-ai/chatterbox/master/pyproject.toml ·
https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages ·
https://github.com/OpenMOSS/MOSS-TTS · https://github.com/OpenMOSS/MOSS-TTSD ·
https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5 · https://arxiv.org/abs/2603.18090 ·
https://github.com/QwenAudio/CosyVoice · https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512 ·
https://arxiv.org/html/2505.17589v2 · https://arxiv.org/abs/2412.10117 ·
https://github.com/OpenBMB/VoxCPM · https://pypi.org/pypi/voxcpm/json ·
https://github.com/Zyphra/Zonos2 · https://raw.githubusercontent.com/Zyphra/Zonos2/main/README.md ·
https://www.zyphra.com/our-work/zonos2 ·
https://github.com/fishaudio/fish-speech · https://huggingface.co/fishaudio/s2-pro ·
https://huggingface.co/fishaudio/openaudio-s1-mini · https://speech.fish.audio/install/ ·
https://huggingface.co/bosonai/higgs-tts-3-4b ·
https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base ·
https://www.lmsys.org/blog/2026-06-04-higgs-audio-v3-tts/ · https://github.com/timoncool/HiggsAudio-Studio ·
https://github.com/index-tts/index-tts · https://huggingface.co/IndexTeam/IndexTTS-2.5 ·
https://arxiv.org/html/2601.03888v2 ·
https://github.com/microsoft/VibeVoice · https://huggingface.co/microsoft/VibeVoice-1.5B ·
https://github.com/vibevoice-community/VibeVoice · https://huggingface.co/vibevoice/VibeVoice-7B ·
https://huggingface.co/coqui/XTTS-v2 · https://github.com/idiap/coqui-ai-TTS ·
https://pypi.org/project/coqui-tts/ · https://github.com/coqui-ai/TTS/issues/3649 ·
https://github.com/coqui-ai/TTS/issues/4435 · https://github.com/coqui-ai/TTS/discussions/4146 ·
https://huggingface.co/hexgrad/Kokoro-82M · https://github.com/hexgrad/kokoro ·
https://github.com/kyutai-labs/pocket-tts · https://huggingface.co/kyutai/tts-1.6b-en_fr ·
https://huggingface.co/nineninesix/kani-tts-2-en · https://www.liquid.ai/lfm-license ·
https://github.com/nari-labs/dia · https://github.com/nari-labs/dia2 ·
https://github.com/canopyai/Orpheus-TTS ·
https://huggingface.co/collections/canopylabs/orpheus-multilingual-research-release ·
https://huggingface.co/sesame/csm-1b · https://github.com/SesameAILabs/csm ·
https://github.com/myshell-ai/MeloTTS · https://github.com/myshell-ai/MeloTTS/issues/244 ·
https://github.com/SparkAudio/Spark-TTS · https://huggingface.co/SparkAudio/Spark-TTS-0.5B ·
https://github.com/stepfun-ai/Step-Audio-EditX · https://huggingface.co/HKUSTAudio/Llasa-3B ·
https://huggingface.co/nvidia/magpie_tts_multilingual_357m · https://huggingface.co/BreezeBlue/Breeze-TTS-2

**Leaderboards** (all observed 2026-09-18)
https://artificialanalysis.ai/text-to-speech/leaderboard ·
https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights ·
https://artificialanalysis.ai/text-to-speech/models/qwen3-tts-vc-realtime ·
https://tts-agi-tts-arena-v2.hf.space/api/leaderboard · https://soniqo.audio/blog/voice-cloning-benchmarks

**Third-party practical benchmarks**
https://github.com/zeropointnine/tts-audiobook-tool (consumer-GPU realtime ratios, updated 2026-09-16)
