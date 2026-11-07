"""Four passes with exactly one job each: rough → fine → broll → polish (guides/01–04).

resolve(cl, base, profile) returns the *effective* cutlist the server plans and builds:
  * later passes start from the cutlist of the previous one (base_cutlist = its timeline name, or inline),
  * only the fields the current pass may change are taken from the request; others are ignored with a warning,
  * profile defaults fill every option the request (or the base) did not set explicitly,
  * the timeline is named <name>_V1_Rough … _V4_Polish unless timeline_name is given.
Cutlists without "pass" keep the old behaviour (everything allowed, profile defaults for unset options).
"""

from __future__ import annotations

from .cutlist import Cutlist, CutOptions, PunchIn
from .profiles import Profile

PASSES = ("rough", "fine", "broll", "polish", "motion")
SUFFIX = {"rough": "V1_Rough", "fine": "V2_Fine", "broll": "V3_BRoll", "polish": "V4_Polish", "motion": "V5_Motion"}
PREVIOUS = {"fine": "rough", "broll": "fine", "polish": "broll", "motion": "polish"}
# request fields a pass may set (besides name/pass/base_cutlist/timeline_name/format/style/version)
ALLOWED = {
    "rough": {"items", "rejected", "corrections", "markers", "alternates"},
    "fine": {"items", "rejected", "corrections", "markers", "alternates", "options", "punch_in", "item_changes", "beats"},
    "broll": {"overlays", "sfx", "sfx_mode", "corrections", "markers", "alternates"},
    "polish": {"audio", "sfx_mode", "corrections", "markers", "alternates", "item_changes", "items"},
    "motion": {"graphics", "brand", "sfx", "sfx_mode", "corrections", "markers"},
}
META = {"name", "pass_", "base_cutlist", "timeline_name", "format", "style", "version", "revision_of"}


def timeline_name(cl: Cutlist) -> str:
    if "timeline_name" in cl.model_fields_set or not (cl.name and cl.pass_):
        return cl.timeline_name
    return f"{cl.name}_{SUFFIX[cl.pass_]}"


def option_defaults(profile: Profile, pass_name: str | None) -> dict:
    if pass_name == "rough":  # hard cuts at item boundaries only; pauses and fillers inside items stay
        return {"pre_pad_ms": profile.pre_pad_ms, "post_pad_ms": profile.post_pad_ms, "cut_fillers": False,
                "tighten_gaps_over_ms": profile.rough_max_gap_ms, "keep_pause_ms": profile.rough_keep_gap_ms,
                "motion_aware_cuts": False, "keep_breaths": True, "decay_max_ms": profile.decay_max_ms, "edge_db": profile.edge_db}
    return {"pre_pad_ms": profile.pre_pad_ms, "post_pad_ms": profile.post_pad_ms,
            "tighten_gaps_over_ms": profile.tighten_gaps_over_ms, "keep_pause_ms": profile.keep_pause_ms,
            "keep_pause_mid_ms": profile.keep_pause_mid_ms, "beat_key_ms": profile.deliberate_pause_ms,
            "beat_section_ms": profile.beat_section_ms, "keep_breaths": profile.keep_breaths,
            "decay_max_ms": profile.decay_max_ms, "edge_db": profile.edge_db}


def _apply_option_defaults(opts: CutOptions, defaults: dict, force: bool) -> CutOptions:
    upd = {k: v for k, v in defaults.items() if force or k not in opts.model_fields_set}
    new = opts.model_copy(update=upd)
    new.__pydantic_fields_set__ = set(opts.model_fields_set)  # keep "explicit" = what the user set
    return new


