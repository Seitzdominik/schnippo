"""Render presets made by the server: a check-render preset and an export preset (H.264/AAC), both normalization off.

Finding: SetRenderSettings has no key for the Deliver-page "Normalize Audio" (script key
list ends at DataBurnIn, 21.1.2), but a preset round trip reaches it: SaveAsNewRenderPreset → ExportRenderPreset (XML) →
set fields in <FieldsBlob> (hex of a Qt QDataStream QVariantMap: u32 version, u32 count, QString key + QVariant value) →
ImportRenderPreset → LoadRenderPreset. Mode 2 + target −16 → render −16.0 LUFS. But the normalization gain is applied
*before* the clip FX (with a driven limiter the output TP stays at the ceiling), so it does not help the true peak →
not used for loudness; the true peak is handled in apply_audio. Method values > 2 crashed Resolve twice → never written.
Saved presets copy the project's current render state, so normalization is switched off explicitly.
"""

from __future__ import annotations

import re
import struct
import tempfile
from pathlib import Path

CHECK_PRESET = "schnippo Prüfrender"
NORM_FIELDS = {"RecordNormalizeAudio": True, "RecordAudioNormalizationMethod": 0, "RecordAudioNormalizationMode": 2}


class PresetError(RuntimeError):
    pass


def _qstr(s: str) -> bytes:
    e = s.encode("utf-16-be")
    return struct.pack(">I", len(e)) + e


def _qvar(v) -> bytes:
    if isinstance(v, bool):
        return struct.pack(">I", 1) + b"\x00" + (b"\x01" if v else b"\x00")
    if isinstance(v, int):
        return struct.pack(">I", 2) + b"\x00" + struct.pack(">i", v)
    if isinstance(v, float):
        return struct.pack(">I", 6) + b"\x00" + struct.pack(">d", v)
    raise TypeError(type(v))


def _skip_var(b: bytes, pos: int) -> int:
    """Position after the QVariant starting at pos (types seen in 21.1.2 presets + the common ones)."""
    ty = struct.unpack(">I", b[pos:pos + 4])[0]
    pos += 5  # type + null flag
    if ty == 1:
        return pos + 1
    if ty in (2, 3):
        return pos + 4
    if ty in (4, 5, 6):
        return pos + 8
    if ty in (10, 12):
        n = struct.unpack(">I", b[pos:pos + 4])[0]
        return pos + 4 + (0 if n == 0xFFFFFFFF else n)
    if ty == 9:
        n = struct.unpack(">I", b[pos:pos + 4])[0]
        pos += 4
        for _ in range(n):
            pos = _skip_var(b, pos)
        return pos
    if ty == 8:
        n = struct.unpack(">I", b[pos:pos + 4])[0]
        pos += 4
        for _ in range(n):
            k = struct.unpack(">I", b[pos:pos + 4])[0]
            pos = _skip_var(b, pos + 4 + k)
        return pos
    raise PresetError(f"unbekannter QVariant-Typ {ty} im Preset")


def parse_blob(b: bytes) -> tuple[int, list[tuple[str, bytes]]]:
    """FieldsBlob → (version, [(key, raw QVariant bytes)]) – values kept raw so unknown fields round-trip exactly."""
    ver, n = struct.unpack(">II", b[:8])
    pos, out = 8, []
    for _ in range(n):
        k = struct.unpack(">I", b[pos:pos + 4])[0]
        key = b[pos + 4:pos + 4 + k].decode("utf-16-be")
        start = pos + 4 + k
        pos = _skip_var(b, start)
        out.append((key, b[start:pos]))
    if pos != len(b):
        raise PresetError("FieldsBlob nicht vollständig gelesen")
    return ver, out


def set_blob_fields(xml: str, fields: dict) -> str:
    """Set (replace or append) QVariant fields in the preset's FieldsBlob."""
    m = re.search(r"<FieldsBlob>([0-9a-fA-F]*)</FieldsBlob>", xml)
    if not m:
        raise PresetError("Preset-XML ohne FieldsBlob")
    raw = bytes.fromhex(m.group(1)) if m.group(1) else struct.pack(">II", 1, 0)
    if len(raw) < 8:
        raise PresetError("FieldsBlob zu kurz")
    ver, entries = parse_blob(raw)
    entries = [(k, v) for k, v in entries if k not in fields] + [(k, _qvar(v)) for k, v in fields.items()]
    b = struct.pack(">II", ver, len(entries)) + b"".join(_qstr(k) + v for k, v in entries)
    return xml[:m.start(1)] + b.hex() + xml[m.end(1):]


