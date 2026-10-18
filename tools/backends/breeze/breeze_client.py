"""Minimal client for Breeze TTS 2's own HTTP API (python -m breeze_infer.api). Standard library only.

Not the tts-serve contract: requests are multipart form data and the reply is raw 24 kHz mono signed 16-bit PCM.
Server address, first match wins: env BREEZE_URL, `breeze.url` in website/assets/config.json, http://127.0.0.1:7861.
Design (no reference): text + instruction. Clone / direction: ref_audio + ref_text (+ optional instruction).
"""
import io
import json
import os
import urllib.error
import urllib.request
import uuid

SAMPLE_RATE = 24000


class BreezeError(RuntimeError):
    pass


def server_url():
    url = os.environ.get("BREEZE_URL")
    if not url:
        try:
            with open(os.path.join("website", "assets", "config.json"), encoding="utf-8") as f:
                url = (json.load(f).get("breeze") or {}).get("url")
        except (OSError, ValueError):
            url = None
    return (url or "http://127.0.0.1:7861").rstrip("/")


def _multipart(fields, files):
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for name, value in fields.items():
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, (filename, data) in files.items():
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                   f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


class Breeze:
    def __init__(self, url=None, timeout=600):
        self.url, self.timeout = (url or server_url()).rstrip("/"), timeout

    def model(self):
        try:
            with urllib.request.urlopen(self.url + "/v1/model", timeout=15) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise BreezeError(f"cannot reach Breeze at {self.url} ({exc}). Set BREEZE_URL or breeze.url in "
                              f"website/assets/config.json") from None

    def check(self):
        try:
            return self.model()
        except BreezeError as exc:
            raise SystemExit(f"Error: {exc}")

    def speak(self, text, instruction=None, ref_wav=None, ref_text=None, cfg_scale=None, seed=None):
        """Return float32 mono samples at 24 kHz. Design when ref_wav is None; clone / direction otherwise."""
        import numpy as np
        fields = {"text": text}
        if instruction:
            fields["instruction"] = instruction
        if cfg_scale is not None:
            fields["cfg_scale"] = cfg_scale
        if seed is not None:
            fields["seed"] = int(seed)
        files = {}
        if ref_wav is not None:
            if not ref_text:
                raise BreezeError("Breeze needs the exact transcript of the reference clip (ref_text)")
            raw = ref_wav if isinstance(ref_wav, bytes) else open(ref_wav, "rb").read()
            files["ref_audio"] = ("reference.wav", raw)
            fields["ref_text"] = ref_text
        data, ctype = _multipart(fields, files)
        req = urllib.request.Request(self.url + "/v1/audio/speech", data=data, method="POST", headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                pcm = r.read()
        except urllib.error.HTTPError as exc:
            raise BreezeError(f"HTTP {exc.code} from {self.url}: {exc.read().decode(errors='replace')[:300]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BreezeError(f"cannot reach Breeze at {self.url} ({exc})") from None
        if len(pcm) < 2400:
            raise BreezeError(f"Breeze returned no audio ({len(pcm)} bytes): {pcm[:200]!r}")
        return np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype("float32") / 32768.0
