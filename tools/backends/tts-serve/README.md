# tts-serve backend

Audition, lock and generate audio through a [tts-serve](https://github.com/scorbo2/tts-serve) server over HTTP,
so the GPU can be another machine. Select it per command with `--backend tts-serve`, or set `"ttsBackend": "tts-serve"`
in `website/assets/config.json`.

Server address, first match wins: env `TTS_SERVE_URL`, then `ttsServe.url` in `website/assets/config.json`, then
`http://127.0.0.1:7501`. Engine parameters go under `ttsServe.params` (names come from the server's `/capabilities`).
Two text options, both under `ttsServe`: `rawText` (default `false`) sends the story text as written, skipping the
phonetic substitutions and the em-dash rewrite, and `maxChunkChars` (default 400) is the longest piece sent in one
request. VoxCPM2 read a 416-character passage cleanly as one raw request; the substitution list was written for Qwen3.

```
python .claude/tools/audition-voice.py waterdeep-dragon-heist durnan --backend tts-serve
python .claude/tools/lock-voice.py waterdeep-dragon-heist durnan --wav <chosen_audition.wav> --backend tts-serve
python .claude/tools/generate-audio.py <campaign> <session> --backend tts-serve
```

| Step | What happens | Engine needed |
|------|--------------|---------------|
| audition | the voice description from the character file goes in parentheses before the intro text; no reference audio | one that designs voices: **VoxCPM2** |
| audition --reaudition | clones the locked WAV with its intro text as transcript | any cloning engine |
| lock | copies the chosen audition to `<slug>.wav` (no `.pt`); the intro text in the character file is its transcript | none |
| generate | one request per sentence chunk (350 chars max), cloned from the locked WAV; output resampled to 24 kHz | any cloning engine |

Differences from the local qwen3 backend: the server chooses the sampling settings, the reference clip is sent and
re-encoded on every request, and long text is chunked here because tts-serve has no `max_new_tokens` guard.
Qwen3-TTS and OmniVoice servers clone only, so auditioning against them fails with a clear message. Use
`server-setup.sh` to run a VoxCPM2 server on the GPU machine.