add_blob_fields = set_blob_fields


def normalization_fields(target_lufs: float) -> dict:
    return {**NORM_FIELDS, "RecordAudioNormalizationTargetLoudness": float(target_lufs)}


def make_preset(r, p, name: str, fmt: str, codec: str, settings: dict, extra_fields: dict) -> None:
    """(Re)create our own render preset `name` from format/codec/settings (+ blob fields) and load it."""
    if name in (p.GetRenderPresetList() or []):
        p.DeleteRenderPreset(name)
    if not p.SetCurrentRenderFormatAndCodec(fmt, codec):
        raise PresetError(f"Render-Format {fmt}/{codec} abgelehnt")
    p.SetRenderSettings({"ExportVideo": True, "ExportAudio": False})
    if not p.SetRenderSettings(settings):
        raise PresetError("SetRenderSettings abgelehnt")
    tmp_name = "schnippo-tmp"
    if tmp_name in (p.GetRenderPresetList() or []):
        p.DeleteRenderPreset(tmp_name)
    if not p.SaveAsNewRenderPreset(tmp_name):
        raise PresetError("Preset nicht gespeichert")
    try:
        with tempfile.TemporaryDirectory(prefix="schnippo_preset_") as d:
            exp = Path(d) / "export"
            if not r.ExportRenderPreset(tmp_name, str(exp)):
                raise PresetError("ExportRenderPreset fehlgeschlagen")
            files = [exp] if exp.is_file() else sorted(exp.rglob("*.xml"))  # 21.1.2 exports into a folder of that name
            if not files:
                raise PresetError("exportiertes Preset nicht gefunden")
            xml = set_blob_fields(files[0].read_text(encoding="utf-8"), extra_fields)
            f = Path(d) / f"{name}.xml"  # Resolve names the imported preset after the file
            f.write_text(xml, encoding="utf-8")
            if not r.ImportRenderPreset(str(f)):
                raise PresetError("ImportRenderPreset fehlgeschlagen")
    finally:
        p.DeleteRenderPreset(tmp_name)
    if not p.LoadRenderPreset(name):
        raise PresetError(f"Preset „{name}“ lässt sich nicht laden")


def ensure_check_preset(r, p) -> str:
    """ProRes Proxy + PCM, normalization explicitly off (SaveAsNewRenderPreset copies the project's current state,
    which may hold a delivery preset's normalization)."""
    make_preset(r, p, CHECK_PRESET, "mov", "ProRes422P",
                {"ExportVideo": True, "ExportAudio": True, "AudioCodec": "lpcm", "AudioSampleRate": 48000, "AudioBitDepth": 24,
                 "SelectAllFrames": True}, {"RecordNormalizeAudio": False})
    return CHECK_PRESET


def delivery_preset_name(fmt: str) -> str:
    label = {"reel": "Reel", "course": "Kurs", "commercial": "Werbespot"}.get(fmt, "YouTube")
    return f"schnippo Export {label} (H.264)"


def ensure_delivery_preset(r, p, fmt: str, target_dir: Path, custom_name: str) -> str:
    """H.264 MP4 + AAC at timeline resolution/rate, normalization explicitly off (the loudness is in the timeline);
    left loaded so the Deliver page is ready (TargetDir = export folder, file name = timeline name)."""
    name = delivery_preset_name(fmt)
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    make_preset(r, p, name, "mp4", "H264",
                {"ExportVideo": True, "ExportAudio": True, "AudioCodec": "aac", "AudioSampleRate": 48000,
                 "SelectAllFrames": True, "TargetDir": str(target_dir), "CustomName": custom_name, "VideoQuality": 0},
                {"RecordNormalizeAudio": False})
    return name


