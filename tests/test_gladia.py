import json

import httpx
import pytest

from schnippo.transcribe import gladia as g
from schnippo.transcribe.base import TranscriptionError

RESULT = {
    "id": "job-1", "status": "done",
    "result": {
        "metadata": {"audio_duration": 4.2, "number_of_distinct_channels": 1, "billing_time": 4.2, "transcription_time": 1.1},
        "transcription": {"languages": ["de"], "full_transcript": "Hallo äh Welt", "utterances": [
            {"start": 0.2, "end": 1.6, "words": [
                {"word": "Hallo", "start": 0.2, "end": 0.6, "confidence": 0.98},
                {"word": " äh", "start": 0.7, "end": 0.9, "confidence": 0.5},
                {"word": " Welt", "start": 1.0, "end": 1.6, "confidence": 0.97}]}]}},
}


def transport(log, init_status=201, polls=2):
    state = {"n": 0}

    def handler(req: httpx.Request):
        log.append((req.method, req.url.path, req.headers.get("x-gladia-key"), req.content if req.method == "POST" else b""))
        if req.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://api.gladia.io/file/abc", "audio_metadata": {}})
        if req.url.path == "/v2/pre-recorded" and req.method == "POST":
            return httpx.Response(init_status, json={"id": "job-1", "result_url": "x"} if init_status < 400 else {"message": "boom"})
        if req.url.path == "/v2/pre-recorded/job-1":
            state["n"] += 1
            if state["n"] < polls:
                return httpx.Response(200, json={"id": "job-1", "status": "processing"})
            return httpx.Response(200, json=RESULT)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(g.time, "sleep", lambda s: None)


def test_full_flow(cfg, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 100)
    log = []
    prov = g.GladiaProvider(cfg, client=httpx.Client(transport=transport(log)))
    raw = prov.transcribe(wav, "de", raw_out=tmp_path / "raw.json")
    assert [w.text for w in raw.tokens] == ["Hallo", "äh", "Welt"]  # leading spaces stripped
    assert [w.id for w in raw.tokens] == ["w0001", "w0002", "w0003"]
    assert raw.billing_s == 4.2 and raw.provider_job_id == "job-1"
    assert all(h == "test-key-123" for _, _, h, _ in log)
    body = json.loads(next(c for m, p, _, c in log if p == "/v2/pre-recorded"))
    assert body["language_config"] == {"languages": ["de"], "code_switching": False} and body["model"] == "solaria-3"
    assert json.loads((tmp_path / "raw.json").read_text())["id"] == "job-1"
    assert "test-key-123" not in repr(prov) and "test-key-123" not in repr(cfg)


def test_job_post_is_never_retried(cfg, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    log = []
    prov = g.GladiaProvider(cfg, client=httpx.Client(transport=transport(log, init_status=503)))
    with pytest.raises(TranscriptionError, match="HTTP 503"):
        prov.transcribe(wav, "de")
    assert sum(1 for m, p, _, _ in log if p == "/v2/pre-recorded" and m == "POST") == 1


def test_missing_key(cfg):
    cfg.gladia_api_key = None
    with pytest.raises(TranscriptionError, match="GLADIA_API_KEY"):
        g.GladiaProvider(cfg)


def test_option_fingerprint_changes_with_settings(cfg):
    a = g.GladiaProvider(cfg).option_fingerprint()
    assert a == g.option_fingerprint(cfg)  # computable without constructing a provider (no key needed)
    assert g.GladiaProvider(cfg, filler_vocabulary=True).option_fingerprint() != a
    cfg.gladia_model = "solaria-1"
    assert g.option_fingerprint(cfg) != a
    cfg.gladia_model, cfg.gladia_custom_vocabulary = "solaria-3", ["DaVinci"]
    assert g.option_fingerprint(cfg) != a


def test_interrupted_job_is_resumed_without_new_upload(cfg, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 100)
    log = []
    prov = g.GladiaProvider(cfg, client=httpx.Client(transport=transport(log, polls=99)))
    prov.poll_timeout = -1  # the first run gives up while Gladia is still working (like an abort)
    with pytest.raises(TranscriptionError, match="serverseitig weiter"):
        prov.transcribe(wav, "de", raw_out=tmp_path / "raw.json")
    assert (tmp_path / "raw.json.pending").exists()
    log2 = []
    prov2 = g.GladiaProvider(cfg, client=httpx.Client(transport=transport(log2, polls=1)))
    raw = prov2.transcribe(wav, "de", raw_out=tmp_path / "raw.json")
    assert raw.provider_job_id == "job-1" and not (tmp_path / "raw.json.pending").exists()
    assert not any(p in ("/v2/upload", "/v2/pre-recorded") and m == "POST" for m, p, _, _ in log2)  # nothing billed twice
