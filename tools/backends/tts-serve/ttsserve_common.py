"""Shared helpers for the tts-serve backend: character files, voice descriptions, text and audio utilities."""
import io
import json
import os
import re

SAMPLE_RATE = 24000  # generate-audio assembles and encodes at 24 kHz, like the other backends
MAX_CHUNK_CHARS = 400  # tts-serve has no max_new_tokens guard, so long text is split on sentence ends. 416 characters in one
#                        cloning request stayed level and clean on VoxCPM2; override with ttsServe.maxChunkChars
DESIGN_CFG = 3.0  # voice-design guidance: 2.0 (server default) is too weak and quiet, 3.5 clips and drifts louder
DESIGN_CHARS = 300  # audition on the first sentences of the intro (~15 s); VoxCPM wants a 3-10 s reference


def setting(name, default):
    """A value from `ttsServe` in website/assets/config.json (ttsServe.rawText, ttsServe.maxChunkChars)."""
    import ttsserve_client
    return ttsserve_client._config().get(name, default)


def find_character_file(campaign, slug):
    for path in (os.path.join("campaigns", campaign, "info", "npcs", f"{slug}.md"),
                 os.path.join("campaigns", campaign, "party", "characters", f"{slug}.md"),
                 os.path.join("campaigns", campaign, "info", "introductions", f"{slug}.md")):
        if os.path.exists(path):
            return path
    return None


