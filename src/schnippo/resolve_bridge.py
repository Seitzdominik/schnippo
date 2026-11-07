"""Connection to a running DaVinci Resolve Studio (21.1+) via the scripting API.

Phase 1 scope: connect, import clips into a bin, read Resolve's own clip properties.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"


class ResolveUnavailable(RuntimeError):
    pass


def _module():
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", LIB)
    if MODULES not in sys.path:
        sys.path.append(MODULES)
    try:
        import DaVinciResolveScript  # type: ignore

        return DaVinciResolveScript
    except ImportError as e:  # pragma: no cover - depends on host
        raise ResolveUnavailable(f"DaVinciResolveScript not importable: {e}") from e


class ResolveBridge:
    def __init__(self):
        self._resolve = None

    def resolve(self):
        if self._resolve is not None:
            try:
                self._resolve.GetVersionString()
                return self._resolve
            except Exception:
                self._resolve = None
        r = _module().scriptapp("Resolve")
        if r is None:
            raise ResolveUnavailable(
                "Resolve not reachable. Is DaVinci Resolve Studio running and "
                "Preferences > System > General > External scripting = Local?")
        self._resolve = r
        return r

    def project(self):
        p = self.resolve().GetProjectManager().GetCurrentProject()
        if p is None:
            raise ResolveUnavailable("no project open in Resolve")
        return p

    def status(self) -> dict:
        r = self.resolve()
        p = self.project()
        return {"version": r.GetVersionString(), "product": r.GetProductName(), "project": p.GetName(),
                "project_fps": p.GetSettings().get("timelineFrameRate"), "timelines": p.GetTimelineCount()}

    def _ensure_bin(self, mp, name: str):
        """Bin by path ("Schnippo/Grafiken"), created step by step inside our own top bin. Existing bins of the user
        are only looked up, never renamed, moved or emptied."""
        folder = mp.GetRootFolder()
        for part in [x for x in name.split("/") if x]:
            sub = next((f for f in folder.GetSubFolderList() or [] if f.GetName() == part), None)
            if sub is None:  # AddSubFolder accepts duplicate names, so the lookup above makes this idempotent
                sub = mp.AddSubFolder(folder, part)
                if sub is None:
                    raise RuntimeError(f"Ordner „{part}“ im Media Pool ließ sich nicht anlegen")
            folder = sub
        return folder

    def import_clips(self, paths: list[Path], bin_name: str) -> dict[str, dict]:
        """Import files into bin (idempotent by file path). Returns {path: resolve clip props}."""
        mp = self.project().GetMediaPool()
        # anywhere in the Media Pool (also the user's own bins): reuse, never import a second copy, never move it
        existing = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
        todo = [str(p) for p in paths if str(p) not in existing]
        if todo:
            folder = self._ensure_bin(mp, bin_name)
            mp.SetCurrentFolder(folder)
            # 21.1.2: the README's canonical ImportMedia([{"FilePath": p}]) returns None for video files;
            # the deprecated list-of-paths form works.
            for item in mp.ImportMedia(todo) or []:
                existing[item.GetClipProperty("File Path")] = item
        out = {}
        for p in paths:
            item = existing.get(str(p))
            if item is None:
                out[str(p)] = {"imported": False}
                continue
            props = item.GetClipProperty()
            out[str(p)] = {
                "imported": True,
                "media_id": item.GetMediaId(),
                "fps": float(props.get("FPS") or 0) or None,
                "frames": int(props["Frames"]) if str(props.get("Frames", "")).isdigit() else None,
                "start_tc": props.get("Start TC"),
            }
        return out


def tool_bin(sub: str) -> str:
    """Media Pool path of our own bins: "<Toolname>/<sub>" (sub: material folder name, Standbilder, Grafiken,
    Audio-Extrakte)."""
    from .branding import DISPLAY_NAME
    return f"{DISPLAY_NAME}/{sub}"


# ---------------------------------------------------------------- phase 2: timeline build
def fps_setting(fps: float) -> str:
    for std, s in ((23.976, "23.976"), (29.97, "29.97"), (59.94, "59.94"), (47.952, "47.952"), (119.88, "119.88")):
        if abs(fps - std) < 0.01:
            return s
    return f"{fps:g}"


class BuildError(RuntimeError):
    pass


def _all_clips(folder):
    for c in folder.GetClipList() or []:
        yield c
    for f in folder.GetSubFolderList() or []:
        yield from _all_clips(f)


INCOMPLETE = "_unvollstaendig"


def _unique_name(existing: set[str], name: str) -> str:
    if name not in existing:
        return name
    k = 2
    while f"{name}_v{k}" in existing:
        k += 1
    return f"{name}_v{k}"


def _f(v) -> float | None:
    """Parse a Resolve rate value; None if Resolve does not report it (e.g. playback rate of custom timelines)."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def fps_readback(p, tl=None, mpis: dict | None = None) -> dict:
    """All frame-rate values that matter. timelinePlaybackFrameRate is read-only in the 21.1 API."""
    ps = p.GetSettings()
    out = {"project_fps": _f(ps.get("timelineFrameRate")), "project_playback_fps": _f(ps.get("timelinePlaybackFrameRate"))}
    if tl is not None:
        ts_ = tl.GetSettings()
        out.update({"timeline_fps": _f(ts_.get("timelineFrameRate")),
                    "timeline_playback_fps": _f(ts_.get("timelinePlaybackFrameRate")),
                    "timeline_custom_settings": ts_.get("useCustomSettings")})
    if mpis:
        out["clip_fps"] = {cid: _f(it.GetClipProperty("FPS")) for cid, it in mpis.items()}
    return out


def _mismatch(rb: dict, fps: float, keys=("project_fps", "project_playback_fps", "timeline_fps", "timeline_playback_fps")) -> list[str]:
    bad = [f"{k}={rb[k]:g}" for k in keys if rb.get(k) is not None and abs(rb[k] - fps) > 0.005]
    bad += [f"{k}=fehlt" for k in keys if k in rb and rb[k] is None and not k.startswith("timeline_playback")]
    bad += [f"clip_fps[{c}]={v}" for c, v in rb.get("clip_fps", {}).items() if v is None or abs(v - fps) > 0.005]
    return bad


FAIL_HELP = ("Resolve hat für keinen Weg eine Timeline mit {fps} fps (Timeline- und Wiedergabe-Framerate) angelegt: {attempts}. "
             "Manuell: In Resolve eine leere Timeline anlegen, Rechtsklick → Timelines → Timeline Settings → „Use Project "
             "Settings“ aus, Timeline-Framerate {fps}; oder ein leeres Projekt mit {fps} fps öffnen und erneut bauen.")


def _is_whole(fps: float) -> bool:
    return abs(fps - round(fps)) < 0.001


def _fps_fraction(fps: float) -> tuple[int, int]:
    for std, frac in ((23.976, (24000, 1001)), (29.97, (30000, 1001)), (59.94, (60000, 1001)),
                      (47.952, (48000, 1001)), (119.88, (120000, 1001))):
        if abs(fps - std) < 0.01:
            return frac
    return (round(fps), 1)


