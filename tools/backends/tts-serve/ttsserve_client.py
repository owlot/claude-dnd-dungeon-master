"""Minimal client for a tts-serve server (https://github.com/scorbo2/tts-serve). Standard library only.

The server URL comes from, in order: the TTS_SERVE_URL environment variable, `ttsServe.url` in
website/assets/config.json, then http://127.0.0.1:7501. Extra engine parameters (for example VoxCPM's
`cfg_value`) can be listed under `ttsServe.params` in that config and are sent with every request.
"""
import base64
import json
import os
import urllib.error
import urllib.request

MAX_REF_B64 = 10_000_000  # the server rejects a larger audio_base64


class TTSServeError(RuntimeError):
    pass


def _config():
    try:
        with open(os.path.join("website", "assets", "config.json"), encoding="utf-8") as f:
            return json.load(f).get("ttsServe") or {}
    except (OSError, ValueError):
        return {}


def server_url():
    return (os.environ.get("TTS_SERVE_URL") or _config().get("url") or "http://127.0.0.1:7501").rstrip("/")


class Clip:
    """One synthesized clip: WAV file bytes plus the server's metadata."""

    def __init__(self, wav, sample_rate, seed=None, time_used=None, rtf=None):
        self.wav, self.sample_rate, self.seed, self.time_used, self.rtf = wav, sample_rate, seed, time_used, rtf


class Client:
    def __init__(self, url=None, timeout=600):
        self.url = (url or server_url()).rstrip("/")
        self.timeout = timeout
        self.params = dict(_config().get("params") or {})

    def _call(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:400]
            raise TTSServeError(f"HTTP {exc.code} from {self.url}{path}: {body}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TTSServeError(f"cannot reach tts-serve at {self.url} ({exc}). Set TTS_SERVE_URL or "
                                f"ttsServe.url in website/assets/config.json") from None

    def health(self):
        return self._call("GET", "/health")

    def check(self):
        """health(), but exit with a one-line message when the server cannot be reached (for command-line tools)."""
        try:
            return self.health()
        except TTSServeError as exc:
            raise SystemExit(f"Error: {exc}")

    def capabilities(self):
        return self._call("GET", "/capabilities")

    def synthesize(self, text, ref_wav=None, ref_text=None, language="en", seed=None, **params):
        """Clone from ref_wav (path or bytes, optional transcript), or design a voice when ref_wav is None.

        For voice design put the description in parentheses before the text: "(a gruff old man)Hello."
        Only engines that support it (VoxCPM2) accept a request without reference audio.
        """
        payload = {"text": text, "language": language}
        if seed is not None:
            payload["seed"] = int(seed)
        if ref_wav is not None:
            raw = ref_wav if isinstance(ref_wav, bytes) else open(ref_wav, "rb").read()
            b64 = base64.b64encode(raw).decode()
            if len(b64) > MAX_REF_B64:
                raise TTSServeError("reference clip is too large for the server (limit ~7.5 MB of audio)")
            payload["audio_base64"] = b64
            if ref_text:
                payload["reference_text"] = ref_text
        payload.update(self.params)
        payload.update({k: v for k, v in params.items() if v is not None})
        try:
            r = self._call("POST", "/synthesize", payload)
        except TTSServeError as exc:
            if ref_wav is None and "audio_base64" in str(exc):
                raise TTSServeError(f"{exc}\nThis server needs reference audio and cannot design a voice from a "
                                    f"description. Point TTS_SERVE_URL at a VoxCPM2 server for auditioning.") from None
            raise
        return Clip(base64.b64decode(r["audio_base64"]), r["sample_rate"], r.get("seed"),
                    r.get("time_used"), r.get("rtf"))