def _section(content, name):
    m = re.search(rf"^## {name}\s*\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _field(text, key):
    m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def parse_introduction(path):
    """(name, voice description, intro text) from a unified NPC/PC file. Same description as the qwen3 backend."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if not re.search(r"^## character", content, re.MULTILINE):
        raise SystemExit(f"Error: could not parse {path}: expected a ## character section")
    char, voice = _section(content, "character"), _section(content, "voice")
    name, gender, age = _field(char, "name") or "Unknown", _field(char, "gender"), _field(char, "age")
    override = _field(voice, "instruction").strip("\"'")
    if override:
        instruct = override
    else:
        parts = []
        if gender and age:
            parts.append(f"{gender}, {age} years old")
        elif gender or age:
            parts.append(gender or f"{age} years old")
        parts += [v.rstrip(".") for v in (_field(voice, k) for k in ("pitch", "pace", "tone", "quality", "notes")) if v]
        instruct = ". ".join(parts) + "."
    body, in_body = [], False
    for line in voice.splitlines():
        if re.match(r"^\w[\w-]*:\s", line) or re.match(r'^instruction:\s*"', line):
            in_body = False
        elif line.strip() == "" and not in_body:
            continue
        else:
            in_body = True
            body.append(line)
    return name, instruct, "\n".join(body).strip()


def voice_fields(path):
    """Optional per-character design settings from the ## voice section: design, design_text, design_seed, design_cfg."""
    with open(path, encoding="utf-8") as f:
        voice = _section(f.read(), "voice")
    return {k: _field(voice, k).strip("\"'") for k in ("design", "design_text", "design_seed", "design_cfg")}


def design_excerpt(text, max_chars=DESIGN_CHARS):
    """The first whole sentences of the intro that fit in max_chars (at least one)."""
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if out and len(out) + 1 + len(sentence) > max_chars:
            break
        out = f"{out} {sentence}".strip()
    return out


def pause_text(text):
    """Text as sent in design mode: '...' between sentences gives clear pauses; em dashes become commas."""
    text = re.sub(r"\s*\u2014\s*", ", ", text)
    return re.sub(r"(?<=[a-z])\.\s+(?=[A-Z])", "... ", text)


def design_prefix(instruct):
    """VoxCPM voice design: the description goes in parentheses before the text, so strip any parentheses."""
    return "(" + " ".join(instruct.replace("(", ",").replace(")", ",").split()) + ")"


def phonetic_subs(campaign):
    path = os.path.join("campaigns", campaign, "party", "phonetic-substitutions.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {rf"\b{re.escape(k)}\b": v for k, v in json.load(f).items()}


def audition_text(campaign, body):
    """The intro text as spoken during auditions (substitutions applied); it is also the clip's transcript."""
    for pattern, replacement in phonetic_subs(campaign).items():
        body = re.sub(pattern, replacement, body, flags=re.IGNORECASE)
    return body


def sentence_chunks(text, max_chars=MAX_CHUNK_CHARS):
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text] if text else []
    chunks, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > max_chars:  # one very long sentence: break at a comma or space
            cut = max(sentence.rfind(", ", 0, max_chars), sentence.rfind(" ", 0, max_chars))
            cut = cut if cut > 0 else max_chars
            piece, sentence = sentence[:cut + 1].strip(), sentence[cut + 1:].strip()
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(piece)
        if cur and len(cur) + 1 + len(sentence) > max_chars:
            chunks.append(cur)
            cur = ""
        cur = f"{cur} {sentence}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def clip_to_array(clip, target_rate=SAMPLE_RATE):
    """Decode a Clip's WAV to mono float32 at target_rate (None keeps the server's rate)."""
    import soundfile as sf
    audio, rate = sf.read(io.BytesIO(clip.wav), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return resample(audio, rate, target_rate) if target_rate and rate != target_rate else audio


def resample(audio, rate_from, rate_to):
    import numpy as np
    try:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(rate_from), int(rate_to))
        return resample_poly(audio, int(rate_to) // g, int(rate_from) // g).astype("float32")
    except ImportError:  # no scipy: box-filter when downsampling, then linear interpolation
        if rate_to < rate_from:
            k = max(1, int(round(rate_from / rate_to)))
            audio = np.convolve(audio, np.ones(k, dtype="float32") / k, mode="same")
        n = int(round(len(audio) * rate_to / rate_from))
        return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype("float32")


def trim_and_fade(audio, sr, floor_db=-45.0, keep_s=0.2, fade_s=0.12):
    """Cut the quiet tail the model sometimes trails into, keep a short pause, fade the last 120 ms."""
    import numpy as np
    hop = max(1, int(sr * 0.02))
    last = 0
    for i in range(0, len(audio), hop):
        if 20 * np.log10(np.sqrt(np.mean(audio[i:i + hop] ** 2)) + 1e-9) > floor_db:
            last = i + hop
    audio = audio[:min(len(audio), last + int(sr * keep_s))].copy()
    n = min(len(audio), int(sr * fade_s))
    if n:
        audio[-n:] *= np.linspace(1.0, 0.0, n, dtype="float32")
    return audio


def normalize(audio, sr, target_db=-20.0):
    """One gain for the whole clip (mean level of its speech frames to target_db) plus a soft limiter.

    Keeps the natural dynamics; a time-varying leveler made openings sound distant, so there is none.
    """
    import numpy as np
    hop = max(1, int(sr * 0.1))
    levels = [20 * np.log10(np.sqrt(np.mean(audio[i:i + hop] ** 2)) + 1e-9) for i in range(0, len(audio) - hop, hop)]
    speech = [x for x in levels if x > -45.0]
    gain = 10 ** ((target_db - (float(np.mean(speech)) if speech else target_db)) / 20)
    return (np.tanh(audio * gain / 0.9) * 0.9).astype("float32")


def sidecar(wav_path):
    """The transcript saved next to a locked or audition WAV (exact text that was spoken), or None."""
    path = os.path.splitext(wav_path)[0] + ".txt"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def trim_silence(audio, sr, floor_db=-60.0, keep_lead_s=0.06, keep_tail_s=0.15):
    """Cut leading and trailing stretches quieter than floor_db (engines such as VoxCPM2 start a clone with up to
    1.5 s of digital silence). Keeps a short margin; a clip with nothing above the floor is returned as is."""
    import numpy as np
    hop = max(1, int(sr * 0.01))
    lv = np.array([20 * np.log10(np.sqrt(np.mean(audio[i:i + hop] ** 2)) + 1e-12) for i in range(0, len(audio), hop)])
    idx = np.where(lv > floor_db)[0]
    if len(idx) == 0:
        return audio
    return audio[max(0, idx[0] * hop - int(sr * keep_lead_s)):min(len(audio), (idx[-1] + 1) * hop + int(sr * keep_tail_s))]


def tighten_reference(audio, sr, floor_db=-45.0, lead_s=0.03, tail_s=0.05, fade_s=0.03):
    """Tight reference clip for cloning: no lead-in, a short tail, a 30 ms fade. A silent lead-in on the reference is
    reproduced (and stretched) at the start of every clone."""
    import numpy as np
    out = trim_silence(audio, sr, floor_db, lead_s, tail_s).copy()
    n = min(len(out), int(sr * fade_s))
    if n:
        out[-n:] *= np.linspace(1.0, 0.0, n, dtype="float32")
    return out