def _tc_frames(tc: str | None, fps: float) -> int:
    if not tc:
        return 0
    parts = [int(x) for x in tc.replace(";", ":").split(":")]
    if len(parts) != 4:
        return 0
    h, m, sec, f = parts
    nominal = round(fps)
    frames = ((h * 60 + m) * 60 + sec) * nominal + f
    if ";" in tc:  # drop-frame
        dropped = 2 if nominal == 30 else 4
        total_min = h * 60 + m
        frames -= dropped * (total_min - total_min // 10)
    return frames


def build_timeline(bridge: "ResolveBridge", cl, pieces: list, clips: dict, alternates: list | None,
                   bin_name: str, master_clip: str, plan_seconds: float, audio_crossfade_frames: int = 2,
                   work_dir: str | None = None, force_way: str | None = None, overlays: list | None = None,
                   stills: dict | None = None, audio_spectrum: dict | None = None, export_dir: str | None = None,
                   fmt: str = "reel", channel_plans: dict | None = None, graphics: list | None = None,
                   progress=None, on_stage=None, sfx: list | None = None) -> dict:
    """Build the cut (+ optional alternates timeline) with the frame rate of the main clip, in any project.

    Ways, each verified by reading back timeline *and* playback rate before anything is appended:
      1. project rate already right – or the project is empty and its rate can be set;
      2. whole rates: timeline with its own settings ("Use project settings" off);
      3. otherwise / if 2 fails: write the cut as FCPXML and import it (Resolve takes the rate from the file);
      4. clear error with instructions.
    Then: every piece (start, length, source offset, seconds vs. source ±1 frame), linked audio, timeline length vs.
    validate_cutlist, markers and 2-frame audio crossfades (added via API if the import did not bring them).
    """
    import tempfile
    from pathlib import Path

    from .fcpxml import write_fcpxml

    r = bridge.resolve()
    pm = r.GetProjectManager()
    p = bridge.project()
    if (p.GetName() or "").startswith("Untitled Project"):
        # after a restart or sleep Resolve may sit on a fresh unnamed project; render presets there crash it (21.1.2, assertion in the Deliver panel)
        raise BuildError("In Resolve ist kein eigenes Projekt geöffnet, nur ein unbenanntes. Bitte dein Projekt öffnen oder eines anlegen und speichern. Nichts gebaut.")
    if hasattr(r, "OpenPage") and r.GetCurrentPage() != "edit":  # check renders leave it on Deliver; building from there ended in a crash (NOTES, Phase 10)
        import time
        r.OpenPage("edit")
        time.sleep(1.0)
    used = sorted({pc.clip for pc in pieces} | {pc.clip for pc, _ in (alternates or [])})
    fps = clips[master_clip].resolve_fps or clips[master_clip].fps
    other = {c: (clips[c].resolve_fps or clips[c].fps) for c in used if abs((clips[c].resolve_fps or clips[c].fps) - fps) > 0.005}
    if other:
        raise BuildError(f"Hauptmaterial {master_clip} hat {fps:g} fps, abweichend: {other} – gemischte Raten werden "
                         f"nicht gebaut (Phase 0: ±1 Frame je Schnitt). Nichts gebaut.")
    c0 = clips[master_clip]
    disp_w, disp_h = (c0.height, c0.width) if abs(c0.rotation) % 180 == 90 else (c0.width, c0.height)
    rf = getattr(cl, "reframe", None)
    if rf is not None:  # a reel has its own size, so never the project settings
        disp_w, disp_h = rf.width, rf.height
        force_way = force_way or "timeline"
    notes: list[str] = []

    mp = p.GetMediaPool()
    by_path = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    missing = [clips[c].path for c in used if clips[c].path not in by_path]
    if missing:
        bridge.import_clips([Path(m) for m in missing], bin_name)
        by_path = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    mpi = {cid: by_path.get(clips[cid].path) for cid in used}
    if any(v is None for v in mpi.values()):
        raise BuildError(f"Clips nicht im Media Pool: {[k for k, v in mpi.items() if v is None]}. Nichts gebaut.")
    # Everything goes into the pool before the timeline gets its first item: ImportMedia after B-roll was placed ended in std::out_of_range (NOTES, Phase 10)
    for paths, target in (([g["mov"] for g in graphics or []], tool_bin("Grafiken")), ([c["file"] for c in sfx or []], tool_bin("SFX")),
                          ([clips[o.media].path for o in overlays or [] if getattr(o, "kind", "still") == "video" and o.media in clips], bin_name)):
        if paths:
            bridge.import_clips([Path(x) for x in dict.fromkeys(paths)], target)
    clip_bad = [f"{c}={v}" for c, v in fps_readback(p, mpis=mpi)["clip_fps"].items() if v is None or abs(v - fps) > 0.005]
    if clip_bad:
        raise BuildError(f"Clip-FPS in Resolve {', '.join(clip_bad)} ≠ {fps:g} (Clip-Attribute geändert?). Nichts gebaut.")

    # way 1: empty project -> set the project rate (playback rate may not follow: checked per timeline below)
    rb0 = fps_readback(p)
    if _mismatch(rb0, fps) and p.GetTimelineCount() == 0:
        p.SetSettings({"timelineFrameRate": fps_setting(fps)})
        p.SetSettings({"timelineResolutionWidth": str(disp_w), "timelineResolutionHeight": str(disp_h)})
        notes.append(f"Projekt „{p.GetName()}“ war leer: Projekt-Framerate {rb0['project_fps']:g} → {fps_setting(fps)}")

    existing = {p.GetTimelineByIndex(i + 1).GetName() for i in range(p.GetTimelineCount())}
    frame_tol = 1.0 / fps + 1e-6
    folder = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="schnippo_"))

    def tl_rates_ok(tl) -> list[str]:
        return _mismatch(fps_readback(p, tl), fps, keys=("timeline_fps", "timeline_playback_fps"))

    def drop(tl) -> None:  # only ever called for a timeline this call has just created and that holds nothing
        mp.DeleteTimelines([tl])

    def make(name: str, plist: list, marker_rows: list[tuple[int, str, str, str]], crossfade: int,
             expect_seconds: float | None) -> dict:
        tl_name = _unique_name(existing, name)
        existing.add(tl_name)
        attempts: list[str] = []
        tl, way = None, None
        recs, rec = [], 0
        for pc in plist:
            recs.append(rec)
            rec += pc.frames

        # way 1: project (already right or just set)
        bad = _mismatch(fps_readback(p), fps)
        if force_way in ("timeline", "fcpxml"):  # testing: skip the earlier ways
            bad = bad or [f"übersprungen (force_way={force_way})"]
        if not bad:
            tl = mp.CreateEmptyTimeline(tl_name)
            if tl is not None:
                p.SetCurrentTimeline(tl)
                bad = tl_rates_ok(tl)
                if bad:
                    attempts.append(f"Projekt-Einstellungen → {', '.join(bad)}")
                    drop(tl)
                    tl = None
                else:
                    way = "Projekt-Einstellungen"
        else:
            attempts.append(f"Projekt {', '.join(bad)}")
        # way 2: whole rate -> own timeline settings
        if tl is None and _is_whole(fps) and force_way != "fcpxml":
            t2 = mp.CreateEmptyTimeline(tl_name)
            if t2 is not None:
                p.SetCurrentTimeline(t2)
                ok1 = t2.SetSettings({"useCustomSettings": "1"})
                ok2 = t2.SetSettings({"timelineFrameRate": fps_setting(fps)})
                t2.SetSettings({"timelineResolutionWidth": str(disp_w), "timelineResolutionHeight": str(disp_h)})
                bad = tl_rates_ok(t2)
                if bad or not (ok1 and ok2):
                    attempts.append(f"eigene Timeline-Einstellungen (SetSettings {ok1}/{ok2}) → {', '.join(bad) or 'Fehler'}")
                    drop(t2)
                else:
                    tl, way = t2, "eigene Timeline-Einstellungen"
        # way 3: FCPXML import
        if tl is None:
            num, den = _fps_fraction(fps)
            f = folder / f"{tl_name}.fcpxml"
            assets = {cid: {"path": clips[cid].path, "frames": int(mpi[cid].GetClipProperty("Frames") or 0),
                            "tc_frames": _tc_frames(mpi[cid].GetClipProperty("Start TC"), fps), "name": Path(clips[cid].path).name,
                            "audio_channels": clips[cid].audio_channels or 2} for cid in used}
            write_fcpxml(f, tl_name, num, den, disp_w, disp_h, assets, [(pc.clip, pc.start_frame, pc.end_frame) for pc in plist],
                         [(fr, mname, note) for fr, _, mname, note in marker_rows])
            src_folders = list({id(mpi[c].GetParentFolder()): mpi[c].GetParentFolder() for c in used}.values())
            t3 = mp.ImportTimelineFromFile(str(f), {"timelineName": tl_name, "importSourceClips": False,
                                                    "sourceClipsFolders": src_folders})
            if t3 is None:
                attempts.append("FCPXML-Import fehlgeschlagen")
            else:
                p.SetCurrentTimeline(t3)
                bad = tl_rates_ok(t3)
                if bad:
                    attempts.append(f"FCPXML-Import → {', '.join(bad)}")
                    drop(t3)
                else:
                    tl, way = t3, "FCPXML-Import"
        if tl is None:
            raise BuildError(FAIL_HELP.format(fps=fps_setting(fps), attempts="; ".join(attempts)) + " Es wurde nichts gebaut.")

        t0 = tl.GetStartFrame()
        if way != "FCPXML-Import":
            infos = [{"mediaPoolItem": mpi[pc.clip], "startFrame": pc.start_frame, "endFrame": pc.end_frame,
                      "recordFrame": t0 + rc, "trackIndex": 1} for pc, rc in zip(plist, recs)]
            mp.AppendToTimeline(infos)
        chan_info = remap_channels(tl, mpi, channel_plans or {})
        items = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
        rb_tl = fps_readback(p, tl, mpi)
        errors = [f"Framerate: {b} (Soll {fps:g})" for b in _mismatch(rb_tl, fps, keys=("timeline_fps", "timeline_playback_fps"))]
        if len(items) != len(plist):
            errors.append(f"{len(items)} Video-Items statt {len(plist)}")
        # custom-settings timelines report no playback rate; they play at their own timeline rate
        # (confirmed by listening test 2026-11-04, see NOTES – the API offers no way to measure it)
        tl_play = rb_tl.get("timeline_playback_fps") or rb_tl.get("timeline_fps") or fps
        for k, (pc, it, rc) in enumerate(zip(plist, items, recs)):
            got = (it.GetStart() - t0, it.GetDuration(), it.GetLeftOffset())
            want = (rc, pc.frames, pc.start_frame)
            if got != want:
                errors.append(f"Stück {k + 1}: Position/Dauer/Quell-Offset {got} ≠ Soll {want}")
                continue
            src_s = pc.frames / (clips[pc.clip].resolve_fps or clips[pc.clip].fps)
            tl_s = (it.GetDuration() or 0) / tl_play
            if abs(tl_s - src_s) > frame_tol:
                errors.append(f"Stück {k + 1}: {tl_s:.3f}s auf der Timeline ≠ {src_s:.3f}s Quelle")
            auds = [a for a in (it.GetLinkedItems() or []) if a.GetType() == "audio"]
            if not auds:  # imported timelines may not link A/V: match by position on A1
                auds = [a for a in (tl.GetItemListInTrack("audio", 1) or []) if a.GetStart() == it.GetStart()]
            if not auds or (auds[0].GetStart(), auds[0].GetDuration()) != (it.GetStart(), it.GetDuration()):
                errors.append(f"Stück {k + 1}: Audio fehlt oder weicht ab")
        if chan_info.get("errors"):
            errors += chan_info["errors"]
        n_zoom = 0
        for k, (pc, it) in enumerate(zip(plist, items)):
            fill = getattr(pc, "fill", False)
            if fill:
                it.SetProperties({"Scaling": r.SCALE_FILL})
                if it.GetProperty("Scaling") != r.SCALE_FILL:
                    errors.append(f"Stück {k + 1}: Scaling {it.GetProperty('Scaling')} ≠ Fill")
            if fill or (getattr(pc, "zoom", 1.0) and pc.zoom != 1.0):
                want_p = {"ZoomX": pc.zoom, "ZoomY": pc.zoom, "Pan": pc.pan, "Tilt": pc.tilt}
                it.SetProperties(want_p)
                got_p = {key: it.GetProperty(key) for key in want_p}
                if any(abs(float(got_p[key] or 0) - v) > 0.01 for key, v in want_p.items()):
                    errors.append(f"Stück {k + 1}: Punch-in {want_p} ≠ gelesen {got_p}")
                n_zoom += pc.zoom != 1.0
        tl_frames = tl.GetEndFrame() - t0 if items else 0
        tl_seconds = tl_frames / tl_play if tl_play else 0.0
        if tl_frames != rec:
            errors.append(f"Timeline-Länge {tl_frames} ≠ Soll {rec} Frames")
        if expect_seconds is not None and abs(tl_seconds - expect_seconds) > frame_tol:
            errors.append(f"Timeline-Dauer {tl_seconds:.3f}s ≠ validate_cutlist {expect_seconds:.3f}s")
        have = set((tl.GetMarkers() or {}).keys())
        n_markers_file = len(have)
        for frame, color, mname, note in marker_rows:
            if frame not in have:
                tl.AddMarker(frame, color, mname, note[:250], 1)
        markers = tl.GetMarkers() or {}
        if any(frame not in markers for frame, *_ in marker_rows):
            errors.append("Marker fehlen")
        n_x = 0
        if crossfade and not errors:
            audio_items = sorted(tl.GetItemListInTrack("audio", 1) or [], key=lambda a: a.GetStart())
            audio_items = [a for a in audio_items if a.GetType() == "audio"]
            for a, b in zip(audio_items, audio_items[1:]):
                if a.GetEnd() == b.GetStart():
                    n_x += a.AddTransition({"type": "Cross Fade 0 dB", "category": "audio", "position": "end",
                                            "alignment": "center", "duration": crossfade}) is not None
            for k, (pc, it, rc) in enumerate(zip(plist, items, recs)):
                if (it.GetStart() - t0, it.GetDuration()) != (rc, pc.frames):
                    errors.append(f"Stück {k + 1}: nach Überblendung verändert")
        return {"name": tl_name, "way": way, "attempts": attempts, "pieces": len(plist), "frames": tl_frames,
                "seconds": round(tl_seconds, 3), "expected_seconds": None if expect_seconds is None else round(expect_seconds, 3),
                "verified": not errors, "errors": errors, "markers": len(markers), "markers_from_file": n_markers_file,
                "crossfades": n_x, "cuts": max(0, len(plist) - 1), "readback": rb_tl, "punch_ins": n_zoom,
                "audio_channels": chan_info}

    rows, pos, seen = [], 0, set()
    for pc in pieces:
        if pc.item not in seen and cl.markers:
            seen.add(pc.item)
            it = cl.items[pc.item - 1]
            first = " ".join(pc.text.split()[:5])
            rows.append((pos, "Blue", f"#{pc.item:02d} {first}…", f"{it.clip}:{it.from_word}–{it.to_word}"
                         + (f" · {it.note}" if it.note else "")))
        pos += pc.frames
    say = progress or (lambda msg: None)
    stage = on_stage or (lambda name, info=None: None)
    # built under "<name>_unvollstaendig" and renamed only when every stage ran: an abort (crash, kill, Resolve gone)
    # leaves a clearly marked timeline, never one that looks finished
    final = _unique_name(existing, cl.timeline_name)
    existing.add(final)
    say(f"Timeline wird angelegt ({len(pieces)} Teilstücke)")
    main = make(final + INCOMPLETE, pieces, rows, audio_crossfade_frames, plan_seconds)
    stage("timeline", {"tmp": main["name"], "final": final})
    say(f"Timeline „{main['name']}“ steht, wird geprüft")
    if overlays:
        say(f"B-Roll: {len(overlays)} Overlays")
        tl_main = find_timeline(p, main["name"])
        settle(p, tl_main)
        main["overlays"] = place_overlays(bridge, r, p, tl_main, overlays, stills or {}, bin_name, fps, disp_w, disp_h,
                                          folder / "broll", pieces, clips)
        if any(not o["verified"] for o in main["overlays"]):
            main["verified"] = False
            main["errors"] += [e for o in main["overlays"] for e in o["errors"]]
        stage("overlays")
    if graphics:
        tl_main = find_timeline(p, main["name"])
        settle(p, tl_main)
        main["graphics"] = place_graphics(bridge, p, tl_main, graphics, bin_name)
        if any(not g["verified"] for g in main["graphics"]):
            main["verified"] = False
            main["errors"] += [e for g in main["graphics"] for e in g["errors"]]
        stage("graphics")
    if sfx:
        say(f"Sound-Effekte: {len(sfx)}")
        tl_main = find_timeline(p, main["name"])
        settle(p, tl_main)
        main["sfx"] = place_sfx(bridge, p, tl_main, sfx)
        if any(not c["verified"] for c in main["sfx"]):
            main["verified"] = False
            main["errors"] += [e for c in main["sfx"] for e in c["errors"]]
        stage("sfx")
    if getattr(cl, "audio", None) is not None:
        tl_main = find_timeline(p, main["name"])
        settle(p, tl_main)
        try:
            voice_tracks = (tl_main.GetTrackCount("audio") or 1) - len(sfx_tracks(tl_main))
            dup = voice_tracks > 1 and (channel_plans or {}).get(master_clip, {}).get("class") == "identisch"
            from .delivery import ensure_check_preset, ensure_delivery_preset
            exp = Path(export_dir) if export_dir else folder / "export"
            presets = {"check": lambda: ensure_check_preset(r, p),
                       "delivery": lambda: ensure_delivery_preset(r, p, fmt, exp, final)}
            say("Ton: Lautheit wird per Prüf-Render eingestellt (dauert je nach Länge Minuten)")
            main["audio"] = apply_audio(r, p, tl_main, cl.audio, audio_spectrum, folder / "audio", duplicate_tracks=dup,
                                        progress=say,
                                        presets=presets, aroll_paths={clips[c].path for c in used})
        except Exception as e:  # a failed check render must not swallow the receipt
            main["audio"] = {"before": {}, "after": {}, "gain_db": None, "delivery_preset": None, "chain": [], "iterations": 0, "actions": [],
                             "notes": [f"Audio-Stufe abgebrochen: {type(e).__name__}: {e}"], "lufs_ok": False, "tp_ok": False}
        if not main["audio"]["lufs_ok"]:
            main["verified"] = False
            main["errors"].append(f"Lautheit {main['audio']['after'].get('lufs')} LUFS außerhalb "
                                  f"{cl.audio.target_lufs}±{cl.audio.tolerance_lu}")
        if not main["audio"]["tp_ok"]:
            main["verified"] = False
            main["errors"].append(f"True Peak {main['audio']['after'].get('true_peak')} dBTP über {cl.audio.true_peak_max}")
        stage("audio")
    tl_done = find_timeline(p, main["name"])
    if not tl_done.SetName(final):
        main["errors"].append(f"Umbenennen von „{main['name']}“ in „{final}“ abgelehnt – Timeline trägt noch den Zusatz")
        main["verified"] = False
    else:
        main["name"] = final
    stage("fertig", {"final": main["name"]})
    receipt = {"project": p.GetName(), "fps": fps, "master_clip": master_clip, "timeline": main, "notes": notes}
    if alternates:
        rows, pos, last = [], 0, None
        for pc, reason in alternates:
            if reason != last:
                rows.append((pos, "Red", "verworfen", reason))
                last = reason
            pos += pc.frames
        alt_s = sum(pc.frames for pc, _ in alternates) / fps
        receipt["alternates"] = make(f"{main['name']}_Alternativen", [pc for pc, _ in alternates], rows, 0, alt_s)
    for i in range(p.GetTimelineCount()):
        if p.GetTimelineByIndex(i + 1).GetName() == main["name"]:
            p.SetCurrentTimeline(p.GetTimelineByIndex(i + 1))
    pm.SaveProject()
    return receipt


