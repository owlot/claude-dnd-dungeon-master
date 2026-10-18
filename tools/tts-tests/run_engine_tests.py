#!/usr/bin/env python3
"""Run the tests in yagra-emotion-tests.md against one tts-serve server and record what comes out.

    python .claude/tools/tts-tests/run_engine_tests.py --url http://127.0.0.1:7500 [--tests T1,T2] [--play] [--ref WAV]

Every engine is cloned from the same reference clip (default: Yagra's audition take 1 and its transcript), so only
the engine changes. Chatterbox gets the `tagged` text and Breeze the `breeze` text where a test has one; every other engine gets `plain`.
Takes are saved raw (no gain, no trimming) to .claude/tools/tts-tests/results/<engine>/, with results.json holding the
numbers. --play plays a level-matched copy of each take (the saved file stays raw).
Modes for VoxCPM: default = clone with transcript; --no-transcript --direction = style-controlled cloning.
Run it with a Python that has numpy and soundfile.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backends", "tts-serve"))
from ttsserve_client import Client, TTSServeError  # noqa: E402


def parse_tests(path):
    """{id: {"title", "plain", "tagged"|None, "direction"}} from the markdown file."""
    tests = {}
    for block in re.split(r"^## ", open(path, encoding="utf-8").read(), flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        m = re.match(r"(T\d+)\s+(.*)", head)
        if not m:
            continue
        def field(name):
            f = re.search(rf"\*\*{name}\*\*:?\s*(.*?)(?=\n\*\*|\n---|\Z)", body, re.S)
            return " ".join(f.group(1).split()) if f else None
        tests[m.group(1)] = {"title": m.group(2).strip(), "plain": field("plain"), "tagged": field("tagged"),
                             "breeze": field("breeze"), "direction": field("direction")}
    return tests


def metrics(audio, sr):
    n = sr // 4
    env = np.array([20 * np.log10(np.sqrt(np.mean(audio[i:i + n] ** 2)) + 1e-9) for i in range(0, len(audio) - n // 2, n)])
    inner = env[2:-2] if len(env) > 6 else env
    speech = env[env > -45]
    return {"duration_s": round(len(audio) / sr, 2), "peak": round(float(np.abs(audio).max()), 3),
            "clipped": int((np.abs(audio) > 0.99).sum()), "gaps_mid_clip": int((inner < -45).sum()),
            "level_start_db": round(float(env[:8].mean()), 1), "level_end_db": round(float(env[-8:].mean()), 1),
            "level_mean_db": round(float(speech.mean()), 1) if len(speech) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--tests", default="")
    ap.add_argument("--ref", default=".claude/tools/tts-tests/refs/yagra-voxcpm-take1.wav")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--label", help="folder name for the results (default: the server's engine name)")
    ap.add_argument("--plain", action="store_true", help="use the plain text even for Chatterbox (no inline tags)")
    ap.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                    help="engine parameter sent with every request, e.g. --param exaggeration=0.8 (repeatable)")
    ap.add_argument("--instruction", action="store_true",
                    help="send each test's direction line in the engine's `instruction` field (Breeze), not in the text")
    ap.add_argument("--direction", action="store_true",
                    help="prefix each text with its direction as a (description), for engines that take one (VoxCPM)")
    ap.add_argument("--no-transcript", action="store_true",
                    help="send the reference clip without its transcript (VoxCPM 'controllable cloning', which allows style control)")
    a = ap.parse_args()

    client = Client(a.url)
    caps = client.capabilities()
    engine = a.label or caps.get("engine", "engine")
    # which text variant this engine gets: Chatterbox "tagged" ([laugh]), Breeze "breeze" ((laugh)), everyone else "plain"
    variant = "plain" if a.plain else ("tagged" if engine.lower().startswith("chatterbox") else
                                       "breeze" if engine.lower().startswith("breeze") else "plain")
    def num_or_str(v):
        try:
            return float(v)
        except ValueError:
            return v
    extra_params = {k: num_or_str(v) for k, v in (x.split("=", 1) for x in a.param)}
    takes_transcript = any(p["name"] == "reference_text" for p in caps.get("parameters", []))
    transcript = None
    txt = os.path.splitext(a.ref)[0] + ".txt"
    if os.path.exists(txt) and not a.no_transcript and takes_transcript:
        transcript = open(txt, encoding="utf-8").read().strip()
    print(f"engine {engine} ({caps.get('model')}) at {client.url}; reference {a.ref}"
          f"{'' if transcript else ' (no transcript)'}; {variant} text; params {extra_params or 'default'}")

    tests = parse_tests(os.path.join(HERE, "yagra-emotion-tests.md"))
    wanted = [t for t in a.tests.split(",") if t] or list(tests)
    out_dir = os.path.join(HERE, "results", engine)
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    for tid in wanted:
        t = tests[tid]
        used = variant if t.get(variant) else "plain"
        text = t[used]
        if text and text.startswith("same as plain"):
            text = t["plain"]
        sent = f"({t['direction'].replace('(', ',').replace(')', ',')}){text}" if a.direction and t["direction"] else text
        try:
            t0 = time.time()
            kw = dict(extra_params)
            if a.instruction and t["direction"]:
                kw["instruction"] = t["direction"]
            clip = client.synthesize(sent, ref_wav=a.ref, ref_text=transcript, seed=a.seed, **kw)
            wall = time.time() - t0
        except TTSServeError as exc:
            results[tid] = {"title": t["title"], "error": str(exc)[:300]}
            print(f"{tid} {t['title']}: FAILED {str(exc)[:160]}")
            continue
        import io
        audio, sr = sf.read(io.BytesIO(clip.wav), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        path = os.path.join(out_dir, f"{tid}.wav")
        sf.write(path, audio, sr)
        r = metrics(audio, sr)
        r.update(title=t["title"], text_variant=used, sample_rate=sr,
                 direction=bool(a.direction), transcript=bool(transcript), text_sent=sent, params=extra_params, instruction=(t["direction"] if a.instruction else None),
                 wall_s=round(wall, 1), rtf=round(wall / (len(audio) / sr), 2), file=path)
        results[tid] = r
        print(f"{tid} {t['title']}: {r['duration_s']}s in {r['wall_s']}s (rtf {r['rtf']}) | peak {r['peak']} clipped "
              f"{r['clipped']} | gaps {r['gaps_mid_clip']} | level {r['level_start_db']}→{r['level_end_db']} dBFS", flush=True)
        if a.play:
            tmp = os.path.join(out_dir, "_play.wav")
            gain = 10 ** ((-20 - (r["level_mean_db"] or -20)) / 20)
            sf.write(tmp, (np.tanh(audio * gain / 0.9) * 0.9).astype("float32"), sr)
            print(f"   playing {tid}...", flush=True)
            subprocess.run(["paplay", tmp])
            time.sleep(1.5)
    if a.play and os.path.exists(os.path.join(out_dir, "_play.wav")):
        os.remove(os.path.join(out_dir, "_play.wav"))
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"engine": engine, "model": caps.get("model"), "server": client.url, "reference": a.ref,
                   "seed": a.seed, "direction": a.direction, "transcript": bool(transcript), "results": results}, f, indent=2)
    print(f"saved {out_dir}/results.json")


if __name__ == "__main__":
    main()
