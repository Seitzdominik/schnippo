"""Gladia v2 pre-recorded transcription (Bring Your Own Key).

Flow: POST /v2/upload (multipart field "audio") -> POST /v2/pre-recorded -> poll GET /v2/pre-recorded/{id}.
Docs checked 2026-11-04. Gladia documents *no* option for filler words / disfluencies /
verbatim output, so fillers may be dropped; analysis.py has a gap-based fallback for that.

The API key is only ever placed in the request header. It is never logged or stored.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from pathlib import Path

import httpx

from ..models import RawTranscript, Word
from .base import TranscriptionError

log = logging.getLogger("schnippo.gladia")
BASE = "https://api.gladia.io/v2"
RETRY_STATUS = {429, 500, 502, 503, 504}


def request_options(cfg, filler_vocabulary: bool = False) -> dict:
    """Result-relevant request options (everything except audio_url and language)."""
    opts: dict = {"model": cfg.gladia_model}
    if getattr(cfg, "gladia_diarization", False):
        opts["diarization"] = True
    vocab: list = list(cfg.gladia_custom_vocabulary)
    if filler_vocabulary:  # measured in Phase 1: no fillers gained, content words changed -> probe only
        vocab += [{"value": v, "intensity": 0.5} for v in ("äh", "ähm", "öhm", "hm")]
    if vocab:
        opts["custom_vocabulary"] = True
        opts["custom_vocabulary_config"] = {"vocabulary": vocab, "default_intensity": 0.4}
    return opts


def option_fingerprint(cfg, filler_vocabulary: bool = False) -> str:
    return hashlib.sha1(json.dumps(request_options(cfg, filler_vocabulary), sort_keys=True,
                                   ensure_ascii=False).encode()).hexdigest()[:8]


class GladiaProvider:
    name = "gladia"

    def __init__(self, cfg, client: httpx.Client | None = None, filler_vocabulary: bool = False):
        if not cfg.gladia_api_key:
            raise TranscriptionError(
                "GLADIA_API_KEY fehlt: als Umgebungsvariable setzen oder in config.toml im Einstellungsordner von Schnippo "
                "unter [gladia] api_key = \"...\" eintragen.")
        self._key = cfg.gladia_api_key
        self.cfg = cfg
        self.model = cfg.gladia_model
        self.filler_vocabulary = filler_vocabulary
        self.poll_timeout = cfg.gladia_poll_timeout_s
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0, read=300.0, write=300.0))

    def __repr__(self) -> str:
        return f"GladiaProvider(model={self.model!r})"

    # ---- request body (result-relevant options -> part of cache key) ----
    def _body(self, audio_url: str, language: str) -> dict:
        return {"audio_url": audio_url, "language_config": {"languages": [language], "code_switching": False},
                **request_options(self.cfg, self.filler_vocabulary)}

    def option_fingerprint(self) -> str:
        return option_fingerprint(self.cfg, self.filler_vocabulary)

    # ---- HTTP helpers ----
    def _req(self, method: str, url: str, retries: int = 4, **kw) -> httpx.Response:
        headers = {"x-gladia-key": self._key, **kw.pop("headers", {})}
        for attempt in range(retries + 1):
            try:
                r = self._client.request(method, url, headers=headers, **kw)
            except (httpx.TransportError,) as e:
                if attempt == retries:
                    raise TranscriptionError(f"Gladia nicht erreichbar: {type(e).__name__}") from None
                self._sleep(attempt)
                continue
            if r.status_code in RETRY_STATUS and attempt < retries:
                ra = r.headers.get("retry-after")
                self._sleep(attempt, float(ra) if ra and ra.replace(".", "").isdigit() else None)
                continue
            if r.status_code >= 400:
                raise TranscriptionError(f"Gladia {method} {url.removeprefix(BASE)} -> HTTP {r.status_code}: {_msg(r)}")
            return r
        raise TranscriptionError("unreachable")

    @staticmethod
    def _sleep(attempt: int, override: float | None = None) -> None:
        time.sleep(override if override is not None else min(30.0, 1.5 * 2 ** attempt) + random.random())

    # ---- API ----
    def upload(self, wav: Path) -> str:
        with wav.open("rb") as f:
            r = self._req("POST", f"{BASE}/upload", files={"audio": (wav.name, f, "audio/wav")})
        return r.json()["audio_url"]

    def start(self, audio_url: str, language: str) -> str:
        # No automatic retry of the job POST on 5xx/timeouts: Gladia does not deduplicate jobs, every POST is billed.
        r = self._req("POST", f"{BASE}/pre-recorded", retries=0, json=self._body(audio_url, language))
        return r.json()["id"]

    def wait(self, job_id: str) -> dict:
        t0, delay = time.time(), 1.0
        while True:
            data = self._req("GET", f"{BASE}/pre-recorded/{job_id}").json()
            st = data.get("status")
            if st == "done":
                return data
            if st == "error":
                raise TranscriptionError(f"Gladia-Job {job_id} fehlgeschlagen (error_code={data.get('error_code')})")
            if time.time() - t0 > self.poll_timeout:
                raise TranscriptionError(f"Gladia-Job {job_id} nach {self.poll_timeout:.0f}s nicht fertig (Status {st}); "
                                         "Job läuft serverseitig weiter, nicht erneut starten")
            time.sleep(delay)
            delay = min(delay * 1.5, 8.0)

    def transcribe(self, wav: Path, language: str, raw_out: Path | None = None) -> RawTranscript:
        t0 = time.time()
        pending = raw_out.with_name(raw_out.name + ".pending") if raw_out else None
        job = None
        if pending is not None and pending.exists():  # interrupted earlier: fetch that job instead of paying again
            try:
                info = json.loads(pending.read_text(encoding="utf-8"))
                if info.get("fingerprint") == self.option_fingerprint():
                    job = info["job"]
                    log.info("gladia job %s resumed for %s (no new upload)", job, wav.parent.name)
            except (OSError, ValueError, KeyError):
                job = None
        if job is None:
            url = self.upload(wav)
            job = self.start(url, language)
            log.info("gladia job %s started for %s", job, wav.parent.name)
            if pending is not None:
                pending.write_text(json.dumps({"job": job, "fingerprint": self.option_fingerprint(), "started": time.time()}),
                                   encoding="utf-8")
        try:
            data = self.wait(job)
        except TranscriptionError as e:
            if pending is not None and "serverseitig weiter" not in str(e):
                pending.unlink(missing_ok=True)  # the job itself failed → next attempt starts fresh
            raise
        if raw_out:
            raw_out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if pending is not None:
            pending.unlink(missing_ok=True)
        raw = normalize(data, language)
        raw.options = {**request_options(self.cfg, self.filler_vocabulary), "filler_vocabulary": self.filler_vocabulary,
                       "fingerprint": self.option_fingerprint()}
        raw.processing_s = raw.processing_s or round(time.time() - t0, 2)
        return raw


def _msg(r: httpx.Response) -> str:
    try:
        j = r.json()
        return str(j.get("message") or j.get("validation_errors") or j)[:300]
    except Exception:
        return r.text[:300]


def normalize(data: dict, language: str) -> RawTranscript:
    """Gladia result JSON -> RawTranscript with w0001… IDs (time-ordered, leading spaces stripped)."""
    res = data.get("result") or {}
    tr = res.get("transcription") or {}
    meta = res.get("metadata") or {}
    words = []
    for utt in tr.get("utterances") or []:
        spk = utt.get("speaker")
        for w in utt.get("words") or []:
            text = (w.get("word") or "").strip()
            if not text:
                continue
            words.append((float(w["start"]), float(w["end"]), text, w.get("confidence"), spk))
    words.sort(key=lambda x: (x[0], x[1]))
    tokens = [Word(id=f"w{i:04d}", text=t, start_s=round(s, 3), end_s=round(max(e, s), 3),
                   confidence=None if c is None else round(float(c), 3), speaker=None if sp is None else int(sp))
              for i, (s, e, t, c, sp) in enumerate(words, 1)]
    langs = tr.get("languages") or [language]
    return RawTranscript(provider="gladia", language=langs[0] if langs else language, tokens=tokens,
                         audio_duration_s=meta.get("audio_duration"), billing_s=meta.get("billing_time"),
                         processing_s=meta.get("transcription_time"), provider_job_id=data.get("id"))