def place_overlays(bridge, r, p, tl, overlays: list, stills: dict, bin_name: str, fps: float, width: int, height: int,
                   render_dir, pieces: list, clips: dict | None = None) -> list[dict]:
    """Put still overlays on upper tracks (video only) and verify position, length, track and framing properties.

    Native when Resolve can express it (centered fill, Dynamic Zoom out); otherwise the still is rendered to a ProRes
    clip in the timeline format (kenburns.render_still). Stills ignore endFrame on append (always the project's still
    duration) → trimmed afterwards with SetRightOffset.
    """
    from pathlib import Path

    from .kenburns import needs_render, render_still

    mp = p.GetMediaPool()
    t0 = tl.GetStartFrame()
    v1_before = [(i.GetStart(), i.GetDuration()) for i in tl.GetItemListInTrack("video", 1) or []]
    num, den = _fps_fraction(fps)
    ahead = {}  # all stills first: nothing is imported once the first overlay lies on the timeline
    for ov in overlays:
        st = stills.get(ov.media)
        if getattr(ov, "kind", "still") != "video" and st is not None:
            needs = ov.fit == "fill" and needs_render(ov.motion, ov.focus)
            ahead[ov.index] = render_still(Path(st.path), Path(render_dir), width, height, num, den, ov.frames, ov.motion, ov.focus, st.rotation) if needs else Path(st.path)
    if ahead:
        bridge.import_clips(list(ahead.values()), tool_bin("Standbilder"))
    results = []
    for ov in sorted(overlays, key=lambda o: o.tl_start):
        errs: list[str] = []
        if getattr(ov, "kind", "still") == "video":
            results.append(_place_video_overlay(bridge, p, mp, tl, ov, (clips or {}).get(ov.media), bin_name, t0))
            continue
        st = stills.get(ov.media)
        if st is None:
            results.append({"index": ov.index, "media": ov.media, "verified": False, "errors": [f"O{ov.index}: Standbild {ov.media} unbekannt"]})
            continue
        while tl.GetTrackCount("video") < ov.track:
            tl.AddTrack("video")
        render = ov.fit == "fill" and needs_render(ov.motion, ov.focus)
        path = ahead[ov.index]
        by_path = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
        if str(path) not in by_path:
            bridge.import_clips([path], tool_bin("Standbilder"))
            by_path = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
        item = by_path.get(str(path))
        if item is None:
            results.append({"index": ov.index, "media": ov.media, "verified": False, "errors": [f"O{ov.index}: Import von {path.name} fehlgeschlagen"]})
            continue
        info = {"mediaPoolItem": item, "recordFrame": t0 + ov.tl_start, "trackIndex": ov.track, "mediaType": 1}
        if render:
            info.update({"startFrame": 0, "endFrame": ov.frames})
        got = mp.AppendToTimeline([info]) or []
        it = got[0] if got else None
        if it is None or it.GetStart() is None:
            results.append({"index": ov.index, "media": ov.media, "verified": False, "errors": [f"O{ov.index}: AppendToTimeline fehlgeschlagen"]})
            continue
        if not render and it.GetDuration() != ov.frames:  # still: default duration → trim to the word range
            it.SetRightOffset(it.GetRightOffset() + (it.GetDuration() - ov.frames))
        props: dict = {}
        if not render:
            props["Scaling"] = r.SCALE_FILL if ov.fit == "fill" else r.SCALE_FIT
            if ov.motion == "slow_zoom_out":
                props.update({"DynamicZoomEnabled": True, "DynamicZoomEase": r.DYNAMIC_ZOOM_EASE_LINEAR})
            if not it.SetProperties(props):
                errs.append(f"O{ov.index}: SetProperties {list(props)} abgelehnt")
        # verification
        on_track = [x for x in tl.GetItemListInTrack("video", ov.track) or [] if x.GetStart() == it.GetStart()]
        if (it.GetStart() - t0, it.GetDuration()) != (ov.tl_start, ov.frames):
            errs.append(f"O{ov.index}: Position/Dauer {(it.GetStart() - t0, it.GetDuration())} ≠ Soll {(ov.tl_start, ov.frames)}")
        if not on_track:
            errs.append(f"O{ov.index}: nicht auf Spur V{ov.track}")
        if [a for a in (it.GetLinkedItems() or []) if a.GetType() == "audio"]:
            errs.append(f"O{ov.index}: hat Audio")
        for k, v in props.items():
            if k != "DynamicZoomEase" and it.GetProperty(k) != v:
                errs.append(f"O{ov.index}: {k} = {it.GetProperty(k)} ≠ {v}")
        results.append({"index": ov.index, "media": ov.media, "way": "gerendert (ffmpeg, nur Standbild)" if render else
                        ("nativ + Dynamic Zoom" if ov.motion == "slow_zoom_out" else "nativ"), "track": ov.track,
                        "tl_start": ov.tl_start, "frames": ov.frames, "file": path.name, "verified": not errs, "errors": errs})
    if [(i.GetStart(), i.GetDuration()) for i in tl.GetItemListInTrack("video", 1) or []] != v1_before:
        results.append({"index": 0, "media": "V1", "verified": False, "errors": ["V1 wurde durch Overlays verändert"]})
    return results