# ---------------------------------------------------------------- phase 8: final export
EXPORT_PRESETS = {
    "reel": {"label": "Reel 1080×1920 H.264", "size": (1080, 1920), "portrait": True},
    "youtube_1080": {"label": "YouTube 1080p H.264", "size": (1920, 1080), "portrait": False},
    "youtube_4k": {"label": "YouTube 4K H.264", "size": (3840, 2160), "portrait": False},
}


def pick_preset(preset: str, tl_w: int, tl_h: int) -> str:
    """auto → reel for portrait timelines, YouTube 1080p for landscape (4K only on request)."""
    if preset in EXPORT_PRESETS:
        want_portrait = EXPORT_PRESETS[preset]["portrait"]
        if want_portrait != (tl_h > tl_w):
            raise ValueError(f"„{EXPORT_PRESETS[preset]['label']}“ passt nicht zur Timeline ({tl_w}×{tl_h}, "
                             f"{'Hochformat' if tl_h > tl_w else 'Querformat'}). Reframing macht der Server nicht – bitte "
                             f"{'youtube_1080 oder youtube_4k' if tl_w > tl_h else 'reel'} wählen.")
        if preset == "youtube_4k" and tl_h < 2160:
            raise ValueError(f"Die Timeline hat {tl_w}×{tl_h} – 4K wäre hochskaliert. Bitte youtube_1080 wählen.")
        return preset
    if preset != "auto":
        raise ValueError("preset: auto | reel | youtube_1080 | youtube_4k")
    return "reel" if tl_h > tl_w else "youtube_1080"


def export_final(r, p, tl, preset: str, target_dir: Path, name: str, fmt: str, progress=None, timeout: float = 3600.0,
                 sleep=None) -> dict:
    """Render the finished timeline to <target_dir>/<name>.mp4 (H.264 + AAC 48 kHz, normalization OFF – the loudness is
    already in the timeline from the polish pass). Returns {"file", "preset", "size"}."""
    import time as _t

    from .render import _wait_idle

    sleep = sleep or _t.sleep
    w, h = int(tl.GetSetting("timelineResolutionWidth")), int(tl.GetSetting("timelineResolutionHeight"))
    key = pick_preset(preset, w, h)
    pw, ph = EXPORT_PRESETS[key]["size"]
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    p.SetCurrentTimeline(tl)
    _wait_idle(p, 120)
    ensure_delivery_preset(r, p, fmt, target_dir, name)  # H.264/AAC, normalization explicitly off, loaded
    if not p.SetRenderSettings({"TargetDir": str(target_dir), "CustomName": name, "SelectAllFrames": True,
                                "FormatWidth": pw, "FormatHeight": ph, "ExportVideo": True, "ExportAudio": True}):
        raise PresetError("Export-Einstellungen abgelehnt")
    before = set(target_dir.glob(f"{name}*.mp4"))
    job = p.AddRenderJob()
    if not job:
        raise PresetError("Resolve hat keinen Export-Auftrag angelegt")
    try:
        if not p.StartRendering([job]):
            raise PresetError("Resolve startet den Export nicht (Dialog offen?)")
        t_end, last = _t.time() + timeout, -1
        st = {}
        while _t.time() < t_end:
            st = p.GetRenderJobStatus(job) or {}
            pct = int(st.get("CompletionPercentage") or 0)
            if progress and pct // 10 != last // 10:
                progress(f"Export {pct} %")
                last = pct
            if st.get("JobStatus") in ("Complete", "Failed", "Cancelled"):
                break
            sleep(1.0)
        if st.get("JobStatus") != "Complete":
            raise PresetError(f"Export nicht abgeschlossen: {st}")
    finally:
        p.DeleteRenderJob(job)
    new = sorted(set(target_dir.glob(f"{name}*.mp4")) - before, key=lambda f: f.stat().st_mtime)
    files = new or sorted(target_dir.glob(f"{name}*.mp4"), key=lambda f: f.stat().st_mtime)
    if not files:
        raise PresetError("Exportdatei nicht gefunden")
    return {"file": str(files[-1]), "preset": key, "label": EXPORT_PRESETS[key]["label"], "size": (pw, ph)}
