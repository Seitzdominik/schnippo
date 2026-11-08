"""Workspace = one ingested folder of takes. Holds the clip registry and orchestrates
ingest -> audio -> transcription -> analysis, all cached by content fingerprint.

Kept free of MCP so it can be tested and scripted directly.
"""

from __future__ import annotations

from . import platforms
import logging
import os
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import media
from .analysis import analyze
from .cache import Cache, fingerprint
from .config import Config
from .formatting import ts
from .models import AnalyzedTranscript, Clip, RawTranscript, Still
from . import context as ctx
from . import retakes
from .cutlist import Cutlist, CutOptions, Piece, Plan, build_plan, plan_item, plan_text
from .script import ScriptLine, load_script, match
from .segments import Segment, segment
from .acoustic import Acoustic, AcousticParams, analyze_wav
from .transcribe.base import get_provider, option_fingerprint

log = logging.getLogger("schnippo")


ETA_OVERHEAD_S = 6.0  # per transcription job: upload start, job creation, polling
ETA_PER_AUDIO_S = 0.018  # upload of 16-kHz mono PCM (~32 kB/s of audio) + processing, measured


def eta_seconds(durations: list[float], lanes: int = 3) -> float:
    """Wall time for transcribing clips of these durations, `lanes` jobs in parallel (longest first)."""
    acc = [0.0] * lanes
    for d in sorted(durations, reverse=True):
        acc[acc.index(min(acc))] += ETA_OVERHEAD_S + ETA_PER_AUDIO_S * d
    return max(acc) if durations else 0.0