def _place_video_overlay(bridge, p, mp, tl, ov, clip, bin_name: str, t0: int) -> dict:
    """Video B-roll on an upper track: picture only (mute by default), source frames counted at the clip's own rate
    (measured: 100 frames @50 fps = 50 frames in a 25-fps timeline), slow motion via TimelineItem.SetSpeed on the item
    (keeps length and in-point, shows every source frame once; the clip's FPS attribute stays untouched)."""
    from pathlib import Path as _P

    errs: list[str] = []
    res = {"index": ov.index, "media": ov.media, "track": ov.track, "tl_start": ov.tl_start, "frames": ov.frames,
           "way": "Video-B-Roll" + (" · Zeitlupe 50 %" if ov.speed < 1 else ""), "verified": False, "errors": errs}
    if clip is None:
        errs.append(f"O{ov.index}: Clip {ov.media} unbekannt")
        return res
    by_path = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    if clip.path not in by_path:
        bridge.import_clips([_P(clip.path)], bin_name)
        by_path = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    item = by_path.get(clip.path)
    if item is None:
        errs.append(f"O{ov.index}: Import von {_P(clip.path).name} fehlgeschlagen")
        return res
    while (tl.GetTrackCount("video") or 1) < ov.track:
        tl.AddTrack("video")
    got = mp.AppendToTimeline([{"mediaPoolItem": item, "startFrame": ov.src_start, "endFrame": ov.src_start + ov.src_frames,
                                "recordFrame": t0 + ov.tl_start, "trackIndex": ov.track, "mediaType": 1}]) or []
    it = got[0] if got else None
    if it is None or it.GetStart() is None:
        errs.append(f"O{ov.index}: AppendToTimeline fehlgeschlagen")
        return res
    if ov.speed != 1.0:
        if not it.SetSpeed({"Percentage": ov.speed * 100, "RippleTimeline": False}):
            errs.append(f"O{ov.index}: SetSpeed {ov.speed * 100:g} % abgelehnt")
        res["speed_readback"] = (it.GetSpeed() or {}).get("Percentage")
    if (it.GetStart() - t0, it.GetDuration()) != (ov.tl_start, ov.frames):
        errs.append(f"O{ov.index}: Position/Dauer {(it.GetStart() - t0, it.GetDuration())} ≠ Soll {(ov.tl_start, ov.frames)}")
    if [a for a in (it.GetLinkedItems() or []) if a.GetType() == "audio"]:
        errs.append(f"O{ov.index}: B-Roll hat Ton (soll stumm sein)")
    if getattr(ov, "audio", "mute") == "atmo":  # quiet ambience on its own track
        n = tl.GetTrackCount("audio") or 1
        tl.AddTrack("audio", "stereo")
        ga = mp.AppendToTimeline([{"mediaPoolItem": item, "startFrame": ov.src_start, "endFrame": ov.src_start + ov.src_frames,
                                   "recordFrame": t0 + ov.tl_start, "trackIndex": n + 1, "mediaType": 2}]) or []
        if ga:
            ga[0].SetProperties({"AudioVolume": -20.0})
            res["atmo_track"] = n + 1
        else:
            errs.append(f"O{ov.index}: Atmo-Ton nicht angelegt")
    if getattr(ov, "fill_video", False):  # reel: the crop of the B-roll, last, on a settled item
        it.SetProperties({"Scaling": bridge.resolve().SCALE_FILL, "Pan": ov.pan})
        if abs(float(it.GetProperty("Pan") or 0) - ov.pan) > 0.01:
            errs.append(f"O{ov.index}: Pan {it.GetProperty('Pan')} ≠ {ov.pan}")
    res["file"] = _P(clip.path).name
    res["verified"] = not errs
    return res


