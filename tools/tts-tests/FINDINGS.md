# TTS engine findings (Yagra tests)

Texts: `yagra-emotion-tests.md`. Runner: `run_engine_tests.py`. Takes and numbers: `results/<label>/`.
Reference for every clone: Yagra's VoxCPM-designed audition take 1 (seed 645, cfg 3.0) with its transcript. Seed 42.
Verdicts below are the DM's listening notes (2026-10-17); numbers are from the runner. One listener, one voice.

## Qwen3-TTS Base (Gamer, :7500 through the tunnel), plain text, T1 to T3 heard
- Does not sound like her when cloning a VoxCPM-designed clip (hypothesis: another engine's voice does not carry over).
- Emotions are read as words. The server has no instruction field or tags (params: text, reference, transcript, language,
  seed, x_vector_only_mode, temperature, top_p, repetition_penalty), so it cannot be steered.

## VoxCPM2 (laptop, :7501)
| Mode | Result |
|------|--------|
| clone **with transcript**, plain text with spelled-out sounds ("Ha! Ha ha ha!", "Ahem.") | her voice. **Laughter (T2) good, cough (T3) good, anger (T4) not angry enough** |
| clone **without transcript** + `(direction)` prefix | not her voice at all. The transcript is what holds the voice |
| clone with transcript **+ `(direction)` prefix** | the direction is spoken aloud. Prefixes only work in design mode (no reference clip) |
| anger levers on T4 (clone + transcript) | **V1** CAPS + `?!` (cfg 2.0) and **V3** CAPS + `?!` + cfg 3.5 were the best; V2 (cfg 3.5, original text) was not picked |

- cfg 3.5 raises the level during a take (V3 raw -27 to -14 dBFS, V2 -34 to -20, one clipped sample each); V1 stays level.
  Design mode at cfg 3.5 clipped badly and drifted louder; 3.0 is the design default in the tts-serve backend.
- Speed about 0.55 x real time (RTX 5090 laptop). A 416-character passage in one request stayed level and clean.
- Voice design: the voice depends on the text and seed together (seed 645 only reproduces with the same text), so
  keep `design_text` fixed per character.
- Not judged: the angry-reference approach (`results/voxcpm-emotion-refs/`), T1 and T5 on VoxCPM, T4/T5 on Qwen3.

## Chatterbox multilingual v3 (Gamer, :7500), reference = take 1, no transcript (the server takes none)
- **Not her voice at all, and the laugh is "super fake"** (T2, tagged and plain). Verdict from the DM; the other takes
  (T1, T3 to T5, results in `results/chatterbox-*`) were saved but not played.
- It conditions on a speaker embedding from the first 10 s of the clip, with no transcript. Faster than VoxCPM
  (about 0.37 x real time) but the raw takes clip (up to 44 samples) and the output is watermarked.
- This server is v3 multilingual, not Chatterbox Turbo, so the guide's `[laugh]`/`[cough]` tags are unverified here.
- Pattern so far: engines that **continue from the reference audio** (VoxCPM2 with transcript) kept the designed voice;
  engines that build a **speaker embedding** (Qwen3 Base, Chatterbox) did not.

## dots.tts-soar (Gamer, :7500), clone + transcript, plain text, seed 42
- **Voice closer to her than VoxCPM's** (DM). Laugh "similar" to VoxCPM's ("in between" real laughter and spoken ha ha).
- **Cough: the word "ahem"** (VoxCPM's was a real cough). **Anger: not really** on plain text (VoxCPM's was weak too).
- Slow: about 1.0 to 1.2 x real time on Gamer's 12 GB GPU (VoxCPM 0.55 on the laptop). 48 kHz, no watermark.
- Parameters: `guidance_scale` (1.2), `speaker_scale` (1.5), `num_steps` (10), optional transcript. Anger variants with
  CAPS and `?!` (default and guidance 2.5) are in `results/dots-anger-variants/`.

## Breeze TTS 2 (Gamer, :7500; model page huggingface.co/BreezeBlue/Breeze-TTS-2), clone + transcript, seed 42
- Tags in parentheses: `(laugh)`, `(cough)`, `(clears throat)`, `(sigh)`. A separate `instruction` field steers tone,
  emotion and pace while keeping the speaker (`cfg_scale` 4 recommended; it is not spoken aloud). Transcript required.
- **Voice good, no fade-out at the end** (DM). The runner's very low end-of-clip levels (-33 to -59 dBFS) were trailing
  silence, not an audible fade: that metric misleads for this engine.
- **T2 laughter (clone, two `(laugh)` tags): the first was only a breath, "an inner laugh", the second a real laugh.**
  The same tag gives different results depending on context; one tag does not guarantee an outright laugh.
- Slowest: about 1.5 x real time on Gamer's 12 GB GPU (7.7 GiB reported for normal inference). 24 kHz, no watermark.
- Weights are non-commercial / research only (model page); fine for a home table, a problem if audio is published.
- **T3 cough: `(cough)` and `(clears throat)` sounded alike, a throat clear, but a genuine sound** (not a word).
- **T4 anger via the `instruction` field: the anger is really there**, in how she says it, not in volume (the take is
  level-matched for playback, and the instruction asked for a lower, harder voice rather than a louder one).
- Not judged: T1/T5, and `breeze-instruction` T2.

### Breeze voice design (Breeze's own API on :7860, not tts-serve)
- tts-serve's Breeze wrapper requires a reference clip and transcript, so design is not available through it; Breeze's own
  `python -m breeze_infer.api <checkpoint> --port 7860` (`POST /v1/audio/speech`: text, instruction, cfg_scale, seed; raw
  24 kHz PCM) does it. It takes about 1.5 x real time and cannot share Gamer's 12 GB GPU with the tts-serve Breeze.
- Yagra with her short description, cfg_scale 4, seeds 645 to 648: **"perfect for all 4"** (DM). **Seed 648 was chosen
  and locked as her voice** (2026-10-17): faster than the first three, 9.2 s. Old Qwen3 voice files are in git history.

### Decision (2026-10-17): the split
- **Live voices in TalkWithMe: VoxCPM2 on the laptop (:7501)**: fast (0.55 x real time), Apache-2.0, keeps the voice from a
  reference clip. TalkWithMe's `settings.yaml` TTS now points at 7501.
- **Auditioning and website media (scenes, memoirs): Breeze TTS 2 on Gamer.** Needs its own backend: Breeze's API
  (`/v1/audio/speech`) is not the tts-serve `/synthesize` contract, and design is only in Breeze's own server.
- VoxCPM2 cloning from a Breeze-designed reference works, but it starts clones with 0.5 to 1.5 s of digital silence (it
  reproduces the reference's lead-in: a 0.2 s playback lead-in became 1.3 s). Fixes in place: references are locked tight
  (no lead-in, `tighten_reference`) and `generate-audio` trims silence per chunk (`trim_silence`). A patch that trimmed
  TalkWithMe's `/api/tts` replies was **reverted at the DM's request**: TalkWithMe stays unmodified, and the lead-in the DM
  hears on live replies is whatever VoxCPM produces (0.5 to 1.5 s). The DM wants a lead-in (the Bluetooth speaker swallows
  the start of audio that begins immediately; 0.5 s of silence in front sounded right).

### Layout as of 2026-10-17 (evening) and a seed caveat
- Laptop: TalkWithMe (:8010), Breeze API (:7861, same model digest as Gamer's, no flash-attn). Gamer: Whisper (:8181) and
  VoxCPM2 through tts-serve (:7500, tunnel). TalkWithMe's TTS setting is back at `localhost:7500` (the VoxCPM on Gamer).
- **A seed does not reproduce a Breeze voice across machines**: Yagra's design settings (same text, instruction, cfg 4,
  seed 648) gave an 11.0 s take on the laptop (1.77 x real time) against 9.0 s on Gamer, waveform correlation 0.02. The
  locked WAV is what keeps her voice; `design_seed` only re-finds a voice on the machine that made it.

## Scorecard (DM's ears, Yagra clone of take 1; ratings are plain-language, not scores)
| Engine | Her voice | Laugh | Cough | Anger | Speed (x real time) |
|--------|-----------|-------|-------|-------|---------------------|
| Qwen3 Base | no | words | words | not heard | not timed (Gamer) |
| Chatterbox multilingual v3 | no | fake | not heard | not heard | 0.37 |
| VoxCPM2 (clone + transcript) | yes | good | good | weak; CAPS and `?!` help | 0.55 |
| dots.tts-soar | closest | in between | the word "ahem" | not really | 1.0 to 1.2 |
| Breeze TTS 2 | good | breath or real, depends on context | genuine throat clear | yes, via `instruction` | 1.5 |

Offline audio (scenes, memoirs) can wait for Breeze's speed; live NPC replies in TalkWithMe cannot (about 25 s per
17 s line). Breeze weights are non-commercial only.

## Not tested yet
Chatterbox Turbo if a tts-serve server for it exists; dots `speaker_scale`; dots T1/T5 beyond the notes above.