class Workspace:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache = Cache(cfg.cache_dir)
        self.folder: Path | None = None
        self.clips: dict[str, Clip] = {}
        self.stills: dict[str, Still] = {}
        self.corrections: dict[str, str] = {}
        self.builds: dict[str, dict] = {}  # timeline name → cutlist (as built), for base_cutlist and exports
        self.content_choice: str | None = None  # interview | course | commercial | talking_head, set by the user for this folder
        self.format_choice: str | None = None  # reel | youtube | course | commercial, set by the user (set_format) for this folder
        self.reviews: dict[str, dict] = {}  # review id → {timeline, decisions, answers}
        self.roles: dict[str, str] = {}  # clip id → aroll | broll, set by the user (overrides the classification)
        self.glossary_terms: list[str] = []  # terms given in the chat (set_glossary), in addition to glossar.txt
        self.variants: dict[str, str] = {}  # clip id → tokens file used (word IDs stay valid when the glossary grows)
        self.script_path: str | None = None
        self.script: list[ScriptLine] | None = None
        self._restore_active()

    # ---------- persistence ----------
    def _active_file(self) -> Path:
        self.cache.root.mkdir(parents=True, exist_ok=True)
        return self.cache.root / "active_workspace.json"

    def _restore_active(self) -> None:
        data = Cache.read_json(self._active_file()) if self.cache.root.exists() else None
        if data and Path(data["folder"]).exists():
            self._load(Path(data["folder"]))

    def _load(self, folder: Path) -> None:
        reg = Cache.read_json(self.cache.workspace_file(folder)) or {}
        self.folder = folder
        os.environ["SCHNIPPO_MATERIAL"] = str(folder)  # read by the path rules (e.g. own font files in the material)
        self.clips = {cid: Clip(**c) for cid, c in reg.get("clips", {}).items()}
        self.stills = {sid: Still(**c) for sid, c in reg.get("stills", {}).items() if sid.startswith("i")}
        self.script_path = reg.get("script")
        self.corrections = dict(reg.get("corrections", {}))
        self.builds = dict(reg.get("builds", {}))
        self.format_choice = reg.get("format")
        self.content_choice = reg.get("content_type")
        self.reviews = dict(reg.get("reviews", {}))
        self.roles = dict(reg.get("roles", {}))
        self.glossary_terms = list(reg.get("glossary", []))
        self.variants = dict(reg.get("variants", {}))
        self.script = None
        if self.script_path and Path(self.script_path).exists():
            self.script = load_script(self.script_path)

    def _save(self) -> None:
        assert self.folder
        Cache.write_json(self.cache.workspace_file(self.folder),
                         {"folder": str(self.folder), "clips": {k: v.model_dump(exclude={"fps"}) for k, v in self.clips.items()},
                          "stills": {k: v.model_dump() for k, v in self.stills.items()}, "script": self.script_path,
                          "corrections": self.corrections, "builds": self.builds,
                          "format": self.format_choice, "content_type": self.content_choice, "reviews": self.reviews, "roles": self.roles,
                          "glossary": self.glossary_terms, "variants": self.variants})
        Cache.write_json(self._active_file(), {"folder": str(self.folder)})

    # ---------- ingest ----------
    def ingest(self, folder: str | Path, import_to_resolve: bool = False, recursive: bool = False,
               bridge=None) -> dict:
        from .guard import material_root
        folder = material_root(folder)
        self._load(folder)
        by_fp = {c.fingerprint: c for c in self.clips.values()}
        next_n = max([int(c[1:]) for c in self.clips] or [0]) + 1
        current: dict[str, Clip] = {}
        notes: list[str] = []
        from . import projects
        structured = projects.has_structure(folder)
        scan = recursive or structured  # A-Roll/, B-Roll/ … are part of the project; other subfolders stay out unless asked for

        def wanted(files: list[Path]) -> list[Path]:
            if not structured or recursive:
                return files
            keep = [p for p in files if projects.in_structure(p, folder)]
            if len(keep) < len(files):
                notes.append(f"{len(files) - len(keep)} Datei(en) in anderen Unterordnern nicht eingelesen")
            return keep

        for p in wanted(media.find_videos(folder, scan, notes)):
            fp = fingerprint(p)
            old = by_fp.get(fp)
            meta = media.clip_metadata(p) if old is None or old.path != str(p) else None
            if old is not None:
                clip = old if meta is None else old.model_copy(update={"path": str(p), **meta})
            else:
                clip = Clip(id=f"c{next_n:02d}", path=str(p), fingerprint=fp, **meta)
                next_n += 1
            current[clip.id] = clip
            if clip.vfr:
                notes.append(f"{clip.id} {p.name}: VFR ({clip.vfr_detail})")
        self.clips = dict(sorted(current.items(), key=lambda kv: int(kv[0][1:])))
        # stills: listed only (resolution, aspect ratio) – never transcribed, not imported into Resolve yet
        st_by_fp = {s.fingerprint: s for s in self.stills.values()}
        next_s = max([int(k[1:]) for k in self.stills] or [0]) + 1
        stills: dict[str, Still] = {}
        for p in wanted(media.find_images(folder, scan, notes)):
            fp = fingerprint(p)
            old = st_by_fp.get(fp)
            try:
                st = old.model_copy(update={"path": str(p)}) if old else Still(id=f"i{next_s:02d}", path=str(p), fingerprint=fp,
                                                                               **media.image_metadata(p))
            except media.MediaError as e:
                notes.append(f"{p.name}: übersprungen ({e})")
                continue
            if not old:
                next_s += 1
            stills[st.id] = st
        self.stills = dict(sorted(stills.items(), key=lambda kv: int(kv[0][1:])))
        if structured and not self.script_path:
            found = projects.script_files(folder)
            if len(found) == 1:
                self.folder = folder
                self.load_script(str(found[0]))
                notes.append(f"Skript geladen: {found[0].name}")
            elif found:
                notes.append(f"Mehrere Skripte im Ordner, welches gilt? {', '.join(f.name for f in found)}")
        resolve_info = None
        if import_to_resolve:
            if bridge is None:
                raise RuntimeError("no Resolve bridge")
            from .resolve_bridge import tool_bin
            props = bridge.import_clips([Path(c.path) for c in self.clips.values()], tool_bin(self.cfg.resolve_bin_prefix + folder.name))
            for c in self.clips.values():
                rp = props.get(c.path, {})
                c.resolve_fps = rp.get("fps")
                c.resolve_frames = rp.get("frames")
                if c.resolve_fps and abs(c.resolve_fps - c.fps) > 0.01:
                    notes.append(f"{c.id}: Resolve-FPS {c.resolve_fps} ≠ ffprobe {c.fps:.3f} → Frame-Raster folgt Resolve")
            resolve_info = {"bin": tool_bin(self.cfg.resolve_bin_prefix + folder.name),
                            "imported": sum(1 for v in props.values() if v.get("imported"))}
        self._save()
        return {"folder": str(folder), "clips": list(self.clips.values()), "stills": list(self.stills.values()),
                "notes": notes, "resolve": resolve_info}

    def clip(self, clip_id: str) -> Clip:
        cid = clip_id.strip().lower()
        if cid.isdigit():
            cid = f"c{int(cid):02d}"
        if cid not in self.clips:
            raise KeyError(f"unknown clip {clip_id!r}; known: {', '.join(self.clips) or '(none – run ingest_folder)'}")
        return self.clips[cid]

    # ---------- audio / silence ----------
    def audio(self, clip: Clip) -> Path:
        return media.extract_audio(Path(clip.path), self.cache.media_dir(clip.fingerprint) / "audio16k.wav")

    def acoustic(self, clip: Clip) -> Acoustic:
        params = AcousticParams(delta_db=self.cfg.acoustic_delta_db)
        f = self.cache.media_dir(clip.fingerprint) / "acoustic.npz"
        ac = Acoustic.load(f, params)
        if ac is None:
            ac = analyze_wav(self.audio(clip), params)
            ac.save(f)
        return ac

    # ---------- transcription ----------
    def _vocab_cfg(self):
        """Settings for NEW transcriptions: the project glossary as custom vocabulary (names only)."""
        import dataclasses

        from . import glossary as gl
        names = gl.vocabulary(self.glossary())
        if not names:
            return self.cfg
        return dataclasses.replace(self.cfg, gladia_custom_vocabulary=list(self.cfg.gladia_custom_vocabulary) + names)

    def _tokens_file(self, clip: Clip, provider_name: str, language: str, new: bool = False) -> Path:
        """Which transcript belongs to the clip: the one it was transcribed with (a clip keeps its word IDs when the glossary
        grows; cutlists depend on them), else the plain settings, else – for a new transcription – with the vocabulary."""
        d = self.cache.media_dir(clip.fingerprint)
        plain = d / f"tokens.{provider_name}.{language}.{option_fingerprint(provider_name, self.cfg)}.json"
        with_vocab = d / f"tokens.{provider_name}.{language}.{option_fingerprint(provider_name, self._vocab_cfg())}.json"
        if new:
            return with_vocab
        base, _, pinned = self.variants.get(clip.id, "").partition("|")
        if pinned and base == plain.name and (d / pinned).exists():  # other model or language: the pin does not count
            return d / pinned
        return plain if plain.exists() else with_vocab

    def cached_transcript(self, clip: Clip, provider_name: str = "gladia", language: str | None = None) -> RawTranscript | None:
        """Transcript for the *current* provider settings – never just the newest file."""
        f = self._tokens_file(clip, provider_name, language or self.cfg.language)
        return RawTranscript(**Cache.read_json(f)) if f.exists() else None

    def other_variants(self, clip: Clip) -> list[str]:
        return sorted(p.name for p in self.cache.media_dir(clip.fingerprint).glob("tokens.*.json"))

    def transcription_estimate(self, clip_ids: list[str] | str = "all", provider: str = "gladia",
                               language: str | None = None, force: bool = False) -> dict:
        """Audio to transcribe (cached clips are free), cost at the configured price, rough duration: per clip 6 s
        overhead + 0.018 s per audio second (upload of the 16-kHz WAV + Gladia processing; measured in Phase 8 on 30
        clips: 17:40 → 27.8 s, 10–60 s clips → 5–12 s), 3 jobs in parallel."""
        language = language or self.cfg.language
        ids = self.transcribe_ids() if clip_ids in ("all", ["all"]) else [self.clip(c).id for c in
                                                                      ([clip_ids] if isinstance(clip_ids, str) else clip_ids)]
        rows = []
        for cid in ids:
            clip = self.clips[cid]
            cached = self._tokens_file(clip, provider, language).exists() and not force
            rows.append((cid, clip.duration_s, cached))
        new_s = sum(d for _, d, c in rows if not c)
        per = [d for _, d, c in rows if not c]
        return {"clips": rows, "new_s": new_s, "cached_s": sum(d for _, d, c in rows if c),
                "cost_usd": round(new_s / 3600 * self.cfg.gladia_price_usd_per_hour, 2), "eta_s": round(eta_seconds(per)),
                "price": self.cfg.gladia_price_usd_per_hour, "needs_confirm": new_s > self.cfg.transcribe_confirm_over_min * 60}

    def transcribe(self, clip_ids: list[str] | str = "all", provider: str = "gladia", language: str | None = None,
                   force: bool = False, max_parallel: int = 3, progress=None) -> list[dict]:
        language = language or self.cfg.language
        ids = self.transcribe_ids() if clip_ids in ("all", ["all"]) else [self.clip(c).id for c in
                                                                      ([clip_ids] if isinstance(clip_ids, str) else clip_ids)]
        prov = get_provider(provider, self._vocab_cfg())  # raises early (e.g. missing API key) before any work

        def one(cid: str) -> dict:
            clip = self.clips[cid]
            out = self._tokens_file(clip, prov.name, language)
            if out.exists() and not force:
                raw = RawTranscript(**Cache.read_json(out))
                return {"clip": cid, "cached": True, "raw": raw}
            out = self._tokens_file(clip, prov.name, language, new=True)
            t0 = time.time()
            wav = self.audio(clip)
            raw_path = out.with_name(out.name.replace("tokens.", "raw."))
            raw = prov.transcribe(wav, language, raw_out=raw_path)
            Cache.write_json(out, raw.model_dump())
            plain = f"tokens.{prov.name}.{language}.{option_fingerprint(prov.name, self.cfg)}.json"
            self.variants[cid] = f"{plain}|{out.name}"
            return {"clip": cid, "cached": False, "raw": raw, "wall_s": round(time.time() - t0, 1)}

        results = []
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=max(1, max_parallel)) as ex:
            futs = {ex.submit(one, cid): cid for cid in ids}
            for done, fut in enumerate(as_completed(futs), 1):
                cid = futs[fut]
                try:
                    r = fut.result()
                    if progress:
                        progress(done, len(ids), f"{cid} fertig ({'Cache' if r['cached'] else str(r.get('wall_s')) + ' s'})")
                    at = self.analyzed(self.clips[cid], r["raw"])
                    r["stats"] = at.stats
                    r["audio_s"] = r["raw"].audio_duration_s
                    r["billing_s"] = r["raw"].billing_s
                    del r["raw"]
                    results.append(r)
                except Exception as e:  # report per clip, keep going
                    results.append({"clip": cid, "error": f"{type(e).__name__}: {e}"})
        if self.folder:
            self._save()
        return results

    # ---------- analysis ----------
    def analyzed(self, clip: Clip, raw: RawTranscript | None = None) -> AnalyzedTranscript:
        raw = raw or self.cached_transcript(clip)
        if raw is None:
            other = self.other_variants(clip)
            raise LookupError(f"{clip.id}: kein Transkript für die aktuellen Einstellungen (Modell {self.cfg.gladia_model}, "
                              f"Sprache {self.cfg.language}) – transcribe aufrufen"
                              + (f"; vorhandene andere Varianten: {', '.join(other)}" if other else ""))
        return analyze(clip.id, raw, self.cfg, acoustic=self.acoustic(clip), clip_duration_s=clip.duration_s)

    # ---------- phase 8: recording aids ----------
    def retake_markers(self, clip: Clip, at: AnalyzedTranscript, segs: list[Segment]) -> list[dict]:
        from . import markers
        times = []
        if self.cfg.clap_markers:
            ac = self.acoustic(clip)
            spans = [(e.start_s, e.end_s) for e in at.entries if e.id[0] == "w"]
            times = markers.claps(ac.env_db, ac.voicing, spans)
        return markers.mark(segs, self.cfg.retake_words, times)

    # ---------- phase 8: A-roll / B-roll ----------
    def clip_role(self, clip: Clip) -> tuple[str, str]:
        """("aroll" | "broll" | "?", reason). B-roll = no audio, no words, or mean confidence below broll_max_confidence:
        Gladia invents a few words on ambience (measured 0.04–0.14), real speech scores ≥ 0.35 even when noisy."""
        if clip.id in self.roles:
            return self.roles[clip.id], "vom Nutzer festgelegt"
        hint = self.folder_hint(clip)
        if hint in ("aroll", "broll"):
            return hint, f"Ordner {'A-Roll' if hint == 'aroll' else 'B-Roll'}"
        if not clip.audio_channels:
            return "broll", "ohne Tonspur"
        raw = self.cached_transcript(clip)
        if raw is None:
            return "?", "noch nicht transkribiert"
        words = [t for t in raw.tokens if t.kind == "word"]
        if not words:
            return "broll", "keine Sprache erkannt"
        conf = sum(t.confidence or 0.0 for t in words) / len(words)
        if conf < self.cfg.broll_max_confidence:
            return "broll", f"{len(words)} Wörter mit Ø Konfidenz {conf:.2f} (< {self.cfg.broll_max_confidence:g}) → keine echte Sprache"
        return "aroll", f"{len(words)} Wörter, Ø Konfidenz {conf:.2f}"

    def folder_hint(self, clip: Clip) -> str | None:
        from .projects import role_of_file
        return role_of_file(clip.path, self.folder) if self.folder else None

    def role_notes(self) -> list[str]:
        """Where a folder name and the content disagree. Measured locally, so it costs nothing."""
        out = []
        for c in self.clips.values():
            hint = self.folder_hint(c)
            if c.id in self.roles or hint not in ("aroll", "broll"):
                continue
            if hint == "aroll" and not c.audio_channels:
                out.append(f"{c.id} liegt in A-Roll, hat aber keinen Ton")
            elif hint == "broll" and c.audio_channels:
                try:
                    voiced = float((self.acoustic(c).voicing > 0.6).mean())
                except Exception:
                    continue
                if voiced > 0.3:
                    out.append(f"{c.id} liegt in B-Roll, klingt aber nach Sprache ({voiced:.0%}): set_clip_role(\"{c.id}\", \"aroll\"), falls es A-Roll ist")
        return out

    def transcribe_ids(self) -> list[str]:
        """"all" without what the folder already calls B-roll: nobody pays for transcribing ambience."""
        return [cid for cid, c in self.clips.items() if self.folder_hint(c) != "broll" or self.roles.get(cid) == "aroll"]

    def broll_ids(self) -> list[str]:
        return [cid for cid, c in self.clips.items() if self.clip_role(c)[0] == "broll"]

    def set_clip_role(self, clip_ids: list[str] | str, role: str) -> str:
        if role not in ("aroll", "broll", "auto"):
            raise ValueError("role: aroll | broll | auto")
        ids = [clip_ids] if isinstance(clip_ids, str) else clip_ids
        for cid in ids:
            c = self.clip(cid)
            if role == "auto":
                self.roles.pop(c.id, None)
            else:
                self.roles[c.id] = role
        if self.folder:
            self._save()
        return "; ".join(f"{self.clip(c).id}: {self.clip_role(self.clip(c))[0]}" for c in ids)

    def broll_text(self) -> list[str]:
        ids = self.broll_ids()
        if not ids:
            return []
        lines = ["B-Roll-Clips (ohne Sprache, nicht im Segment-Text; als Overlay mit media=cNN + from_frame):",
                 "id | Datei | Dauer | fps | Auflösung | Grund"]
        for cid in ids:
            c = self.clips[cid]
            fps = c.resolve_fps or c.fps
            lines.append(f"{cid} | {c.name} | {ts(c.duration_s)} | {fps:g} | {c.width}x{c.height} | {self.clip_role(c)[1]}")
        lines.append("Kontaktabzug mit Frame-IDs: get_frames(\"broll\") (alle) oder get_frames(\"c05\", mode=\"scenes\").")
        return lines

    # ---------- summaries ----------
    def stills_text(self) -> list[str]:
        if not self.stills:
            return []
        lines = ["Standbilder (nicht transkribiert):", "id  | Datei | Auflösung | Seitenverhältnis | Ausrichtung"]
        for st in self.stills.values():
            w, h = st.display_size()
            orient = "Hochformat" if h > w else "Querformat" if w > h else "quadratisch"
            lines.append(f"{st.id} | {st.name} | {w}x{h}" + (f" (rot{st.rotation})" if st.rotation else "")
                         + f" | {st.aspect()} | {orient}")
        return lines

    def list_clips_text(self) -> str:
        if not self.clips and not self.stills:
            return "Keine Clips. Zuerst ingest_folder(path) aufrufen."
        lines = [f"Ordner: {self.folder}", "id  | Datei | Dauer | fps | Auflösung | Audio | TC | Transkript | Art"]
        for c in self.clips.values():
            raw = self.cached_transcript(c)
            tr = f"{raw.provider}/{raw.language} {sum(1 for t in raw.tokens)} Tok." if raw else "–"
            res = f"{c.width}x{c.height}" + (f" rot{c.rotation}" if c.rotation else "")
            fps = f"{c.fps:.3f}".rstrip("0").rstrip(".") + (" VFR" if c.vfr else "")
            if c.resolve_fps and abs(c.resolve_fps - c.fps) > 0.01:
                fps += f" (Resolve {c.resolve_fps:g})"
            role, why = self.clip_role(c)
            art = {"aroll": "A-Roll", "broll": f"B-Roll ({why})", "?": "?"}[role]
            lines.append(f"{c.id} | {c.name} | {ts(c.duration_s)} | {fps} | {res} | {c.audio_channels}ch | "
                         f"{c.start_tc or '–'} | {tr} | {art}")
        return "\n".join(lines + self.stills_text())

    # ---------- phase 2: script, segments, context, cutlist ----------
    def load_script(self, path: str | None) -> list[ScriptLine] | None:
        if not path:
            self.script_path, self.script = None, None
        else:
            from .guard import check_read
            p = check_read(path, [self.folder, self.export_dir() if self.folder or self.cfg.export_folder else None],
                           "Das Skript")
            self.script = load_script(str(p))
            self.script_path = str(p)
        if self.folder:
            self._save()
        return self.script

    def segments(self, clip: Clip, at: AnalyzedTranscript | None = None) -> list[Segment]:
        at = at or self.analyzed(clip)
        segs = segment(at, self.cfg, clip.duration_s)
        self.retake_markers(clip, at, segs)
        if self.script:
            for s in segs:
                s.script = match(s.plain, self.script)
        return segs

    def edit_context(self, clip_ids: list[str] | str = "all", include_guide: bool = True, page: int | None = None,
                     page_size: int = 40, overview: bool = False, pass_name: str | None = "rough") -> str:
        everything = clip_ids in ("all", ["all"])
        ids = list(self.clips) if everything else [self.clip(c).id for c in ([clip_ids] if isinstance(clip_ids, str) else clip_ids)]
        if everything:
            broll = set(self.broll_ids())
            ids = [c for c in ids if c not in broll]
        blocks = []
        for cid in ids:
            clip = self.clips[cid]
            segs = self.segments(clip)
            edges, groups = retakes.find(segs, window_s=self.cfg.retake_window_s)
            blocks.append((clip, segs, edges, groups))
        from .guides import guide as _guide
        from .projects import brief_text
        guide = _guide(self.cfg.guides_dir, pass_name) if include_guide else None
        brief = brief_text(self.folder) if self.folder else None
        if brief:  # read before the rough cut: selection, hook and length follow it
            guide = f"## Brief des Nutzers (geht vor, Auswahl, Hook und Länge danach ausrichten)\n{brief}\n\n{guide or ''}"
        if overview or page is not None:
            pages = ctx.paginate(blocks, max(5, page_size))
            if overview:
                return ctx.render_overview(blocks, self.script, self.broll_text() + self.stills_text(), str(self.folder), guide, pages)
            return ctx.render_page(blocks, pages, page, self.script)
        return ctx.render(blocks, self.script, self.broll_text() + self.stills_text(), str(self.folder), guide)

    def plan(self, cl: Cutlist) -> tuple[Plan, dict[str, AnalyzedTranscript], dict[str, list[Segment]]]:
        need = {it.clip.strip().lower() for it in cl.items if it.clip.strip().lower() in self.clips}
        need |= {r.segment.split(":")[0] for r in cl.rejected if r.segment.split(":")[0] in self.clips}
        analyzed, segs = {}, {}
        for cid in need:
            try:
                analyzed[cid] = self.analyzed(self.clips[cid])
                segs[cid] = self.segments(self.clips[cid], analyzed[cid])
            except LookupError:
                pass
        motions = {cid: self.motion(self.clips[cid]) for cid in analyzed} if cl.options.motion_aware_cuts else {}
        faces = {}
        if cl.punch_in is not None or any(it.zoom for it in cl.items) or cl.graphics or cl.reframe:
            for cid in analyzed:
                pa = self.person(self.clips[cid])
                faces[cid] = (pa["boxes"], tuple(int(x) for x in pa["size"]))
        if self.corrections:  # persistent corrections (set_word_text) apply unless the cutlist overrides them
            from .cutlist import Correction
            given = {c.word for c in cl.corrections}
            cl = cl.model_copy(update={"corrections": [Correction(word=k, text=v) for k, v in self.corrections.items()
                                                       if k not in given] + list(cl.corrections)})
        tok, prof = None, self.profile(cl.format, cl.style)
        if cl.graphics or cl.sfx:
            from .mg import tokens as _tokens
            tok = _tokens.load(cl.brand)
        acoustics = {cid: self.acoustic(self.clips[cid]) for cid in analyzed}
        return (build_plan(cl, self.clips, analyzed, segs, motions, set(self.stills), faces, prof, tok,
                           sandbox=self.cfg.motion_sandbox, acoustics=acoustics, sfx_opts=self.sfx_options(cl, tok, analyzed),
                           reframe_opts={"speakers": lambda ps: self.piece_speakers(ps, analyzed), "focus": self.busiest_x} if cl.reframe else None),
                analyzed, segs)

    def busiest_x(self, cid: str, start: int, frames: int) -> float:
        """Where the crop of a B-roll clip belongs: three frames of the span, 320 px wide. Cached for the session."""
        import subprocess

        import numpy as np

        from .media import _bin
        from .reframe import busiest_x
        key = (cid, start, frames)
        memo = self.__dict__.setdefault("_busiest", {})
        if key not in memo:
            c = self.clips[cid]
            fps = c.resolve_fps or c.fps
            h = max(2, round(320 * c.height / c.width / 2) * 2)
            fr = []
            for k in (0.2, 0.5, 0.8):
                raw = platforms.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-ss", f"{(start + frames * k) / fps:.3f}", "-i", c.path, "-frames:v", "1", "-vf", f"scale=320:{h}",
                                      "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
                if len(raw) == 320 * h:
                    fr.append(np.frombuffer(raw, np.uint8).reshape(h, 320))
            memo[key] = busiest_x(fr) if fr else 0.5
        return memo[key]

    def sfx_library(self) -> list[dict]:
        from . import sfx
        return sfx.load(self.cfg.sfx_folder, self.cache.root / "sfx")

    def sfx_options(self, cl: Cutlist, tok: dict | None, analyzed: dict) -> dict | None:
        """Level reference: the target of the audio pass, before that the measured main clip."""
        if not cl.sfx:
            return None
        if cl.audio is not None:
            voice, source = cl.audio.target_lufs, "Ziel des Polish"
        else:
            clip = self.clips[self.master_clip(set(analyzed))] if analyzed else None
            voice, source = (self.audio_report(clip).get("lufs"), f"gemessen an {clip.id}") if clip else (None, "")
            if voice is None:
                voice, source = -23.0, "nicht messbar, angenommen"
        return {"library": self.sfx_library(), "mode": cl.sfx_mode or self.cfg.sfx_mode, "style": ((tok or {}).get("style") or {}).get("id"),
                "voice_lufs": voice, "voice_source": source}

    def sfx_cues(self, plan: Plan) -> list[dict]:
        from . import sfx
        paths = sfx.stage_files(plan.sfx, self.export_dir())
        credits = sorted({s.credit for s in plan.sfx if s.credit})
        if credits:  # CC-BY asks for attribution: ready to paste into the video description
            (self.export_dir() / "sfx_credits.txt").write_text("Sound-Effekte:\n" + "\n".join(credits) + "\n", encoding="utf-8")
        return [{**s.model_dump(), "file": paths[s.index]} for s in plan.sfx]

    def prepare(self, cl: Cutlist) -> tuple[Cutlist, list[str]]:
        """Pass rules + profile defaults → the effective cutlist (see passes.resolve)."""
        from .passes import resolve
        base = None
        if cl.base_cutlist is not None and cl.pass_ not in (None, "rough"):
            if isinstance(cl.base_cutlist, dict):
                base = Cutlist(**cl.base_cutlist)
            else:
                base = self.built_cutlist(cl.base_cutlist)
                if base is None:
                    known = ", ".join(sorted(self.builds)) or "keine"
                    raise LookupError(f"base_cutlist „{cl.base_cutlist}“ unbekannt – gebaute Timelines: {known}")
        fmt = cl.format or (base.format if base else None) or self.effective_format()[0]
        prof = self.cfg.profile(fmt, cl.style or (base.style if base else None))
        eff, notes = resolve(cl, base, prof)
        if eff.format is None:
            eff.format = fmt
        return eff, notes

    def _hook_face_lines(self, plan: Plan, prof) -> list[str]:
        """01_rough_cut: face at least 1 s within the first hook_s seconds; first frame not mid-movement."""
        try:
            fps = self.clips[plan.pieces[0].clip].resolve_fps or self.clips[plan.pieces[0].clip].fps
            need, rec, seen, total = prof.hook_s * fps, 0, 0, 0
            for pc in plan.pieces:
                boxes = self.person(self.clips[pc.clip])["boxes"]
                for fr in range(pc.start_frame, pc.end_frame):
                    if rec >= need:
                        break
                    total += 1
                    seen += 1 if fr < len(boxes) and boxes[fr][0] >= 0 else 0
                    rec += 1
                if rec >= need:
                    break
        except Exception:  # no frames/analysis available → no hint
            return []
        out = [f"  Hook: Gesicht in {seen / fps:.1f} s der ersten {total / fps:.1f} s "
               + ("✓" if seen >= fps else "⚠ (Leitfaden: mindestens 1 s in den ersten 3 s)")]
        m = plan.pieces[0].start_motion
        if m is not None and m > 6:
            out.append(f"  ⚠ Erster Frame mitten in einer Bewegung (Bew. {m:g}× Median) – Hereinkommen/Geste? "
                       "Mit get_frames(..., pad_s=1) prüfen; ohne ruhigen Frame vor dem ersten Wort: Grenzfall melden")
        return out

    def validate_text(self, cl: Cutlist) -> str:
        from .profiles import profile_text
        eff, notes = self.prepare(cl)
        plan, analyzed, segs = self.plan(eff)
        prof = self.cfg.profile(eff.format, eff.style)
        head = [f"Durchgang: {eff.pass_ or '– (ohne Durchgangs-Regeln)'} · Timeline „{eff.timeline_name}“ · Format {prof.format} · "
                f"{profile_text(prof)}"]
        head += [f"Hinweis {n}" for n in notes]
        extra = []
        if plan.ok and eff.pass_ == "rough":  # what the fine cut will make of it (profile pauses, fillers)
            from .passes import option_defaults
            fine = eff.model_copy(update={"options": CutOptions(**option_defaults(prof, "fine"))})
            fplan, _, _ = self.plan(fine)
            if fplan.ok:
                extra.append(f"Laufzeit-Schätzung nach dem Fine Cut (Profil-Pausen, Füller raus): {ts(fplan.total_seconds(self.clips))}")
        if plan.ok:
            from .qc import plan_checks
            extra += plan_checks(eff, plan, self.clips, prof, analyzed)
            extra += self._hook_face_lines(plan, prof)
        if plan.ok:
            g_err, g_warn = self.glossary_check(eff, plan)
            extra += [f"FEHLER {e}" for e in g_err] + [f"Hinweis {w}" for w in g_warn]
        if plan.ok and eff.revision_of and self.built_cutlist(eff.revision_of) is not None:
            from .revise import diff
            old = self.built_cutlist(eff.revision_of)
            oplan, _, _ = self.plan(old)
            extra = diff(old, eff, oplan.total_seconds(self.clips), plan.total_seconds(self.clips)) + extra
        return "\n".join(head + [plan_text(eff, plan, self.clips)] + extra)

    def alternates(self, cl: Cutlist, plan: Plan, analyzed: dict, segs: dict) -> list[tuple[Piece, str]]:
        """All segments not used in the cut, in recording order, with the reason from `rejected`."""
        reasons = {r.segment: r.reason for r in cl.rejected}
        out = []
        for cid, ss in segs.items():
            used = [(a, b) for c, a, b in plan.item_spans if c == cid]
            clip = self.clips[cid]
            fps = clip.resolve_fps or clip.fps
            for s in ss:
                a, b = s.word_range()
                if any(a <= ub and ua <= b for ua, ub in used):
                    continue
                mo = self.motion(clip) if cl.options.motion_aware_cuts else None
                for p in plan_item(0, clip, analyzed[cid], a, b, cl.options, fps, clip.resolve_frames, mo):
                    out.append((p, f"{s.ref}: " + (reasons.get(s.ref) or "nicht verwendet")))
        return out

    def master_clip(self, clip_ids: set[str]) -> str:
        """Main material = clip with the most speech (sum of word durations); ties → lower id."""
        def speech(cid: str) -> float:
            raw = self.cached_transcript(self.clips[cid])
            return sum(t.end_s - t.start_s for t in raw.tokens) if raw else 0.0
        return max(sorted(clip_ids), key=speech)

    # ---------- phase 3: frames ----------
    def frame_cache(self, clip: Clip):
        from .frames import FrameCache
        return FrameCache(self.cache.media_dir(clip.fingerprint), clip)

    def motion(self, clip: Clip):
        """Per-frame motion for cut decisions (person region, no-face frames restless; see frames.cut_motion)."""
        from .frames import cut_motion, person_analysis
        return cut_motion(person_analysis(self.cache.media_dir(clip.fingerprint), clip))

    def person(self, clip: Clip) -> dict:
        from .frames import person_analysis
        return person_analysis(self.cache.media_dir(clip.fingerprint), clip)

    def _target(self, target: str):
        """→ ("stills", [Still]) | ("clip", clip, [segments], (t0, t1))"""
        t = target.strip()
        if t.lower() == "stills" or re.fullmatch(r"i\d+(\s*,\s*i\d+)*", t, re.I):
            ids = list(self.stills) if t.lower() == "stills" else [x.strip().lower() for x in t.split(",")]
            missing = [i for i in ids if i not in self.stills]
            if missing:
                raise KeyError(f"unbekannte Standbilder {missing}; bekannt: {', '.join(self.stills) or '–'}")
            return ("stills", [self.stills[i] for i in ids])
        m = re.fullmatch(r"(c\d+)(?::(.+))?", t, re.I)
        if not m:
            raise ValueError(f"Ziel {target!r} nicht erkannt (c01, c01:s003-s007, c01:w0010-w0050, stills, i01,i02)")
        clip = self.clip(m.group(1))
        segs = self.segments(clip)
        rest = (m.group(2) or "").strip()
        if not rest:
            return ("clip", clip, segs, (0.0, clip.duration_s))
        sm = re.fullmatch(r"s0*(\d+)(?:\s*-\s*s?0*(\d+))?", rest, re.I)
        if sm:
            a, b = int(sm.group(1)), int(sm.group(2) or sm.group(1))
            sel = [s for s in segs if a <= int(s.id[1:]) <= b]
            if not sel:
                raise KeyError(f"keine Segmente {rest} in {clip.id}")
            return ("clip", clip, sel, (sel[0].start_s, sel[-1].end_s))
        if "," in rest and all(re.fullmatch(r"s\d+", x.strip()) for x in rest.split(",")):
            want = {x.strip() for x in rest.split(",")}
            sel = [s for s in segs if s.id in want]
            return ("clip", clip, sel, (sel[0].start_s, sel[-1].end_s))
        wm = re.fullmatch(r"w0*(\d+)\s*-\s*w?0*(\d+)", rest, re.I)
        if wm:
            a, b = int(wm.group(1)), int(wm.group(2))
            words = [e for e in self.analyzed(clip).entries if e.id[0] == "w" and a <= int(e.id[1:]) <= b]
            if not words:
                raise KeyError(f"keine Wörter {rest} in {clip.id}")
            sel = [s for s in segs if s.word_range()[0] <= b and a <= s.word_range()[1]]
            return ("clip", clip, sel, (words[0].start_s, words[-1].end_s))
        raise ValueError(f"Bereich {rest!r} nicht erkannt (s003, s003-s007, s003,s005, w0010-w0050)")

    def get_frames(self, target: str, mode: str = "segment_strip", interval_s: float = 2.0, max_images: int = 1,
                   page: int = 1, segs_per_row: int = 2, pad_s: float = 0.0) -> tuple[str, list[bytes]]:
        from . import frames as fr
        if target.strip().lower() in ("broll", "clips"):
            return self.clip_sheets(target.strip().lower(), max_images=max_images, page=page)
        kind = self._target(target)
        sheets: list = []
        lines: list[str] = []
        if kind[0] == "stills" or mode == "stills":
            stills = kind[1] if kind[0] == "stills" else list(self.stills.values())
            if not stills:
                return "Keine Standbilder im Ordner.", []
            tiles = []
            for st in stills:
                w, h = st.display_size()
                orient = "Hoch" if h > w else "Quer" if w > h else "quadr."
                tiles.append((fr.still_tile(st), f"{st.id} {st.aspect()} {orient}", f"{w}x{h}"))
                lines.append(f"{st.id} {st.name} {w}x{h} {st.aspect()} {orient}")
            per = 9
            chunks = [tiles[i:i + per] for i in range(0, len(tiles), per)]
            sheets = [fr.sheet(c, 3, 1.0, header=f"Standbilder ({len(stills)})") for c in chunks]
        else:
            _, clip, segs, (t0, t1) = kind
            fc = self.frame_cache(clip)
            fps = fc.fps
            aspect = fc.tw / fc.th
            last = (clip.resolve_frames or clip.nb_frames or int(clip.duration_s * fps)) - 1
            if mode == "segment_strip":
                rows = []
                for s in segs:
                    a, b = math.floor(s.start_s * fps), min(last, math.ceil(s.end_s * fps) - 1)
                    rows.append((s, [a, (a + b) // 2, b]))
                per_sheet = 4 * segs_per_row if segs_per_row > 1 else 5  # 4 rows (or 5 attempts in comparison view)
                chunks = [rows[i:i + per_sheet] for i in range(0, len(rows), per_sheet)]
                for ch in chunks:
                    paths = fc.get([i for _, ids in ch for i in ids])
                    tiles = []
                    for s, ids in ch:
                        for k, i in enumerate(ids):
                            tiles.append((paths[max(0, min(last, i))], fr.frame_id(clip.id, i),
                                          f"{s.id} {'AME'[k]} {fr.label_time(i, fps)}"))
                    sheets.append(fr.sheet(tiles, 3 * segs_per_row, aspect, header=f"{clip.id} Segment-Streifen (A/M/E)"))
                lines += [f"{s.ref} {s.from_word}–{s.to_word}: " + " ".join(fr.frame_id(clip.id, i) for i in ids)
                          for s, ids in rows]
            elif mode in ("interval", "scenes"):
                t0, t1 = max(0.0, t0 - pad_s), min(clip.duration_s, t1 + pad_s)
                if mode == "interval":
                    step = max(1, round(interval_s * fps))
                    ids = list(range(math.floor(t0 * fps), min(last, math.ceil(t1 * fps)) + 1, step))
                else:
                    ids = [i for i in fr.scene_frames(clip) if t0 * fps <= i <= t1 * fps + 1]
                chunks = [ids[i:i + 16] for i in range(0, len(ids), 16)]
                for ch in chunks:
                    paths = fc.get(ch)
                    tiles = [(paths[i], fr.frame_id(clip.id, i), fr.label_time(i, fps)) for i in ch]
                    sheets.append(fr.sheet(tiles, 4, aspect, header=f"{clip.id} {mode} {interval_s if mode == 'interval' else ''}"))
                lines.append(" ".join(f"{fr.frame_id(clip.id, i)}@{fr.label_time(i, fps)}" for i in ids))
            else:
                raise ValueError("mode: segment_strip | interval | scenes | stills")
        n = len(sheets)
        page = max(1, page)
        sel = sheets[(page - 1) * max_images: page * max_images]
        jpgs = [fr.to_jpeg(s) for s in sel]
        tok = sum(fr.image_tokens(*s.size) for s in sel)
        head = (f"{target} · {mode} · Abzug {(page - 1) * max_images + 1}–{(page - 1) * max_images + len(sel)} von {n}"
                f" · ≈{tok} Bild-Token" + (f" · weitere: page={page + 1}" if page * max_images < n else ""))
        return "\n".join([head] + lines), jpgs

    def clip_sheets(self, which: str, max_images: int = 1, page: int = 1) -> tuple[str, list[bytes]]:
        """which="broll": per B-roll clip its scene frames (≥ start/middle/end) with frame IDs – to pick from_frame.
        which="clips": one middle frame per clip (all clips) – to group scenes and propose an order (commercials)."""
        from . import frames as fr
        ids = self.broll_ids() if which == "broll" else list(self.clips)
        if not ids:
            return ("Keine B-Roll-Clips erkannt (set_clip_role legt Clips von Hand fest)." if which == "broll"
                    else "Keine Clips."), []
        tiles, lines = [], []
        for cid in ids:
            clip = self.clips[cid]
            fc = self.frame_cache(clip)
            fps = fc.fps
            last = (clip.resolve_frames or clip.nb_frames or int(clip.duration_s * fps)) - 1
            if which == "clips":
                pick = [last // 2]
            else:
                sc = [i for i in fr.scene_frames(clip) if i <= last]
                pick = sorted(set(sc) | {0, last // 2, max(0, last - 1)})
                if len(pick) > 8:  # keep it readable: evenly spaced subset
                    pick = [pick[round(k * (len(pick) - 1) / 7)] for k in range(8)]
            paths = fc.get(pick)
            role, _ = self.clip_role(clip)
            for i in pick:
                sub = f"{ts(clip.duration_s)} {'B' if role == 'broll' else 'A'}" if which == "clips" else fr.label_time(i, fps)
                tiles.append((paths[i], fr.frame_id(cid, i), sub))
            if which == "clips":
                raw = self.cached_transcript(clip)
                said = " ".join(t.text for t in raw.tokens[:14]) if raw and role != "broll" else ""
                lines.append(f"{cid} {clip.name} {ts(clip.duration_s)} {'B-Roll' if role == 'broll' else 'A-Roll'}"
                             + (f" – „{said}…“" if said else ""))
            else:
                lines.append(f"{cid} ({ts(clip.duration_s)}, {fps:g} fps, Frames 0–{last}): "
                             + " ".join(f"{fr.frame_id(cid, i)}@{fr.label_time(i, fps)}" for i in pick))
        per = 16 if which == "clips" else 24
        chunks = [tiles[i:i + per] for i in range(0, len(tiles), per)]
        sheets = [fr.sheet(c, 4, 16 / 9, header="Alle Clips (Mittelbild)" if which == "clips" else "B-Roll-Szenen")
                  for c in chunks]
        page = max(1, page)
        sel = sheets[(page - 1) * max_images: page * max_images]
        head = (f"{which} · Abzug {(page - 1) * max_images + 1}–{(page - 1) * max_images + len(sel)} von {len(sheets)} · ≈"
                f"{sum(fr.image_tokens(*x.size) for x in sel)} Bild-Token"
                + (f" · weitere: page={page + 1}" if page * max_images < len(sheets) else ""))
        return "\n".join([head] + lines), [fr.to_jpeg(x) for x in sel]

    def preview_cuts(self, cl: Cutlist, max_images: int = 1, top_n: int = 8, page: int = 1) -> tuple[str, list[bytes]]:
        """Pairs 'last frame before | first frame after' per cut, most conspicuous first (image difference + motion)."""
        import numpy as np
        from PIL import Image as PILImage

        from . import frames as fr
        from .cutlist import cut_list
        plan, _, _ = self.plan(cl)
        if not plan.ok:
            raise ValueError("Cutlist ungültig:\n" + "\n".join(plan.errors))
        cuts = cut_list(plan)
        need: dict[str, list[int]] = {}
        for c in cuts:
            for key in ("f_out", "f_in"):
                if c[key]:
                    cid, i = fr.parse_frame_id(c[key])
                    need.setdefault(cid, []).append(i)
        paths = {}
        for cid, idxs in need.items():
            for i, p in self.frame_cache(self.clips[cid]).get(idxs).items():
                paths[fr.frame_id(cid, i)] = p
        gray = lambda f: np.asarray(PILImage.open(paths[f]).convert("L").resize((48, 85)), dtype=np.float32)
        for c in cuts:
            diff = float(np.mean(np.abs(gray(c["f_out"]) - gray(c["f_in"])))) if c["f_out"] and c["f_in"] else 0.0
            c["diff"] = round(diff, 1)
            c["score"] = diff / 10 + max(c["m_out"] or 0, c["m_in"] or 0)
        ranked = sorted(cuts, key=lambda c: -c["score"])[: max(1, top_n)] if top_n else cuts
        clip0 = self.clips[plan.pieces[0].clip]
        fc = self.frame_cache(clip0)
        aspect = fc.tw / fc.th
        tiles = []
        for c in ranked:
            for key, side, mv in (("f_out", "vor", c["m_out"]), ("f_in", "nach", c["m_in"])):
                f = c[key]
                tiles.append((paths.get(f) if f else None, f or "–", f"{c['id']} {side} B{mv if mv is not None else '–'}"))
        per = 16  # 2 pairs per row x 4 rows
        chunks = [tiles[i:i + per] for i in range(0, len(tiles), per)]
        sheets = [fr.sheet(ch, 4, aspect, header="Schnitte: vor | nach  (B = Bewegung x Median)") for ch in chunks]
        sel = sheets[(page - 1) * max_images: page * max_images]
        jpgs = [fr.to_jpeg(s) for s in sel]
        tok = sum(fr.image_tokens(*s.size) for s in sel)
        lines = [f"preview_cuts „{cl.timeline_name}“: {len(ranked)} von {len(cuts)} Schnitten (auffälligste zuerst) · "
                 f"Abzug {page}/{len(sheets)} · ≈{tok} Bild-Token"]
        lines += [f"{c['id']} {c['label']} {c['f_out'] or '–'}|{c['f_in'] or '–'} Bilddiff {c['diff']} Bew. "
                  f"{c['m_out'] if c['m_out'] is not None else '–'}|{c['m_in'] if c['m_in'] is not None else '–'}"
                  + (f" ({c['shift']})" if c["shift"] else "") for c in ranked]
        return "\n".join(lines), jpgs

    def take_frames(self, group: str, max_images: int = 1, page: int = 1) -> tuple[str, list[bytes]]:
        """Attempts of a retake group (c01:G03, or G03 with a single clip, or c01:s022,s026,s028) one per row."""
        g = group.strip()
        m = re.fullmatch(r"(?:(c\d+):)?G0*(\d+)", g, re.I)
        if m:
            cid = m.group(1) or (next(iter(self.clips)) if len(self.clips) == 1 else None)
            if cid is None:
                raise ValueError("bei mehreren Clips die Gruppe mit Clip angeben, z. B. c02:G03")
            clip = self.clip(cid)
            segs = self.segments(clip)
            _, groups = retakes.find(segs, window_s=self.cfg.retake_window_s)
            gid = f"G{int(m.group(2)):02d}"
            grp = next((x for x in groups if x.id == gid), None)
            if grp is None:
                raise KeyError(f"Gruppe {g} nicht gefunden; vorhanden: {', '.join(clip.id + ':' + x.id for x in groups) or '–'}")
            target = f"{clip.id}:" + ",".join(grp.members)
        else:
            target = g
        text, jpgs = self.get_frames(target, "segment_strip", max_images=max_images, page=page, segs_per_row=1)
        return f"Versuche {group} (eine Zeile pro Versuch: Anfang/Mitte/Ende)\n" + text, jpgs

    # ---------- phase 4: audio ----------
    def audio_report(self, clip: Clip) -> dict:
        from pathlib import Path as _P

        from . import audio as au
        f = self.cache.media_dir(clip.fingerprint) / "audio_report.json"
        data = Cache.read_json(f)
        if data and data.get("v") == 3:
            return data
        loud = au.ebur128(["-i", clip.path])
        ac = self.acoustic(clip)
        spec = au.spectral_profile(au.third_octave_levels(au.read_pcm(_P(clip.path)), ac.regions(0, clip.duration_s)))
        data = {"v": 3, **loud, "noise_floor_db": round(ac.floor_db, 1), "spectrum": spec,
                "channels": au.channel_analysis(clip.path)}
        Cache.write_json(f, data)
        return data

    def channel_plan(self, clip: Clip) -> dict | None:
        """audio_report channels + for two different mics and a diarized transcript: one channel per speaker
        (interview: lavalier on the guest, second mic on the interviewer)."""
        from . import audio as au
        plan = dict(self.audio_report(clip).get("channels") or {})
        if plan.get("class") != "verschieden":
            return plan or None
        raw = self.cached_transcript(clip)
        if raw is None or len({t.speaker for t in raw.tokens if t.speaker is not None}) < 2:
            return plan
        f = self.cache.media_dir(clip.fingerprint) / "speaker_channels.json"
        key = f"{len(raw.tokens)}:{raw.provider_job_id}"
        data = Cache.read_json(f)
        if not data or data.get("key") != key:
            spans: dict[int, list] = {}
            for t in raw.tokens:
                if t.speaker is not None:
                    spans.setdefault(t.speaker, []).append((t.start_s, t.end_s))
            data = {"key": key, **au.speaker_channels(clip.path, spans)}
            Cache.write_json(f, data)
        if data.get("split"):
            by = {int(k): v for k, v in data["by_speaker"].items()}
            plan["by_speaker"] = by
            plan["class"] = "je Sprecher"
            plan["reason"] = (plan.get("reason", "") + " · je Sprecher eigenes Mikro: "
                              + ", ".join(f"S{k + 1} → Kanal {v} ({data['levels'][str(k) if str(k) in data['levels'] else k]} dB)"
                                          for k, v in sorted(by.items())))
        return plan

    def piece_speakers(self, pieces: list, analyzed: dict) -> list[int | None]:
        """Majority speaker per piece (diarization), None without speaker info."""
        out = []
        for pc in pieces:
            by_id = {e.id: e for e in analyzed[pc.clip].entries} if pc.clip in analyzed else {}
            raw = self.cached_transcript(self.clips[pc.clip])
            spk_of = {t.id: t.speaker for t in raw.tokens} if raw else {}
            votes: dict[int, int] = {}
            for wid in pc.word_ids:
                sp = spk_of.get(wid)
                if sp is not None and wid in by_id:
                    votes[sp] = votes.get(sp, 0) + 1
            out.append(max(votes, key=votes.get) if votes else None)
        return out

    def audio_text(self, clip_ids: list[str] | str = "all", target_lufs: float = -14.0) -> str:
        from . import audio as au
        ids = list(self.clips) if clip_ids in ("all", ["all"]) else [self.clip(c).id for c in
                                                                      ([clip_ids] if isinstance(clip_ids, str) else clip_ids)]
        out = ["Audio-Analyse (Quelle; im Resolve-Programm liegt Mono auf L+R → dort ca. +3 LU)",
               "Clip | LUFS | True Peak | LRA | Rauschboden | Rumpeln <80 Hz | Boxy 200–500 Hz | Zischlaute 5–8 kHz (dB ggü. Sprach-Referenz)"]
        recs = []
        for cid in ids:
            m = self.audio_report(self.clips[cid])
            sp = m.get("spectrum") or {}
            out.append(f"{cid} | {m['lufs']} | {m['true_peak']} dBTP | {m['lra']} LU | {m['noise_floor_db']} dBFS | "
                       f"{sp.get('rumble_db', '–'):+} | {sp.get('boxy_db', '–'):+} | {sp.get('sibilance_db', '–'):+}")
            recs += [f"{cid}: {r}" for r in au.recommendations(m, target_lufs)]
            ch = self.channel_plan(self.clips[cid]) or {}
            for c in ch.get("channels", []):
                out.append(f"  {cid} Kanal {c['channel']}: {c['lufs']} LUFS, RMS {c['rms_db']} dB, Sprache {c['speech_db']} dB, "
                           f"Rauschen {c['noise_db']} dB (Abstand {c['snr_db']} dB)")
            if ch.get("class"):
                corr = f", Korrelation {ch['correlation']}" if ch.get("correlation") is not None else ""
                recs.append(f"{cid}: Kanäle {ch['class']}{corr} – {ch['reason']}")
        return "\n".join(out + ["Empfehlungen:"] + recs + [
            "Umsetzung in build_timeline über den Cutlist-Abschnitt \"audio\" (Durchgang polish): Lautheit über Clip-Lautstärke, "
            "Limiter → Multiband Compressor für True Peak ≤ −1 dBTP, geprüft per Render. EQ/Hochpass sind per API nicht parametrierbar."])


    # ---------- phase 6: format ----------
    def detect_format(self, hint: str | None = None):
        from .formats import detect, refine
        if not self.clips:
            raise LookupError("kein Ordner eingelesen (ingest_folder)")
        broll = set(self.broll_ids())
        ids = sorted(c for c in self.clips if c not in broll) or sorted(self.clips)
        speech, texts, speakers = {}, [], {}
        for cid in ids:
            raw = self.cached_transcript(self.clips[cid])
            speech[cid] = sum(t.end_s - t.start_s for t in raw.tokens) if raw else None
            if raw:
                texts.append(" ".join(t.text for t in raw.tokens))
                for t in raw.tokens:
                    if t.speaker is not None:
                        speakers[t.speaker] = speakers.get(t.speaker, 0) + 1
        transcribed = any(v is not None for v in speech.values())
        if transcribed:
            main = max(ids, key=lambda c: speech[c] or 0)
            speech_s = sum(v for v in speech.values() if v)
        else:  # not transcribed yet: longest clip, ~60 % speech
            main = max(ids, key=lambda c: self.clips[c].duration_s)
            speech_s = 0.6 * sum(self.clips[c].duration_s for c in ids)
        raw_s = sum(c.duration_s for c in self.clips.values())
        words = sum(len(ln.text.split()) for ln in self.script) if self.script else None
        base = detect([self.clips[main]], speech_s, raw_s, words, hint)
        if not transcribed:
            return base
        total_w = sum(speakers.values()) or 1
        real_speakers = sum(1 for n in speakers.values() if n / total_w >= 0.05)
        return refine(base, speakers=real_speakers, aroll_clips=len(ids), broll_clips=len(broll),
                      longest_take_speech_s=max(v or 0 for v in speech.values()), aroll_speech_s=speech_s,
                      text=" ".join(texts), hint=hint)

    def effective_format(self) -> tuple[str, str]:
        """(format, source): user choice → the project's brief → fixed config value → detection."""
        from .profiles import FORMATS
        from .projects import brief_format
        if self.format_choice in FORMATS:
            return self.format_choice, "gewählt"
        fmt = brief_format(self.folder) if self.folder else None
        if fmt in FORMATS:
            return fmt, "aus dem Brief"
        if self.cfg.format in FORMATS:
            return self.cfg.format, "Konfiguration"
        if not self.clips:
            return "reel", "Standard"
        d = self.detect_format()
        return d.format, f"erkannt ({d.confidence:.2f}{', unsicher' if d.ask else ''})"

    def effective_content_type(self) -> tuple[str, str]:
        """(content type, source), in the order of the format: user choice → brief → preference → detection. Independent of the format: a reel can be an interview."""
        from .formats import CONTENT_TYPES
        from .projects import brief_content_type
        if self.content_choice in CONTENT_TYPES:
            return self.content_choice, "gewählt"
        ct = brief_content_type(self.folder) if self.folder else None
        if ct:
            return ct, "aus dem Brief"
        if self.cfg.content_type in CONTENT_TYPES:
            return self.cfg.content_type, "Vorliebe"
        if not self.clips:
            return "talking_head", "Standard"
        d = self.detect_format()
        return d.content_type or "talking_head", "erkannt"

    def set_content_type(self, ct: str) -> str:
        from .formats import CONTENT_TYPES, CONTENT_WORDS
        value = CONTENT_WORDS.get(ct, ct)
        if value not in CONTENT_TYPES + ("auto",):
            raise ValueError("content_type: " + " | ".join(CONTENT_TYPES) + " | auto")
        self.content_choice = None if value == "auto" else value
        if self.folder:
            self._save()
        return self.effective_content_type()[0]

    def set_format(self, fmt: str) -> str:
        from .profiles import FORMATS
        if fmt not in FORMATS + ("auto",):
            raise ValueError("format: " + " | ".join(FORMATS) + " | auto")
        self.format_choice = None if fmt == "auto" else fmt
        if self.folder:
            self._save()
        return self.effective_format()[0]

    def layout(self) -> str:
        """Graphic sizing follows the picture: portrait main clip → reel, otherwise youtube."""
        if not self.clips:
            return "reel"
        broll = set(self.broll_ids())
        ids = [c for c in self.clips if c not in broll] or list(self.clips)
        c = max((self.clips[i] for i in ids), key=lambda x: x.duration_s)
        w, h = (c.height, c.width) if abs(c.rotation) % 180 == 90 else (c.width, c.height)
        return "reel" if (w and h and h > w) else "youtube"

    def profile(self, fmt: str | None = None, style: str | None = None):
        f = fmt or self.effective_format()[0]
        return self.cfg.profile(f, style, layout=self.layout() if f == "commercial" else None)

    # ---------- phase 6: motion graphics ----------
    def _mg_setup(self, cl: Cutlist, plan: Plan):
        from .frames import display_size
        from .mg import tokens as _tokens
        from .mg.render import ensure
        info = ensure(self.cache.root)
        tok = _tokens.load(cl.brand)
        prof = self.profile(cl.format, cl.style)
        clip0 = self.clips[plan.pieces[0].clip]
        w, h = (cl.reframe.width, cl.reframe.height) if cl.reframe else display_size(clip0)
        fps = clip0.resolve_fps or clip0.fps
        if cl.reframe and cl.reframe.layout == "framed" and plan.reframe.get("window"):
            tok = {**tok, "framed_window": plan.reframe["window"]}
        return info, tok, prof, w, h, fps

    def framed_plate(self, cl: Cutlist, plan: Plan) -> dict | None:
        """The calm surface around the video of a framed reel, one rendered picture with a window, on its own track above the B-roll and below the graphics."""
        if not (cl.reframe and cl.reframe.layout == "framed" and plan.reframe.get("window")):
            return None
        from .mg import plate as _plate
        from .mg import tokens as _tokens
        clip0 = self.clips[plan.pieces[0].clip]
        fps = clip0.resolve_fps or clip0.fps
        tok = _tokens.load(cl.brand)
        frames = sum(pc.frames for pc in plan.pieces)
        return {"index": 0, "template": "framed_plate", "track": _plate.TRACK, "tl_start": 0, "frames": frames,
                "mov": _plate.render(self.cache.root, cl.reframe.width, cl.reframe.height, tuple(plan.reframe["window"]), tok["brand"]["plate"], fps, frames)}

    def _graphic_html(self, g, tok, prof, w, h, fps, stage: str = "above", drop_label: bool = False,
                      allow_scale: bool = True) -> tuple[str, dict]:
        from .mg.templates import build
        dur = round(g.frames / fps * 1000)
        if g.html:  # sandbox: free HTML with the seek contract (+ brand font/colours injected)
            from .mg.render import sandbox_wrap
            from .mg.templates import layout
            safe = layout("hook_text", prof.layout, w, h, g.face, tok, "above") or {}
            return sandbox_wrap(g.html, tok), {"safe": safe.get("safe"), "duration_ms": dur, "in_ms": tok["motion"]["dur"]["in_ms"],
                                               "out_ms": tok["motion"]["dur"]["out_ms"], "text_delay_ms": 0, "stage": "free",
                                               "layout": {"side": "frei (Sandbox)"}}
        return build(g.template, g.params, tok, prof.layout, w, h, fps, dur, face=g.face, expressive=g.expressive, stage=stage,
                     drop_label=drop_label, allow_scale=allow_scale)

    def _place(self, r, g, tok, prof, w, h, fps) -> dict:
        """Stage search (above → beside → below → not placed) with clearance to every head box of the span."""
        from .mg.place import place
        from .mg.templates import ATTEMPTS, spacing
        clearance = tok["layout"].get("head_clearance_px", 48) * w / (1080 if prof.layout == "reel" else 1920)
        sp = spacing(tok)
        min_pad = (sp["min_pad_x_cap"], sp["min_pad_y_cap"])
        fixed = "free" if g.html or g.template == "underline_arrow" else "lower_third" if g.template == "lower_third" else None
        if fixed:
            html, meta = self._graphic_html(g, tok, prof, w, h, fps, fixed if fixed != "free" else "above")
            res = place(r, lambda st, dr, sc: (html, meta), g.heads, clearance, attempts=((fixed, False, True),), min_pad=min_pad)
        else:
            has_label = any(g.params.get(k) for k in ("label", "title"))
            on_plate = bool(tok.get("framed_window")) and g.template == "hook_text"  # on the surface above the picture: no head can be near it
            res = place(r, lambda st, dr, sc: self._graphic_html(g, tok, prof, w, h, fps, st, dr, sc), [] if on_plate else g.heads, clearance,
                        attempts=(("above", False, True),) + ATTEMPTS if on_plate else ATTEMPTS, has_label=has_label, min_pad=min_pad)
        res["clearance"] = round(clearance, 1)
        if res.get("ok") and g.heads:
            res["motion_ratio"] = self._region_motion(g, res["bbox"], w, h)
        n_span = max(1, g.frames // 3)
        res["face_missing"] = round(1 - len(g.heads) / n_span, 2) if n_span else 0.0
        return res

    def _region_motion(self, g, bbox, w: int, h: int) -> float | None:
        """Soft gesture check: frame difference inside the graphic's box vs. the whole frame over the span (sampled frames,
        punch-in mapped back to the source). > ~1.5 = hands/gestures probably move behind/under the graphic."""
        import numpy as np
        from PIL import Image as _Image
        try:
            plan_pc = self._last_plan_pieces
        except AttributeError:
            return None
        from .mg.preview import frame_at
        ts = [hd[4] for hd in g.heads][::2][:16]
        if len(ts) < 3:
            return None
        imgs, boxes = [], []
        for t in ts:
            pc, src = frame_at(self._last_plan, t)
            p = self.frame_cache(self.clips[pc.clip]).get([src])[src]
            im = np.asarray(_Image.open(p).convert("L"), dtype=float)
            th, tw = im.shape
            z = pc.zoom or 1.0
            sx, sy = tw / w, th / h

            def back(x, y):
                return ((x - w / 2 - pc.pan) / z + w / 2) * sx, ((y - h / 2 + pc.tilt) / z + h / 2) * sy
            l, t0 = back(bbox[0], bbox[1])
            r, b = back(bbox[2], bbox[3])
            imgs.append(im)
            boxes.append((max(0, int(l)), max(0, int(t0)), min(tw, int(r)), min(th, int(b))))
        reg, whole = [], []
        for (a, ba), (c, bc) in zip(zip(imgs, boxes), list(zip(imgs, boxes))[1:]):
            d = np.abs(c - a)
            l, t0, r, b = bc
            if r - l > 2 and b - t0 > 2:
                reg.append(d[t0:b, l:r].mean())
            whole.append(d.mean())
        if not reg or not whole or np.mean(whole) < 1e-6:
            return None
        return round(float(np.mean(reg) / np.mean(whole)), 2)

    def preview_graphics(self, cl: Cutlist, index: int | None = None, debug: bool = True) -> tuple[str, list[bytes]]:
        from .mg import preview as pv
        from .mg.place import tried_text
        from .mg.render import Renderer
        cl, notes = self.prepare(cl)
        plan, _, _ = self.plan(cl)
        if not plan.ok:
            raise ValueError("Cutlist ungültig:\n" + "\n".join(plan.errors))
        self._last_plan, self._last_plan_pieces = plan, plan.pieces
        gs = [g for g in plan.graphics if index is None or g.index == index]
        if not gs:
            raise ValueError("keine Grafiken in der Cutlist (Abschnitt graphics, Durchgang motion)")
        info, tok, prof, w, h, fps = self._mg_setup(cl, plan)
        lines = [f"Grafik-Vorschau ({len(gs)} Grafik(en), Marke „{tok['brand_name']}“, Stil {tok['style'].get('label')}, "
                 f"Schrift {tok['brand']['font_family']}, {w}×{h} @ {fps:g} fps; Mindestabstand Kopf "
                 f"{tok['layout'].get('head_clearance_px', 48)} px"
                 + (", Hilfslinien: Kopfbox gelb, Grafik magenta, sichere Zone cyan, Text grün, Mindest-Innenabstand weiß)" if debug else ")")]
        if info["installed"]:
            lines.append(f"Einmalig installiert ({info['seconds']} s): {', '.join(info['installed'])}")
        lines += [f"Hinweis {n}" for n in notes] + [f"Warnung {x}" for x in plan.warnings if "Grafik" in x]
        rows, sc = [], 0.5
        from PIL import Image as _Image
        import io as _io
        with Renderer(self.cache.root, w, h) as r:
            for g in gs:
                res = self._place(r, g, tok, prof, w, h, fps)
                head = f"G{g.index} {g.template} {pv.fmt_time(g.tl_start, fps)}–{pv.fmt_time(g.tl_end, fps)}"
                if not res["ok"]:
                    lines.append(f"{head} · ✗ NICHT GESETZT – kein sauberer Platz ({tried_text(res['tried'])}). "
                                 "Andere Stelle, kürzerer Text oder ohne diese Grafik.")
                    continue
                html, meta = res["html"], res["meta"]
                stage_no = res.get("attempt")
                lines.append(f"{head} · Platz: {res['label']}" + (f" (Versuch {stage_no})" if stage_no else "")
                             + (f" – vorher: {tried_text(res['tried'])}" if res.get("tried") else ""))
                lines.append(f"   {'✓' if res['min_gap'] is None or res['min_gap'] >= res['clearance'] else '⚠'} kleinster Abstand zum Kopf "
                             f"{res['min_gap']} px (Minimum {res['clearance']:g} px, {res['heads']} Kopfpositionen im Zeitraum, "
                             f"Punch-in eingerechnet)")
                lines.append(f"   {'✓' if res['safe_ok'] else '✗'} sichtbare Pixel {res['bbox']} in der sicheren Zone "
                             f"{tuple(round(v) for v in meta['safe'])}" if meta.get("safe") else "")
                pd = res.get("padding")
                if pd:
                    lines.append(f"   {'✓' if pd['ok'] else '✗'} Innenabstand links {pd['left']}, rechts {pd['right']}, oben {pd['top']}, "
                                 f"unten {pd['bottom']} px (Minimum {pd['min_x']:.0f} seitlich, {pd['min_y']:.0f} oben/unten)")
                fit = res.get("fit") or {}
                lines.append(f"   Schriftgröße × {fit.get('scale', 1)} (Minimum × {meta.get('min_scale')}), {fit.get('lines', '?')} Zeile(n)")
                mr = res.get("motion_ratio")
                if mr is not None and mr > 1.5:
                    lines.append(f"   ⚠ viel Bewegung im Grafikbereich ({mr:g}× Bildmittel) – Hände/Gesten unter der Grafik? (weiche Warnung)")
                if res["face_missing"] > 0.2:
                    lines.append(f"   ⚠ Gesicht in {res['face_missing'] * 100:.0f} % der Frames nicht erkannt (Hände vor dem Gesicht, "
                                 "Bewegung?) – Platzierung prüfen")
                lines += ["   " + c for c in pv.checks(meta, res["bbox"], fit, None, tok)[-1:]]
                if g.html:
                    from .mg.render import sandbox_check
                    lines += ["   " + c for c in sandbox_check(r, html, tok, meta.get("safe"))]
                stills = r.stills(html, [t for t, _ in pv.stage_times(meta)])
                row = []
                for (t, png, _), (_, stage) in zip(stills, pv.stage_times(meta)):
                    fr = g.tl_start + round(t * fps / 1000)
                    pc, src = pv.frame_at(plan, fr)
                    base = pv.punched(pv.video_frame(self.clips[pc.clip], src, round(w * sc), round(h * sc)), pc.zoom, pc.pan,
                                      pc.tilt, sc).convert("RGBA")
                    gfx = _Image.open(_io.BytesIO(png)).convert("RGBA").resize(base.size, _Image.LANCZOS)
                    base.alpha_composite(gfx)
                    if debug:
                        hd = min(g.heads, key=lambda x: abs(x[4] - fr)) if g.heads else None
                        pv.debug_lines(base, sc, meta.get("safe"), hd, res["bbox"], res["min_gap"], res.get("padding"))
                    thumb = base.convert("RGB").resize(pv.THUMB, _Image.LANCZOS)
                    row.append(pv.label(thumb, f"G{g.index} {pv.fmt_time(fr, fps)} {stage}"))
                rows.append(row)
        if not rows:
            return "\n".join(lines), []
        return "\n".join(lines), [pv.sheet(rows, f"Grafiken über dem Video – {cl.timeline_name}")]

    def render_graphics(self, cl: Cutlist, plan: Plan) -> tuple[list[dict], dict]:
        from .mg.place import tried_text
        from .mg.render import Renderer, render_graphic
        info, tok, prof, w, h, fps = self._mg_setup(cl, plan)
        self._last_plan, self._last_plan_pieces = plan, plan.pieces
        out, skipped = [], []
        with Renderer(self.cache.root, w, h) as r:
            for g in plan.graphics:
                res = self._place(r, g, tok, prof, w, h, fps)
                if not res["ok"]:
                    skipped.append(f"G{g.index} {g.template}: kein sauberer Platz ({tried_text(res['tried'])})")
                    continue
                rr = render_graphic(self.cache.root, res["html"], w, h, fps, r)
                out.append({"index": g.index, "template": g.template, "track": g.track, "tl_start": g.tl_start, "frames": g.frames,
                            "mov": rr["mov"], "render_s": rr.get("seconds"), "encode_s": rr.get("encode_s"),
                            "cached": rr.get("cached"), "fit": res.get("fit"), "side": res["label"], "stage": res["stage"],
                            "bbox": list(res["bbox"]), "min_gap": res["min_gap"], "clearance": res["clearance"],
                            "safe_ok": res["safe_ok"], "safe": list(res["meta"].get("safe") or []), "padding": res.get("padding")})
        return out, {"installed": info["installed"], "setup_s": info["seconds"], "brand": tok["brand_name"], "w": w, "h": h,
                     "fps": fps, "skipped": skipped}

    # ---------- phase 6: review cards ----------
    def thumb(self, clip: Clip, frame: int, width: int = 180) -> str | None:
        """Small JPEG data URI of one source frame (for review cards)."""
        import base64
        import io

        from PIL import Image
        try:
            p = self.frame_cache(clip).get([frame])[frame]
            im = Image.open(p).convert("RGB")
            im.thumbnail((width, width * 2))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=72)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def review(self, timeline: str, decisions: list[dict], title: str | None = None, intro: str | None = None,
               images: bool = True) -> dict:
        """Enrich Claude's decisions (kind, question, words "c01:w0129-w0133" or segment "c01:s014", recommendation) with
        the spoken text (corrected), the position and a thumbnail; store them for submit_review."""
        import hashlib
        import time as _time

        from .formatting import ts as _ts
        kinds = {"grenzfall": "Grenzfall", "verworfen": "Verworfen", "widerspruch": "Inhaltlicher Widerspruch",
                 "take": "Take-Wahl", "schnitt": "Schnitt", "grafik": "Grafik", "reihenfolge": "Reihenfolge",
                 "frage": "Interviewfrage", "format": "Format"}
        corr = dict(self.corrections)
        built = self.built_cutlist(timeline)
        if built is not None:
            corr.update({c.word.lower(): c.text for c in built.corrections})
        out = []
        for k, d in enumerate(decisions, 1):
            item = {"id": d.get("id") or f"D{k}", "kind": (d.get("kind") or "grenzfall").lower(), "question": d.get("question", ""),
                    "recommendation": d.get("recommendation"), "text": d.get("text"), "where": None, "image": None}
            item["kind_label"] = kinds.get(item["kind"], item["kind"])
            if d.get("frame") and images:  # e.g. scene order: "c07:f0040"
                from .frames import parse_frame_id
                fcid, fidx = parse_frame_id(d["frame"])
                item["image"] = self.thumb(self.clip(fcid), fidx)
                item["where"] = d["frame"]
            ref = (d.get("words") or d.get("segment") or "").strip()
            m = re.fullmatch(r"(c\d+):(?:w0*(\d+)\s*[-–]\s*(?:c\d+:)?w0*(\d+)|s0*(\d+))", ref, re.I) if ref else None
            if m:
                clip = self.clip(m.group(1))
                at = self.analyzed(clip)
                if m.group(4):
                    seg = next((s for s in self.segments(clip, at) if s.ref.lower() == f"{clip.id}:s{int(m.group(4)):03d}"), None)
                    n0, n1 = seg.word_range() if seg else (None, None)
                else:
                    n0, n1 = int(m.group(2)), int(m.group(3))
                if n0 is not None:
                    words = [e for e in at.entries if e.id[0] == "w" and n0 <= int(e.id[1:]) <= n1]
                    if words:
                        if not item["text"]:
                            item["text"] = " ".join(corr.get(f"{clip.id}:{w.id}", w.text) for w in words)
                        item["where"] = f"{ref} · Aufnahme {_ts(words[0].start_s)}–{_ts(words[-1].end_s)}"
                        fps = clip.resolve_fps or clip.fps
                        if images:
                            item["image"] = self.thumb(clip, int((words[0].start_s + words[-1].end_s) / 2 * fps))
            out.append(item)
        rid = "R" + hashlib.sha1(f"{timeline}{_time.time()}".encode()).hexdigest()[:6]
        self.reviews[rid] = {"timeline": timeline, "decisions": [{k: v for k, v in it.items() if k != "image"} for it in out],
                             "answers": None}
        if self.folder:
            self._save()
        return {"view": "review", "review_id": rid, "timeline": timeline, "title": title or f"Bitte kurz entscheiden – {timeline}",
                "intro": intro, "decisions": out}

    def submit_review(self, review_id: str, answers: list[dict]) -> str:
        rv = self.reviews.get(review_id)
        if rv is None:
            raise KeyError(f"Review {review_id} unbekannt")
        labels = {"keep": "behalten", "drop": "raus", "any": "egal"}
        amap = {a["id"]: a.get("answer", "any") for a in answers}
        rv["answers"] = amap
        if self.folder:
            self._save()
        lines = [f"Review {review_id} zu {rv['timeline']}:"]
        for d in rv["decisions"]:
            lines.append(f"- {d['id']} ({d['kind_label']}): {d['question']} → {labels.get(amap.get(d['id'], 'any'), 'egal')}"
                         + (f" [{d['where'].split(' · ')[0]}]" if d.get("where") else ""))
        return "\n".join(lines)

    # ---------- phase 5: builds, transcript export ----------
    def remember_build(self, timeline_name: str, cl: Cutlist, graphics: list | None = None) -> None:
        self.builds[timeline_name] = cl.model_dump(mode="json", by_alias=True, exclude_none=True)
        if graphics:
            self.builds[timeline_name]["_graphics_report"] = graphics
        self._save()

    # ---------- phase 8.5: sense check ----------
    def _sense_file(self) -> Path:
        return self.cache.root / "sense" / (self.cache.workspace_file(self.folder).stem + ".json")

    def sense_estimate(self, timeline: str) -> dict:
        from . import sense
        cl, plan, analyzed, fps = self._built(timeline)
        data = Cache.read_json(self._sense_file()) or {"pieces": {}}
        regions = sense.missing_regions(data["pieces"], plan.pieces, fps)
        new_s = sum(b - a for a, b in regions)
        return {"regions": regions, "new_s": new_s, "cost_usd": round(new_s / 3600 * self.cfg.gladia_price_usd_per_hour, 2),
                "total_s": plan.total_seconds(self.clips)}

    def sense_check(self, timeline: str, wav: Path | None, transcribe=None) -> dict:
        """Hear the finished cut. wav = 16-kHz sound of the whole timeline (None if everything is cached). Only pieces not
        in the cache are transcribed: their regions are cut out of the wav, joined and sent to Gladia once."""
        from . import sense
        from .revise import spoken_words
        cl, plan, analyzed, fps = self._built(timeline)
        path = self._sense_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = Cache.read_json(path) or {"pieces": {}, "timing": {}}
        regions = sense.missing_regions(data["pieces"], plan.pieces, fps)
        new_s, cost = 0.0, 0.0
        if regions:
            tokens = transcribe(wav, regions)
            new_s = sum(b - a for a, b in regions)
            cost = new_s / 3600 * self.cfg.gladia_price_usd_per_hour
            fresh = sense.split_by_piece(tokens, plan.pieces, fps)
            rs = sense.recs(plan.pieces)
            for p, r in zip(plan.pieces, rs):  # only pieces fully inside a transcribed region count as heard
                a, b = r / fps, (r + p.frames) / fps
                if sense.piece_key(p) not in data["pieces"] and any(x - 0.01 <= a and b <= y + 0.01 for x, y in regions):
                    data["pieces"][sense.piece_key(p)] = fresh[sense.piece_key(p)]
        heard = sense.join_pieces(data["pieces"], plan.pieces, fps)
        exp = [{**w, "s": w["start"] / fps, "e": w["end"] / fps} for w in spoken_words(plan, analyzed, fps, plan.corrections)
               if w["text"]]  # corrected text: "Segelwerft" was a recognition error, not a seam problem
        rs = sense.recs(plan.pieces)
        cuts = [r / fps for r in rs[1:]]
        found, stats = sense.seams(exp, heard, cuts)
        wm = sense.word_map(exp, heard)
        data.setdefault("timing", {})[timeline] = {exp[i]["ref"]: [round(heard[j]["s"] * fps), round(heard[j]["e"] * fps)]
                                                   for i, j in wm.items()}
        Cache.write_json(path, data)
        for h in found:
            h["item"] = next((w["item"] for w in exp if w["s"] >= h["t"] - 0.01), None)
        return {"seams": found, "stats": stats, "heard": heard, "new_s": round(new_s, 1), "cost_usd": round(cost, 3),
                "total_s": plan.total_seconds(self.clips), "sections": sense.sections(heard)}

    def heard_timing(self, timeline: str) -> dict | None:
        data = Cache.read_json(self._sense_file()) if self.folder else None
        return (data or {}).get("timing", {}).get(timeline)

    # ---------- phase 10: reels from the long version ----------
    def reel_candidates(self, timeline: str, min_s: float = 10.0, max_s: float = 60.0) -> dict:
        """Structure of the finished long version for picking reels: sentences with speaker, time and simple signals, blocks of one speaker between section ends."""
        from .revise import spoken_words
        from .reels import blocks, sentences
        cl, plan, analyzed, fps = self._built(timeline)
        words = spoken_words(plan, analyzed, fps, plan.corrections)
        spk, src, energy = {}, {}, {}
        for cid in {pc.clip for pc in plan.pieces}:
            raw = self.cached_transcript(self.clips[cid])
            spk.update({f"{cid}:{t.id}": t.speaker for t in raw.tokens} if raw else {})
            src.update({f"{cid}:{e.id}": (e.start_s, e.end_s) for e in analyzed[cid].entries})
            energy[cid] = self.acoustic(self.clips[cid])
        sents = sentences(words, spk, src, energy, fps, plan.beats)
        return {"sentences": sents, "blocks": blocks(sents, min_s, max_s), "fps": fps, "total_s": plan.total_seconds(self.clips), "format": cl.format}

    def reel_cutlist(self, timeline: str, from_word: str, to_word: str, number: int = 1, title: str = "", remove: list | None = None, cold_open: dict | None = None,
                     layout: str = "full", aspect: str = "1:1") -> tuple[dict, list[str]]:
        """Cutlist of a reel: the items of the long version between two words, smaller cuts and a cold open applied. Only ever from one passage."""
        from .reels import spans_between
        cl, plan, analyzed, fps = self._built(timeline)
        spans, notes = spans_between(cl, from_word, to_word, remove or [], cold_open)
        base = cl.name or timeline
        items = [{"clip": c, "from_word": f"w{a:04d}", "to_word": f"w{b:04d}", "note": n} for c, a, b, n in spans]
        inside = lambda ref: any(c == ref.split(":")[0].lower() and a <= int(ref.split(":w")[1]) <= b for c, a, b, _ in spans)
        out = {"format": "reel", "timeline_name": f"{base}_Reel_{number:02d}", "reframe": {"source_timeline": timeline, "number": number, "title": title, "layout": layout, "aspect": aspect}, "items": items,
               "punch_in": {"mode": "alternate"}, "audio": cl.audio.model_dump(exclude_none=True) if cl.audio else {"target_lufs": -14},
               "corrections": [c.model_dump() for c in cl.corrections if inside(c.word)],
               "overlays": [o.model_dump(exclude_none=True) for o in cl.overlays if ":" in o.from_word and inside(o.from_word) and (not o.to_word or inside(o.to_word))]}
        if cl.brand:
            out["brand"] = cl.brand
        from .reframe import display, scale, upscales
        small = [self.clips[c] for c in {c for c, *_ in spans} if upscales(self.clips[c], 1080, 1920)]
        if layout == "full" and small:
            c = small[0]
            notes.append(f"Vollbild 9:16 skaliert die Quelle ({display(c)[0]}×{display(c)[1]}) auf {scale(c, 1080, 1920):.2f}× hoch. Schlage dem Nutzer layout=\"framed\" vor: "
                         "Video als 1:1 mittig auf ruhiger Fläche, nie über 1,0, Hook-Text darüber. Vollbild bleibt die Wahl, wenn er es lieber groß hat.")
        for g in cl.graphics:
            if inside(g.from_word):
                notes.append(f"In der langen Fassung liegt hier eine Grafik ({g.template}, {g.params}): für das Reel neu entscheiden, sie wird nicht übernommen")
        return out, notes

    def reel_preview(self, timeline: str, candidates: list[dict]) -> tuple[str, bytes | None]:
        """Numbered list and one sheet of 9:16 stills, each cropped on the head at the first word of the candidate."""
        from .reels import candidate_sheet, candidate_text
        cl, plan, analyzed, fps = self._built(timeline)
        stills = []
        for c in candidates:
            cid, n = c["from_word"].split(":")[0].lower(), int(c["from_word"].split(":w")[1])
            clip = self.clips[cid]
            at = analyzed.get(cid)
            w = next((e for e in at.entries if e.id == f"w{n:04d}"), None) if at else None
            frame = round(w.start_s * (clip.resolve_fps or clip.fps)) + 6 if w else 0
            pa = self.person(clip)
            box = pa["boxes"][min(frame, len(pa["boxes"]) - 1)]
            try:
                path = self.frame_cache(clip).get([frame])[frame]
            except Exception:
                path = None
            stills.append((path, None if box[0] < 0 else (box, tuple(int(v) for v in pa["size"]))))
        return candidate_text(candidates), candidate_sheet(stills)

    def reel_sheet_frames(self, timeline: str, frames: list[int]) -> dict:
        """Head boxes (timeline px) at timeline frames of a built reel, and the safe zone."""
        from .cutlist import head_track
        from .mg import tokens as _tokens
        cl, plan, analyzed, fps = self._built(timeline)
        faces = {}
        for cid in {pc.clip for pc in plan.pieces}:
            pa = self.person(self.clips[cid])
            faces[cid] = (pa["boxes"], tuple(int(v) for v in pa["size"]))
        tok = _tokens.load(cl.brand)
        safe = tok["layout"]["reel_1080x1920"]["safe_box"]
        marks = [(g.tl_start + round(g.frames * 0.5), f"G{g.index} {g.template}") for g in plan.graphics] + [(o.tl_start + o.frames // 2, f"O{o.index} {o.media}") for o in plan.overlays]
        frames = list(frames) + [t for t, _ in marks]
        return {"marks": marks, "heads": {t: (head_track(faces, plan, self.clips, t, t + 1, tok, cl_reframe=cl.reframe) or [None])[0] for t in frames},
                "safe": (safe["x"][0], safe["y"][0], safe["x"][1], safe["y"][1]), "reframe": plan.reframe, "cl": cl}

    # ---------- phase 8: correction loop ----------
    def _built(self, timeline: str):
        cl = self.built_cutlist(timeline)
        if cl is None:
            known = ", ".join(sorted(self.builds)) or "keine"
            raise LookupError(f"„{timeline}“ wurde nicht von {self.cfg and 'diesem Server'} gebaut – bekannt: {known}")
        plan, analyzed, _ = self.plan(cl)
        fps = self.clips[plan.pieces[0].clip].resolve_fps or self.clips[plan.pieces[0].clip].fps
        return cl, plan, analyzed, fps

    def locate(self, timeline: str, ref: str) -> dict:
        from .revise import resolve_ref, spoken_words
        cl, plan, analyzed, fps = self._built(timeline)
        loc = resolve_ref(ref, cl, plan, spoken_words(plan, analyzed, fps, plan.corrections), fps)
        loc["fps"] = fps
        return loc

    def locate_text(self, timeline: str, ref: str) -> str:
        loc = self.locate(timeline, ref)
        fps = loc["fps"]
        t = lambda f: "–" if f is None else ts(f / fps)
        head = {"item": "Item", "time": "Zeitpunkt", "quote": "Zitat"}[loc["kind"]]
        out = [f"{head} {ref!r} in „{timeline}“ → #{loc['item']:02d} · Wörter {loc['words'][0]}–{loc['words'][1]} · "
               f"Timeline {t(loc['start'])}–{t(loc['end'])}" + (f" · Treffer {loc['score']:.2f}" if loc.get("score") else ""),
               f"„{loc['text']}“"]
        if loc.get("sentence"):
            out.append(f"Satz: {loc['sentence'][0]}–{loc['sentence'][1]} „{loc['sentence_text']}“")
        for a in loc.get("alternatives") or []:
            out.append(f"Weitere Stelle ({a['score']:.2f}): {a['words'][0]}–{a['words'][1]} @{t(a['start'])} „{a['text']}“")
        return "\n".join(out)

    def revision(self, base_timeline: str, instructions: list[dict], existing: set[str] | None = None) -> tuple[Cutlist, list[str]]:
        from .revise import apply_ops, next_revision_name
        base = self.built_cutlist(base_timeline)
        if base is None:
            raise LookupError(f"„{base_timeline}“ unbekannt – gebaute Timelines: {', '.join(sorted(self.builds)) or 'keine'}")
        new, log = apply_ops(base, instructions, lambda r: self.locate(base_timeline, r))
        new.pass_, new.base_cutlist, new.revision_of = None, None, base_timeline
        new.timeline_name = next_revision_name(base_timeline, set(self.builds) | (existing or set()))
        new.__pydantic_fields_set__ = set(new.model_fields_set) | {"timeline_name"}
        return new, log

    def timeline_changes(self, timeline: dict) -> dict:
        from .revise import next_revision_name, timeline_changes
        cl, plan, analyzed, fps = self._built(timeline["name"])
        need = {it["clip"] for it in timeline["v1"] if it["clip"]} - set(analyzed)
        analyzed.update({c: self.analyzed(self.clips[c]) for c in need})
        res = timeline_changes(cl, plan, timeline, analyzed, self.clips)
        new = res["cutlist"]
        if new is not None:
            new.revision_of = timeline["name"]
            new.timeline_name = next_revision_name(timeline["name"], set(self.builds))
            new.__pydantic_fields_set__ = set(new.model_fields_set) | {"timeline_name"}
            nplan, _, _ = self.plan(new)
            bad = [e for e in nplan.errors if e.startswith("Overlay") or e.startswith("Grafik")]
            if bad:  # overlays/graphics whose words are gone: dropped, reported
                keep = [o for k, o in enumerate(new.overlays, 1) if not any(e.startswith(f"Overlay {k} ") for e in bad)]
                res["unclear"] += [f"{e} → Overlay nicht übernommen" for e in bad if e.startswith("Overlay")]
                new.overlays = keep
                gk = [g for k, g in enumerate(new.graphics, 1) if not any(e.startswith(f"Grafik {k} ") for e in bad)]
                res["unclear"] += [f"{e} → Grafik nicht übernommen" for e in bad if e.startswith("Grafik")]
                new.graphics = gk
                nplan, _, _ = self.plan(new)
            res["plan_ok"] = nplan.ok
            res["errors"] = nplan.errors
            same = [(p.clip, p.start_frame, p.frames) for p in nplan.pieces] == [
                (it["clip"], it["src_start"], it["frames"]) for it in timeline["v1"] if it["clip"]]
            res["reproduces"] = same
        return res

    def built_cutlist(self, timeline_name: str) -> Cutlist | None:
        d = self.builds.get(timeline_name)
        if not d:
            return None
        d = {k: v for k, v in d.items() if not k.startswith("_")}
        if "plan_version" not in (d.get("options") or {}):  # built before Phase 8.5: same cut points as back then
            d["options"] = {**(d.get("options") or {}), "plan_version": 1}
        return Cutlist(**d)

    def graphics_report(self, timeline_name: str) -> list:
        return list((self.builds.get(timeline_name) or {}).get("_graphics_report") or [])

    def export_dir(self) -> Path:
        from .guard import EXPORT_DIRNAME, LEGACY_EXPORT_DIRNAME, check_write_dir
        if self.cfg.export_folder:
            return check_write_dir(self.cfg.export_folder)
        if self.folder is None:
            raise LookupError("kein Ordner eingelesen (ingest_folder)")
        old = self.folder / LEGACY_EXPORT_DIRNAME
        return old if old.is_dir() and not (self.folder / EXPORT_DIRNAME).exists() else self.folder / EXPORT_DIRNAME

    def export_transcript(self, cl: Cutlist | None = None, timeline: dict | None = None, chapters: list | None = None,
                          max_words: int | None = None, max_line_chars: int | None = None, fmt: str | None = None) -> dict:
        """From a cutlist (plan) or a timeline read back from Resolve (resolve_bridge.read_timeline). Block sizes come
        from the format profile (reel: word-by-word captions, youtube/course: 2 lines × 42 characters, ≥ 1 s)."""
        from . import export as ex
        fmt = fmt or (cl.format if cl is not None and cl.format else None) or self.effective_format()[0]
        prof = self.profile(fmt)
        max_words = max_words or prof.srt_max_words
        max_line_chars = max_line_chars or prof.srt_line_chars
        sub = {"min_s": prof.srt_min_s, "comma_min_words": prof.srt_comma_min_words}
        if (cl is None) == (timeline is None):
            raise ValueError("export_transcript braucht genau eines: cutlist oder timeline")
        if cl is not None:
            cl, _ = self.prepare(cl)
            plan, analyzed, _ = self.plan(cl)
            if not plan.ok:
                raise ValueError("Cutlist ungültig:\n" + "\n".join(plan.errors))
            fps = self.clips[plan.pieces[0].clip].resolve_fps or self.clips[plan.pieces[0].clip].fps
            return ex.export(cl.timeline_name, plan.pieces, analyzed, fps, plan.corrections, self.export_dir(), fmt,
                             max_words, max_line_chars, chapters, **sub)
        items = [it for it in timeline["v1"] if it["clip"]]
        if not items:
            raise ValueError(f"Timeline „{timeline['name']}“ enthält keine Clips aus {self.folder}")
        unknown = len(timeline["v1"]) - len(items)
        analyzed = {cid: self.analyzed(self.clips[cid]) for cid in {it["clip"] for it in items}}
        corrections = dict(self.corrections)
        built = self.built_cutlist(timeline["name"])
        if built is not None:  # the cutlist this timeline was built from: its corrections and item boundaries
            plan, _, _ = self.plan(built)
            corrections.update(plan.corrections)
            same = [(pc.clip, pc.start_frame, pc.frames) for pc in plan.pieces] == [
                (it["clip"], it["src_start"], it["frames"]) for it in items]
            if same:
                for it, pc in zip(items, plan.pieces):
                    it["item"] = pc.item
        auto, unsure = self.glossary_corrections(set(analyzed), analyzed)
        n_auto = sum(1 for k, v in auto.items() if v and k not in corrections)
        corrections = {**auto, **corrections}  # what was corrected by hand wins
        pieces, recs = ex.pieces_from_timeline(items, analyzed)
        fps = timeline.get("fps") or items[0]["fps"]
        timing = self.heard_timing(timeline["name"])  # from sense_check: word times heard in the finished cut
        res = ex.export(timeline["name"], pieces, analyzed, fps, corrections, self.export_dir(), fmt,
                        max_words, max_line_chars, chapters, recs=recs, total_frames=timeline["frames"], timing=timing, **sub)
        res["heard_timing"] = len(timing) if timing else 0
        res["glossary"] = {"applied": n_auto, "unsure": unsure[:8]}
        if unknown:
            res["chapter_warnings"].append(f"{unknown} Clip(s) auf V1 ohne Transkript (nicht aus diesem Ordner) – ohne Text")
        return res

    def qc(self, timeline: dict, audio: dict | None = None) -> dict:
        from . import qc as _qc
        built = self.built_cutlist(timeline["name"])
        plan = self.plan(built)[0] if built is not None else None
        used = {it["clip"] for it in timeline["v1"] if it["clip"]}
        analyzed = {}
        for cid in used:
            try:
                analyzed[cid] = self.analyzed(self.clips[cid])
            except LookupError:
                pass
        prof = self.profile(built.format if built else None, built.style if built else None)
        master = self.master_clip(used) if used else None
        acoustics = {cid: self.acoustic(self.clips[cid]) for cid in analyzed}
        face_first = None
        if plan is not None and built.reframe and plan.pieces:
            first = plan.pieces[0]
            boxes = self.person(self.clips[first.clip])["boxes"]
            # a turned head escapes the detector for a moment: half a second decides
            fps0 = self.clips[first.clip].resolve_fps or self.clips[first.clip].fps
            face_first = any(f < len(boxes) and boxes[f][0] >= 0 for f in range(first.start_frame, first.start_frame + round(fps0 / 2)))
        res = _qc.run(timeline, self.clips, analyzed, prof, master, plan, audio, self.graphics_report(timeline["name"]), acoustics,
                      built.reframe if built else None, face_first)
        res["pass"] = built.pass_ if built else None
        return res

    # ---------- phase 4: corrections ----------
    def set_word_text(self, word: str, text: str | None) -> str:
        m = re.fullmatch(r"(c\d+):w0*(\d+)", word.strip(), re.I)
        if not m:
            raise ValueError(f"Wort-Referenz {word!r} ungültig (z. B. c01:w0113)")
        clip = self.clip(m.group(1))
        wid = f"w{int(m.group(2)):04d}"
        w = next((e for e in self.analyzed(clip).entries if e.id == wid), None)
        if w is None:
            raise KeyError(f"Wort {word} unbekannt")
        key = f"{clip.id}:{wid}"
        if text:
            self.corrections[key] = text
        else:
            self.corrections.pop(key, None)
        self._save()
        return f"{key}: „{w.text}“ → „{text}“" if text else f"{key}: Korrektur entfernt („{w.text}“)"

    def suggestions_text(self, clip_id: str) -> str:
        from .subtitles import suggest_from_script
        clip = self.clip(clip_id)
        at = self.analyzed(clip)
        out = []
        hits = self.glossary_hits(clip, at)
        if hits:
            out.append("Vorschläge aus dem Glossar (sicher = bekannte Fehlschreibung oder fast gleich):")
            out += [f"{h['refs'][0]}{'–' + h['refs'][-1].split(':')[1] if len(h['refs']) > 1 else ''} „{h['text']}“ → „{h['value']}“ "
                    f"({'sicher' if h['sure'] else 'Ähnlichkeit ' + format(h['score'], '.2f')})" for h in hits]
        if self.script:
            sug = suggest_from_script(self.segments(clip, at), at, self.script)
            if sug:
                out.append("Vorschläge aus dem Skript (nur prüfen, nicht blind übernehmen):")
                out += [f"{ref} „{cur}“ → „{new}“ ({lid})" for ref, cur, new, lid in sug]
        if not out:
            return ("Keine Vorschläge. Korrekturen sonst selbst erkennen (sinnlose Wörter im Transkript) und mit set_word_text setzen; "
                    "Eigennamen gehören ins Glossar (set_glossary).")
        return "\n".join(out)

    # ---------- phase 9: glossary ----------
    def glossary(self) -> list:
        from . import glossary as gl
        return gl.load(self.folder, self.glossary_terms)

    def set_glossary(self, terms: list[str]) -> str:
        from . import glossary as gl
        have = {gl.norm(x.split("=")[0]) for x in self.glossary_terms}
        self.glossary_terms += [t for t in terms if gl.norm(t.split("=")[0]) not in have]
        if self.folder:
            self._save()
        return "Glossar: " + ", ".join(t.value for t in self.glossary())

    def glossary_hits(self, clip: Clip, at: AnalyzedTranscript | None = None) -> list[dict]:
        from . import glossary as gl
        terms = self.glossary()
        if not terms:
            return []
        at = at or self.analyzed(clip)
        words = [{"ref": f"{clip.id}:{e.id}", "text": e.text, "t": e.start_s} for e in at.entries if e.id[0] == "w" and e.kind == "word"]
        return gl.find(words, terms)

    def glossary_corrections(self, clip_ids: set[str], analyzed: dict) -> tuple[dict[str, str], list[str]]:
        """Sure glossary spellings as corrections for the export; the unsure ones only as a hint."""
        from . import glossary as gl
        out, unsure = {}, []
        for cid in clip_ids:
            at = analyzed.get(cid)
            if at is None:
                continue
            by = {f"{cid}:{e.id}": e.text for e in at.entries if e.id[0] == "w"}
            for h in self.glossary_hits(self.clips[cid], at):
                if h["sure"]:
                    out.update(gl.corrections(h, by[h["refs"][-1]]))
                else:
                    unsure.append(f"{h['refs'][0]} „{h['text']}“ → „{h['value']}“?")
        return out, unsure

    def unsure_names(self) -> list[dict]:
        from . import glossary as gl
        toks = []
        for c in self.clips.values():
            if self.clip_role(c)[0] == "broll":
                continue
            raw = self.cached_transcript(c)
            if raw:
                toks += raw.tokens
        return gl.unsure_names(toks, self.glossary())

    def unsure_names_text(self) -> str:
        groups = self.unsure_names()
        if not groups:
            return ""
        lines = ["Eigennamen unsicher – bitte beim Nutzer nachfragen statt raten (set_glossary):"]
        for g in groups:
            lines.append(f"  {' / '.join(g['spellings'])} ({g['count']}×, Konfidenz ab {g['confidence']:.2f}"
                         + (", Schreibweise schwankt)" if g["varies"] else ")"))
        return "\n".join(lines)

    def glossary_check(self, cl: Cutlist, plan: Plan) -> tuple[list[str], list[str]]:
        """Graphics: a name on a lower third must be confirmed (glossary), texts must match the spelling."""
        from . import glossary as gl
        terms = self.glossary()
        errors, warnings = [], []
        for g in plan.graphics:
            for key, val in (g.params or {}).items():
                if isinstance(val, str):
                    warnings += [f"G{g.index} {key}: {x} (Glossar)" for x in gl.check_text(val, terms)]
            if g.template == "lower_third":
                name = str((g.params or {}).get("name", ""))
                missing = [w for w in name.split() if not gl.known(w, terms)]
                if missing:
                    errors.append(f"G{g.index}: Name „{name}“ ist nicht bestätigt – beim Nutzer nachfragen, dann set_glossary(["
                                  f"\"{name}\"]). Erst danach wird die Bauchbinde gerendert.")
        return errors, warnings