ATMO_BELOW_LU = 20.0  # B-roll ambience sits this far under the programme target (quiet, but audible)


def _level_atmo(tl, items: list, path_of, target: float) -> str:
    """Atmo clips keep their own level: measured on their source range (ebur128), set to target LUFS by clip volume,
    no limiter. Fixed −20 dB was inaudible after the programme gain (Phase 8: speech +22.9 dB)."""
    from .audio import ebur128
    try:
        fps = float(tl.GetSetting("timelineFrameRate") or 25)
    except Exception:
        fps = 25.0
    done = []
    for a in items:
        src = path_of(a)
        off = a.GetLeftOffset() if hasattr(a, "GetLeftOffset") else 0
        lufs = ebur128(["-ss", f"{off / fps:.3f}", "-t", f"{a.GetDuration() / fps:.3f}", "-i", src]).get("lufs") if src else None
        if lufs is None or lufs < -70:
            continue
        vol = max(-60.0, min(24.0, round(target - lufs, 1)))
        a.SetProperties({"AudioVolume": vol})
        done.append(f"{lufs:.1f} → {target:.0f} LUFS ({vol:+.1f} dB)")
    return (f"{len(items)} B-Roll-Atmo-Clip(s) ohne Limiter auf eigenem Pegel: " + "; ".join(done)) if done else \
        f"{len(items)} B-Roll-Atmo-Clip(s) ausgenommen (Pegel nicht messbar, bleiben bei −20 dB)"


