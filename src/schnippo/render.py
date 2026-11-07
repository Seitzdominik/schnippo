"""Robust check render of a Resolve timeline (video + audio), for verification only.

Pitfalls measured on 21.1.2 (see NOTES):
  * relative TargetDir → modal "path not valid" dialog, afterwards the API answers None → always absolute;
  * after an audio-only render (ExportVideo False / AudioFormat wav) the render format is 'unknown' and
    SetRenderSettings({ExportVideo: True, ExportAudio: True}) silently keeps rendering audio only →
    set {ExportVideo: True, ExportAudio: False} first, then the full settings;
  * right after building a timeline AddRenderJob/StartRendering sometimes refuse → wait for idle, retry, poll status;
  * audio-only renders (ExportVideo False) are not started at all (StartRendering → False, also later and after
    saving) → we always render video + audio (ProRes Proxy is fast) and only check the streams the caller needs;
  * the output is checked with ffprobe; a missing stream is an error, retried once.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from .media import _bin


class RenderError(RuntimeError):
    pass


def _streams(path: Path) -> list[str]:
    out = subprocess.run([_bin("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [s.get("codec_type") for s in json.loads(out or "{}").get("streams", [])]


def _wait_idle(p, timeout: float) -> None:
    t_end = time.time() + timeout
    while p.IsRenderingInProgress():
        if time.time() > t_end:
            raise RenderError("Resolve rendert noch einen anderen Auftrag")
        time.sleep(0.5)


SMALL_W = 640  # check renders that only measure sound


def _timeline_size(timeline) -> tuple[int, int] | None:
    try:
        w = int(timeline.GetSetting("timelineResolutionWidth"))
        h = int(timeline.GetSetting("timelineResolutionHeight"))
        return (w, h) if w and h else None
    except Exception:
        return None


def render_timeline(p, timeline, out_dir: Path, name: str, video: bool = True, audio: bool = True,
                    mark: tuple[int, int] | None = None, timeout: float = 900.0, sleep=time.sleep,
                    preset: str | None = None) -> Path:
    """Render the timeline (or [mark_in, mark_out] absolute frames) to <out_dir>/<name>*.mov (ProRes Proxy + PCM).
    preset: load this render preset first (e.g. the delivery preset → its audio normalization applies to the check
    render; format, codec and target are overridden here, the normalization fields stay – measured, see delivery.py)."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    p.SetCurrentTimeline(timeline)
    _wait_idle(p, 120)
    want = (["video"] if video else []) + (["audio"] if audio else [])
    last_err = ""
    for attempt in range(2):
        stamp = f"{name}_{int(time.time() * 1000)}"
        if preset and not p.LoadRenderPreset(preset):
            raise RenderError(f"Render-Preset „{preset}“ lässt sich nicht laden")
        if not p.SetCurrentRenderFormatAndCodec("mov", "ProRes422P"):
            raise RenderError("Render-Format mov/ProRes422P abgelehnt (Dialog in Resolve offen?)")
        p.SetRenderSettings({"ExportVideo": True, "ExportAudio": False})  # un-stick video after audio-only renders
        settings = {"TargetDir": str(out_dir), "CustomName": stamp, "ExportVideo": True, "ExportAudio": True,
                    "AudioCodec": "lpcm", "AudioSampleRate": 48000, "AudioBitDepth": 24}
        settings.update({"SelectAllFrames": False, "MarkIn": mark[0], "MarkOut": mark[1]} if mark else {"SelectAllFrames": True})
        full = None
        if not video:  # audio-only renders do not start (Phase 4) → picture at 640 px: 4K ProRes was 9.6 GB per 11 min
            full = _timeline_size(timeline)
            if full:
                w, h = full
                settings.update({"FormatWidth": SMALL_W, "FormatHeight": max(2, round(SMALL_W * h / w / 2) * 2)})
        if not p.SetRenderSettings(settings):
            raise RenderError("SetRenderSettings abgelehnt")
        job = None
        for _ in range(5):
            job = p.AddRenderJob()
            if job:
                break
            sleep(1)
        if not job:
            raise RenderError("AddRenderJob liefert keinen Auftrag")
        try:
            started = False
            for _ in range(15):
                _wait_idle(p, 60)
                started = p.StartRendering([job])
                if started:
                    break
                sleep(2)
            if not started:
                raise RenderError("StartRendering startet nicht (15 Versuche)")
            t_end = time.time() + timeout
            st = {}
            while time.time() < t_end:
                st = p.GetRenderJobStatus(job) or {}
                if st.get("JobStatus") in ("Complete", "Failed", "Cancelled"):
                    break
                sleep(0.5)
            if st.get("JobStatus") != "Complete":
                raise RenderError(f"Render nicht abgeschlossen: {st}")
        finally:
            p.DeleteRenderJob(job)
            if full:  # the next render (e.g. the delivery preset) must not inherit the small size
                p.SetRenderSettings({"FormatWidth": full[0], "FormatHeight": full[1]})
        files = sorted(out_dir.glob(f"{stamp}*.mov"))
        if not files:
            last_err = "keine Ausgabedatei"
            continue
        got = _streams(files[0])
        if all(w in got for w in want):
            return files[0]
        last_err = f"Ausgabe enthält {got}, erwartet {want}"
    raise RenderError(f"Prüf-Render fehlgeschlagen: {last_err}")