def resolve(cl: Cutlist, base: Cutlist | None, profile: Profile) -> tuple[Cutlist, list[str]]:
    notes: list[str] = []
    ps = cl.pass_
    if ps is None:
        eff = cl.model_copy(deep=True)
        eff.options = _apply_option_defaults(eff.options, option_defaults(profile, None), force=False)
        _punch_defaults(eff, profile)
        return eff, notes
    if ps not in PASSES:
        raise ValueError(f"pass muss {' | '.join(PASSES)} sein, nicht {ps!r}")
    given = cl.model_fields_set - META
    if ps == "rough":
        if base is not None:
            notes.append("rough: base_cutlist wird ignoriert (der Rough Cut ist der erste Durchgang)")
        eff = cl.model_copy(deep=True)
    else:
        if base is None:
            raise ValueError(f"pass „{ps}“ braucht base_cutlist (die Timeline des Durchgangs „{PREVIOUS[ps]}“)")
        if base.pass_ and PASSES.index(base.pass_) >= PASSES.index(ps):
            notes.append(f"{ps}: base_cutlist stammt aus dem Durchgang „{base.pass_}“ (erwartet: „{PREVIOUS[ps]}“)")
        eff = base.model_copy(deep=True)
        for f in given & ALLOWED[ps]:
            if f == "items":
                continue
            setattr(eff, f, getattr(cl, f).model_copy(deep=True) if hasattr(getattr(cl, f), "model_copy")
                    else [x.model_copy(deep=True) if hasattr(x, "model_copy") else x for x in getattr(cl, f)]
                    if isinstance(getattr(cl, f), list) else getattr(cl, f))
        if "items" in given and "items" in ALLOWED[ps]:
            changed = _item_diff(base, cl)
            eff.items = [i.model_copy(deep=True) for i in cl.items]
            eff.rejected = [r.model_copy() for r in cl.rejected] if "rejected" in given else eff.rejected
            if changed:
                label = "Take-/Inhaltsänderung gegenüber dem Rough Cut" if ps == "fine" else \
                    "Schnittänderung im Polish – nur wenn die QC einen Fehler gefunden hat"
                notes.append(f"{ps}: {label}: {'; '.join(changed[:6])}{' …' if len(changed) > 6 else ''}")
        eff.item_changes = []
        if "sfx" in given and base.sfx:
            notes.append(f"{ps}: „sfx“ ersetzt die {len(base.sfx)} Effekt(e) aus „{base.timeline_name}“ – dort gesetzte Effekte mit aufführen")
    eff.pass_ = ps
    eff.name = cl.name or (base.name if base else None)
    eff.base_cutlist = cl.base_cutlist if isinstance(cl.base_cutlist, str) else None
    for f in ("format", "style"):
        if f in cl.model_fields_set:
            setattr(eff, f, getattr(cl, f))
    ignored = sorted(given - ALLOWED[ps])
    for f in ignored:
        notes.append(f"{ps}: „{f}“ wird ignoriert – {_why(ps, f)}")
    # item changes (fine/polish)
    for ch in cl.item_changes if ps in ("fine", "polish") else []:
        if not 1 <= ch.index <= len(eff.items):
            notes.append(f"{ps}: item_changes #{ch.index} existiert nicht (1–{len(eff.items)})")
            continue
        upd = {k: v for k, v in ch.model_dump(exclude={"index"}, exclude_unset=True).items()}
        eff.items[ch.index - 1] = eff.items[ch.index - 1].model_copy(update=upd)
    if ps == "rough":
        for k, it in enumerate(eff.items, 1):
            bad = [f for f in ("zoom", "pause_after_ms", "beat") if getattr(it, f) is not None]
            if bad:
                notes.append(f"rough: Item #{k}: {', '.join(bad)} ignoriert (Punch-ins und Pausen-Feinarbeit erst im Fine Cut)")
                eff.items[k - 1] = it.model_copy(update={f: None for f in bad})
        eff.punch_in, eff.overlays, eff.audio, eff.sfx = None, [], None, []
    if ps == "fine":
        eff.overlays, eff.audio, eff.sfx = [], None, []
    if ps == "broll":
        eff.audio = None
    if ps != "motion":
        if "graphics" in given:
            notes.append(f"{ps}: „graphics“ wird ignoriert – Grafiken kommen im Durchgang 5 (motion)")
        eff.graphics = []
    # options: rough = fixed hard-cut options; later passes = profile defaults for what nobody set explicitly
    if ps != "rough" and eff.alternates:  # the alternates timeline belongs to the take decision (rough cut) only
        if "alternates" in given and cl.alternates:
            notes.append(f"{ps}: „alternates“ wird ignoriert – die Alternativen-Timeline gibt es nur im Rough Cut")
        eff.alternates = False
    if ps == "rough":
        if "options" in given:
            notes.append("rough: „options“ wird ignoriert – Pausen/Füller bearbeitet erst der Fine Cut")
        eff.options = _apply_option_defaults(CutOptions(), option_defaults(profile, "rough"), force=True)
    else:
        if "options" in given and "options" in ALLOWED[ps]:
            opts = cl.options
        elif base is not None and base.pass_ == "rough":
            opts = CutOptions()  # the rough cut's hard-cut options are not inherited
        else:
            opts = eff.options
        eff.options = _apply_option_defaults(opts, option_defaults(profile, "fine"), force=False)
    _punch_defaults(eff, profile)
    if "timeline_name" not in cl.model_fields_set and eff.name:
        eff.timeline_name = f"{eff.name}_{SUFFIX[ps]}"
        eff.__pydantic_fields_set__ = set(eff.model_fields_set) - {"timeline_name"}
    elif "timeline_name" in cl.model_fields_set:
        eff.timeline_name = cl.timeline_name
    if not eff.items:
        raise ValueError(f"{ps}: keine Items (Rough Cut: items angeben; spätere Durchgänge: base_cutlist)")
    return eff, notes


def _punch_defaults(eff: Cutlist, profile: Profile) -> None:
    if eff.punch_in is not None:
        upd = {}
        if eff.punch_in.scale is None:
            upd["scale"] = profile.punch_in_scale
        if eff.punch_in.rule is None:
            upd["rule"] = profile.punch_in_rule
        if eff.punch_in.min_hold_s is None:
            upd["min_hold_s"] = profile.punch_min_hold_s
        if eff.punch_in.variation is None:
            upd["variation"] = list(profile.punch_in_variation)
        if eff.punch_in.variation_every is None:
            upd["variation_every"] = profile.punch_variation_every
        if upd:
            eff.punch_in = eff.punch_in.model_copy(update=upd)


def _why(ps: str, f: str) -> str:
    return {
        "rough": "im Rough Cut nur Inhalt, Reihenfolge, Take-Wahl (Zoom/B-Roll/Audio kommen später)",
        "fine": "B-Roll kommt im Durchgang 3, Ton im Durchgang 4",
        "broll": "Schnitt und Timing aus dem Fine Cut bleiben; Ton kommt im Durchgang 4",
        "polish": "im Polish nur Ton, QC und Export",
        "motion": "Motion Graphics ändern Schnitt, B-Roll und Ton nicht",
    }[ps]


def _item_diff(base: Cutlist, cl: Cutlist) -> list[str]:
    key = lambda it: (it.clip.lower(), it.from_word, it.to_word)
    b, c = [key(i) for i in base.items], [key(i) for i in cl.items]
    out = [f"neu {k[0]} {k[1]}–{k[2]}" for k in c if k not in b] + [f"entfernt {k[0]} {k[1]}–{k[2]}" for k in b if k not in c]
    if not out and b != c:
        out.append("Reihenfolge geändert")
    return out


__all__ = ["PASSES", "SUFFIX", "resolve", "timeline_name", "option_defaults", "PunchIn"]