def apply_audio(r, p, tl, opts, spectrum: dict | None, out_dir, render=None, measure=None,
                duplicate_tracks: bool = False, presets: dict | None = None, aroll_paths: set | None = None,
                progress=None, keep_renders: bool = False) -> dict:
    """Clip volume + Fairlight FX on the A1 items, iterated against check renders (true peak has priority).

    Measured on 21.1.2 (see docs/ENTWICKLUNG.md): AudioVolume acts before clip FX; FX come
    with default parameters only; the Limiter's ceiling ≈ −0.2 dBTP; the Deliver-page render normalization (reachable via
    a render preset) is applied *before* the clip FX, so it cannot create headroom after the limiter. Working chain:
    Limiter → Multiband Compressor (defaults): the compressor after the limiter acts as a post-limiter level reduction
    → −14 LUFS at ≈ −2.8 dBTP (cost: ~+5 dB room noise in pauses relative to speech, highs > 5 kHz +3–5 dB).
    tp_strategy "limiter_only" keeps the Phase-4 chain (TP ≈ −0.2, reported openly).

    presets: {"check": () -> name (normalization off), "delivery": () -> name (H.264 export preset, loaded at the end)}.
    """
    from .audio import ebur128
    from .render import render_timeline

    for old in Path(out_dir).glob("audio_*.mov") if Path(out_dir).exists() else []:  # left by an interrupted build
        old.unlink(missing_ok=True)
    render = render or (lambda tag, preset=None: render_timeline(p, tl, out_dir, tag, video=False, audio=True, preset=preset))
    _render, made = render, []

    def render(tag, preset=None):  # noqa: F811 – report every check render (the slow part), remember it for cleanup
        if progress:
            progress(f"Ton: Prüf-Render „{tag}“")
        f = _render(tag, preset)
        made.append(f)
        return f
    try:
        return _apply_audio(r, p, tl, opts, spectrum, out_dir, render, measure, duplicate_tracks, presets, aroll_paths)
    finally:
        if not keep_renders:  # check renders only serve the measurement (they piled up to 128 GB in Phase 8)
            for f in made:
                try:
                    Path(str(f)).unlink(missing_ok=True)
                except (OSError, TypeError):
                    pass


def _apply_audio(r, p, tl, opts, spectrum, out_dir, render, measure, duplicate_tracks, presets, aroll_paths):
    from .audio import ebur128
    measure = measure or (lambda f: ebur128(["-i", str(f)]))
    actions, notes = [], []
    presets = presets or {}
    check = None
    if "check" in presets:
        try:
            check = presets["check"]()
        except Exception as e:  # without it a loaded delivery/user preset may normalize the check renders
            notes.append(f"Prüf-Preset nicht angelegt: {e}")
    fx = sfx_tracks(tl)  # the effects keep their own level: no limiter, no programme gain
    voice = [k for k in range(1, (tl.GetTrackCount("audio") or 1) + 1) if k not in fx]
    n_tracks = len(voice)
    if n_tracks > 1:
        if duplicate_tracks:
            for k in voice[1:]:
                tl.SetTrackEnable("audio", k, False)
                # renders with a loaded render preset still played a disabled track (21.1.2, measured) → also clip volume
                for a in tl.GetItemListInTrack("audio", k) or []:
                    a.SetProperties({"AudioVolume": -100.0})
            actions.append(f"A2–A{n_tracks} stummgeschaltet (Spur aus + Clip-Lautstärke −100 dB): identische Kopie der Tonspur")
        else:
            notes.append(f"{n_tracks} Audiospuren mit unterschiedlichem Inhalt: Verstärkung/Limiter auf allen Spuren")
    tracks = voice[:1] if duplicate_tracks or n_tracks == 1 else voice
    auds = [a for k in tracks for a in (tl.GetItemListInTrack("audio", k) or []) if a.GetType() == "audio"]
    if aroll_paths:  # B-roll ambience (atmo) keeps its own quiet level – gain/limiter only on the A-roll
        def _path(a):
            m = a.GetMediaPoolItem() if hasattr(a, "GetMediaPoolItem") else None
            return m.GetClipProperty("File Path") if m else None
        keep = [a for a in auds if _path(a) in aroll_paths or _path(a) is None]
        atmo = [a for a in auds if a not in keep]
        if atmo:
            notes.append(_level_atmo(tl, atmo, _path, opts.target_lufs - ATMO_BELOW_LU))
        auds = keep
    before = measure(render("audio_before", check))
    fx = {e["name"]: e["id"] for e in (r.GetEffectsList("audio") or [])}
    props = {}
    if opts.dialogue_leveler:
        props["AudioDialogueLevelerEnabled"] = True
        actions.append("Dialogue Leveler an (Option)")
    if opts.voice_isolation:
        props["AudioVoiceIsolationEnabled"] = True
        actions.append("Voice Isolation an (Option)")
    sib = (spectrum or {}).get("sibilance_db")
    deess = opts.deesser == "on" or (opts.deesser == "auto" and sib is not None and sib > 4)
    post = opts.limiter and opts.tp_strategy == "post_compressor" and "Multiband Compressor" in fx
    if opts.limiter and opts.tp_strategy == "post_compressor" and not post:
        notes.append("Multiband Compressor nicht in der FX-Liste → nur Limiter (True Peak ≈ −0,2 dBTP)")
    for a in auds:
        if props:
            a.SetProperties(props)
        if deess and "De-Esser" in fx:
            a.AddEffect("audio", fx["De-Esser"])
        if opts.limiter and "Limiter" in fx:
            a.AddEffect("audio", fx["Limiter"])
        if post:
            a.AddEffect("audio", fx["Multiband Compressor"])
    if deess:
        actions.append(f"De-Esser (Standardwerte){f' – Zischlaute {sib:+.1f} dB über Referenz' if sib is not None else ''}")
    elif sib is not None:
        notes.append(f"kein De-Esser: Zischlaute {sib:+.1f} dB gegenüber Referenz (Schwelle +4 dB)")
    if opts.limiter:
        actions.append("Fairlight Limiter (Standard-Ceiling ≈ −0,2 dBTP)" + (" → Multiband Compressor (Standardwerte) dahinter "
                       "als Pegel-Reserve für True Peak ≤ −1 dBTP" if post else "") + " auf allen Audio-Clips")
    after, gain, iterations, last = before, 0.0, 0, None
    if opts.normalize and before.get("lufs") is not None:
        gain = opts.target_lufs - before["lufs"] + (opts.post_compressor_offset_db if post else 0.0)
        for iterations in range(1, opts.max_iterations + 1):
            for a in auds:
                a.SetProperties({"AudioVolume": max(-100.0, min(30.0, gain))})
            last = render(f"audio_it{iterations}", check)
            after = measure(last)
            if after.get("lufs") is None or abs(after["lufs"] - opts.target_lufs) <= opts.tolerance_lu or gain >= 30.0:
                break
            gain = min(30.0, gain + opts.target_lufs - after["lufs"])
        actions.insert(0, f"Programm-Verstärkung {gain:+.1f} dB per Clip-Lautstärke (AudioVolume) auf {len(auds)} Clips")
        if gain >= 30.0:
            notes.append("Clip-Lautstärke am Maximum (+30 dB) – Quelle zu leise für das Ziel")
    lufs_ok = after.get("lufs") is not None and abs(after["lufs"] - opts.target_lufs) <= opts.tolerance_lu
    tp_ok = after.get("true_peak") is not None and after["true_peak"] <= opts.true_peak_max + 1e-9
    if not tp_ok and after.get("true_peak") is not None:
        notes.append(f"True Peak {after['true_peak']:+.1f} dBTP > {opts.true_peak_max:+.1f}: "
                     + ("Limiter-Ceiling per API nicht einstellbar (tp_strategy limiter_only)" if not post
                        else "trotz Kompressor hinter dem Limiter"))
    balance = None
    if last is not None and Path(str(last)).exists():
        from .audio import channel_balance
        balance = channel_balance(Path(str(last)))
        if balance.get("diff_db") is not None and balance["diff_db"] > 0.5:
            notes.append(f"Ausgang ungleich: L/R {balance['rms_db']} dB")
    delivery = None
    if "delivery" in presets:
        try:
            delivery = presets["delivery"]()
            actions.append(f"Export-Preset „{delivery}“ (H.264/AAC) im Deliver-Tab geladen")
        except Exception as e:
            notes.append(f"Export-Preset nicht angelegt: {e}")
    return {"before": before, "after": after, "gain_db": round(gain, 2), "iterations": iterations, "actions": actions,
            "notes": notes, "lufs_ok": lufs_ok, "tp_ok": tp_ok, "delivery_preset": delivery, "balance": balance, "chain":
            (["De-Esser"] if deess else []) + (["Limiter"] if opts.limiter else []) + (["Multiband Compressor"] if post else [])}

def place_graphics(bridge, p, tl, graphics: list[dict], bin_name: str) -> list[dict]:
    """Rendered ProRes 4444 graphics onto the upper video tracks (alpha read as straight – measured; set explicitly)."""
    from pathlib import Path as _P

    mp = p.GetMediaPool()
    paths = [g["mov"] for g in graphics]
    by = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    missing = [_P(x) for x in paths if x not in by]
    if missing:
        bridge.import_clips(missing, tool_bin("Grafiken"))
        by = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    t0 = tl.GetStartFrame()
    out = []
    for g in graphics:
        res = {**g, "verified": False, "errors": []}
        item = by.get(g["mov"])
        if item is None:
            res["errors"].append(f"Grafik G{g['index']}: nicht im Media Pool")
            out.append(res)
            continue
        if item.GetClipProperty("Alpha mode") != "Straight":
            item.SetClipProperty("Alpha mode", "Straight")
        while (tl.GetTrackCount("video") or 1) < g["track"]:
            tl.AddTrack("video")
        before = {(i.GetStart(), i.GetDuration()) for i in tl.GetItemListInTrack("video", g["track"]) or []}
        mp.AppendToTimeline([{"mediaPoolItem": item, "startFrame": 0, "endFrame": g["frames"], "recordFrame": t0 + g["tl_start"],
                              "trackIndex": g["track"], "mediaType": 1}])
        got = [(i.GetStart() - t0, i.GetDuration()) for i in tl.GetItemListInTrack("video", g["track"]) or []
               if (i.GetStart(), i.GetDuration()) not in before]
        res["placed"] = got[0] if got else None
        if got and got[0] == (g["tl_start"], g["frames"]):
            res["verified"] = True
        else:
            res["errors"].append(f"Grafik G{g['index']}: Position/Dauer {got} ≠ Soll ({g['tl_start']}, {g['frames']})")
        res["alpha"] = item.GetClipProperty("Alpha mode")
        out.append(res)
    v1 = tl.GetItemListInTrack("video", 1) or []
    if not v1:
        out.append({"index": 0, "verified": False, "errors": ["V1 leer nach dem Einfügen der Grafiken"]})
    return out


def settle(p, tl, wait: float = 0.6) -> None:
    """Between build stages: select the timeline only if it is not current, then give the UI a moment. Does not cure the open crash, see NOTES Phase 10."""
    import time
    cur = p.GetCurrentTimeline()
    if cur is None or cur.GetName() != tl.GetName():
        p.SetCurrentTimeline(tl)
    time.sleep(wait)


SFX_TRACK = "SFX"


def sfx_tracks(tl) -> list[int]:
    """SFX, SFX 2, …: what overlaps (a bed under a one-shot) needs a track of its own, on one track Resolve pushes it aside."""
    get = getattr(tl, "GetTrackName", None)
    if get is None:
        return []
    return [k for k in range(1, (tl.GetTrackCount("audio") or 0) + 1) if (get("audio", k) or "").startswith(SFX_TRACK)]


def lanes(cues: list[dict]) -> list[list[dict]]:
    """Cues on as few tracks as possible, none overlapping within a track (one frame of air for the length tolerance)."""
    out: list[list[dict]] = []
    for c in sorted(cues, key=lambda c: c["tl_start"]):
        lane = next((l for l in out if l[-1]["tl_start"] + l[-1]["frames"] + 1 <= c["tl_start"]), None)
        if lane is None:
            lane = []
            out.append(lane)
        lane.append(c)
    return out


def place_sfx(bridge, p, tl, cues: list[dict]) -> list[dict]:
    """Whole files on their own audio track. Without start/end the clip keeps its length; those would count in the
    project rate of the clip, not the timeline rate (measured on 21.1.2)."""
    from pathlib import Path as _P

    mp = p.GetMediaPool()
    by = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    missing = sorted({c["file"] for c in cues if c["file"] not in by})
    if missing:
        bridge.import_clips([_P(x) for x in missing], tool_bin("SFX"))
        by = {c.GetClipProperty("File Path"): c for c in _all_clips(mp.GetRootFolder())}
    plan = []
    for k, lane in enumerate(lanes(cues), 1):
        if not tl.AddTrack("audio", "stereo"):
            return [{**c, "verified": False, "errors": ["Spur SFX ließ sich nicht anlegen"]} for c in cues]
        n = tl.GetTrackCount("audio")
        tl.SetTrackName("audio", n, SFX_TRACK if k == 1 else f"{SFX_TRACK} {k}")
        plan += [(c, n) for c in lane]
    t0 = tl.GetStartFrame()
    out = []
    for c, n in sorted(plan, key=lambda p: p[0]["index"]):
        res = {**c, "track": n, "verified": False, "errors": []}
        out.append(res)
        item = by.get(c["file"])
        if item is None:
            res["errors"].append(f"S{c['index']} {c['id']}: nicht im Media Pool")
            continue
        before = {i.GetStart() for i in tl.GetItemListInTrack("audio", n) or []}
        mp.AppendToTimeline([{"mediaPoolItem": item, "recordFrame": t0 + c["tl_start"], "trackIndex": n, "mediaType": 2}])
        new = [i for i in tl.GetItemListInTrack("audio", n) or [] if i.GetStart() not in before]
        if not new:
            res["errors"].append(f"S{c['index']} {c['id']}: nicht auf der Spur angekommen")
            continue
        it = new[0]
        it.SetProperty("AudioVolume", c["volume_db"])
        got = float(it.GetProperty("AudioVolume") or 0)
        res.update(placed=(it.GetStart() - t0, it.GetDuration()), volume_read=got)
        if it.GetStart() - t0 != c["tl_start"] or abs(it.GetDuration() - c["frames"]) > 1:
            res["errors"].append(f"S{c['index']} {c['id']}: Position/Dauer {res['placed']} ≠ Soll ({c['tl_start']}, {c['frames']})")
        elif abs(got - c["volume_db"]) > 0.05:
            res["errors"].append(f"S{c['index']} {c['id']}: Lautstärke {got} ≠ Soll {c['volume_db']}")
        else:
            res["verified"] = True
    return out


def remap_channels(tl, mpi: dict, plans: dict) -> dict:
    """One audio track, chosen source channel centred (dual mono): per A1 item SetSourceAudioChannelMapping to the best
    channel as mono, then delete the extra audio tracks if they only hold copies of remapped clips. Real stereo stays.
    Measured on 21.1.2: a mono mapping on the stereo track A1 plays equally loud on L and R."""
    import json as _json

    by_path = {m.GetClipProperty("File Path"): cid for cid, m in mpi.items() if m is not None}
    todo = {cid: pl for cid, pl in plans.items() if pl and pl.get("class") in ("identisch", "unausgewogen", "verschieden",
                                                                               "je Sprecher") and pl.get("best")}
    info = {"plans": {cid: {k: pl.get(k) for k in ("class", "best", "reason", "by_speaker")} for cid, pl in plans.items() if pl},
            "mapped": 0, "errors": []}
    if not todo:
        return info
    info["tracks_before"] = tl.GetTrackCount("audio") or 0

    def clip_of(it):
        m = it.GetMediaPoolItem()
        return by_path.get(m.GetClipProperty("File Path")) if m else None

    for it in tl.GetItemListInTrack("audio", 1) or []:
        cid = clip_of(it)
        if cid not in todo:
            continue
        ch = int(todo[cid]["best"])
        by_start = todo[cid].get("by_start")
        if by_start:  # one mic per speaker: this piece's speaker decides (source in-point identifies the piece)
            off = it.GetLeftOffset() if hasattr(it, "GetLeftOffset") else None
            ch = int(by_start.get(off, by_start.get(str(off), ch)))
            info.setdefault("per_channel", {}).setdefault(ch, 0)
            info["per_channel"][ch] += 1
        cur = _json.loads(it.GetSourceAudioChannelMapping() or "{}")
        want = {"embedded_audio_channels": cur.get("embedded_audio_channels", 2), "linked_audio": cur.get("linked_audio", {}),
                "track_mapping": {"1": {"channel_idx": [ch], "mute": False, "type": "mono"}}}
        it.SetSourceAudioChannelMapping(_json.dumps(want))
        got = _json.loads(it.GetSourceAudioChannelMapping() or "{}").get("track_mapping", {})
        if got.get("1", {}).get("channel_idx") == [ch] and len(got) == 1:
            info["mapped"] += 1
        else:
            info["errors"].append(f"Kanalzuordnung nicht übernommen ({cid}): {got}")
    for k in range((tl.GetTrackCount("audio") or 1), 1, -1):
        extra = tl.GetItemListInTrack("audio", k) or []
        if all(clip_of(it) in todo for it in extra):
            if not tl.DeleteTrack("audio", k):
                info["errors"].append(f"Audiospur A{k} ließ sich nicht entfernen")
    info["tracks_after"] = tl.GetTrackCount("audio") or 0
    return info


def find_timeline(p, name: str | None):
    """Timeline by name (None → current)."""
    if not name:
        tl = p.GetCurrentTimeline()
        if tl is None:
            raise BuildError("keine Timeline geöffnet")
        return tl
    for i in range(p.GetTimelineCount()):
        tl = p.GetTimelineByIndex(i + 1)
        if tl.GetName() == name:
            return tl
    raise LookupError(f"Timeline „{name}“ nicht im Projekt „{p.GetName()}“")


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def read_timeline(bridge: "ResolveBridge", name: str | None, clips: dict) -> dict:
    """Read a timeline back for export/QC: V1 items (clip id via file path, source start, length, timeline position,
    zoom), audio items per track with enable state, upper video tracks, markers, rate readback."""
    p = bridge.project()
    tl = find_timeline(p, name)
    by_path = {c.path: cid for cid, c in clips.items()}
    t0 = tl.GetStartFrame()

    def mpi_clip(it):
        m = it.GetMediaPoolItem()
        return by_path.get(m.GetClipProperty("File Path")) if m else None

    v1 = []
    for it in sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart()):
        cid = mpi_clip(it)
        fps = (clips[cid].resolve_fps or clips[cid].fps) if cid else None
        v1.append({"clip": cid, "name": it.GetName(), "rec": it.GetStart() - t0, "frames": it.GetDuration(),
                   "src_start": it.GetLeftOffset(), "fps": fps, "zoom": float(it.GetProperty("ZoomX") or 1.0),
                   "pan": float(it.GetProperty("Pan") or 0), "tilt": float(it.GetProperty("Tilt") or 0), "scaling": it.GetProperty("Scaling"),
                   "linked_audio": [(a.GetStart() - t0, a.GetDuration()) for a in (it.GetLinkedItems() or [])
                                    if a.GetType() == "audio"]})
    audio = {}
    current = p.GetCurrentTimeline()
    p.SetCurrentTimeline(tl)  # GetIsTrackEnabled answers reliably only for the current timeline (21.1.2, measured)
    enabled = {k: bool(tl.GetIsTrackEnabled("audio", k)) for k in range(1, (tl.GetTrackCount("audio") or 0) + 1)}
    if current is not None and current.GetName() != tl.GetName():
        p.SetCurrentTimeline(current)
    for k in range(1, (tl.GetTrackCount("audio") or 0) + 1):
        audio[k] = {"enabled": enabled[k],
                    "items": [(a.GetStart() - t0, a.GetDuration()) for a in sorted(tl.GetItemListInTrack("audio", k) or [],
                                                                                  key=lambda i: i.GetStart())]}
    upper, upper_props = {}, []
    for k in range(2, (tl.GetTrackCount("video") or 0) + 1):
        upper[k] = [(it.GetName(), it.GetStart() - t0, it.GetDuration()) for it in tl.GetItemListInTrack("video", k) or []]
        upper_props += [{"rec": it.GetStart() - t0, "track": k, "scaling": it.GetProperty("Scaling"), "overlay": k == 2 and it.GetMediaPoolItem() is not None
                         and (it.GetMediaPoolItem().GetClipProperty("File Path") or "") in by_path} for it in tl.GetItemListInTrack("video", k) or []]
    rb = fps_readback(p, tl)
    sfx_items = sorted(({"rec": a.GetStart() - t0, "frames": a.GetDuration(), "name": a.GetName(), "volume": float(a.GetProperty("AudioVolume") or 0)}
                        for k in sfx_tracks(tl) for a in tl.GetItemListInTrack("audio", k) or []), key=lambda i: i["rec"])
    return {"project": p.GetName(), "name": tl.GetName(), "frames": tl.GetEndFrame() - t0, "v1": v1, "audio": audio, "sfx": sfx_items, "upper_props": upper_props,
            "scale_fill": getattr(bridge.resolve(), "SCALE_FILL", None), "size": (_int(tl.GetSetting("timelineResolutionWidth")), _int(tl.GetSetting("timelineResolutionHeight"))),
            "upper": upper, "markers": len(tl.GetMarkers() or {}), "readback": rb,
            "fps": rb.get("timeline_fps") or rb.get("project_fps")}


def measure_timeline_audio(bridge: "ResolveBridge", name: str | None, out_dir) -> dict:
    """Check render (own check preset, normalization off) + ebur128 → {lufs, true_peak, lra}."""
    from .audio import ebur128
    from .delivery import ensure_check_preset
    from .render import render_timeline

    r, p = bridge.resolve(), bridge.project()
    tl = find_timeline(p, name)
    current = p.GetCurrentTimeline()
    check = ensure_check_preset(r, p)
    try:
        f = render_timeline(p, tl, out_dir, "qc_audio", video=False, audio=True, preset=check)
    finally:
        if current is not None:
            p.SetCurrentTimeline(current)
    try:
        return ebur128(["-i", str(f)])
    finally:
        Path(str(f)).unlink(missing_ok=True)  # only needed for the measurement
