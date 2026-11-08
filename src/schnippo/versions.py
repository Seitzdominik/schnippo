"""The working timeline and its backups (Phase 13).

Every project has one timeline "<Name>_Schnippo" that Schnippo keeps working on. Before each change it is duplicated into the bin
Schnippo/Versionen as "<Name>_Schnippo__<date>_<time>_<what comes next>"; the newest few stay, older ones are removed.

Measured on 21.1.2 (docs/ENTWICKLUNG.md): DuplicateTimeline copies items, markers and timeline settings and returns in 0.1 s; the copy
lands in the bin of the source (whatever the current folder is) and becomes the current timeline, so it is moved with MoveClips via
Timeline.GetMediaPoolItem and the working timeline is selected again. The copy is independent of the original.

Only timelines that carry the pattern AND lie in that bin are ever deleted.
"""

from __future__ import annotations

import re
import time
from datetime import datetime

WORK_SUFFIX = "_Schnippo"
ROOT_BIN = "Schnippo"
VERSIONS_BIN = "Versionen"
SEP = "__"
KEEP_DEFAULT = 5
_STAMP = re.compile(r"^(?P<work>.+?)__(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})_(?P<label>.*)$")


class BackupFailed(RuntimeError):
    """No backup, no change."""


def work_name(stem: str) -> str:
    return stem if stem.endswith(WORK_SUFFIX) else f"{stem}{WORK_SUFFIX}"


def _slug(label: str) -> str:
    out = re.sub(r"[^\w äöüÄÖÜß-]+", "", label).strip().replace(" ", "_")
    return out[:40] or "Sicherung"


def version_name(work: str, label: str, now: datetime | None = None) -> str:
    return f"{work}{SEP}{(now or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}_{_slug(label)}"


def parse(name: str) -> dict | None:
    """{"work", "when", "label"} of a backup name, None for anything else."""
    m = _STAMP.match(name)
    if not m:
        return None
    return {"work": m["work"], "when": f"{m['date']} {m['time'].replace('-', ':')}", "label": m["label"].replace("_", " ")}


def _sub(mp, parent, name):
    for f in parent.GetSubFolderList() or []:
        if f.GetName() == name:
            return f
    return mp.AddSubFolder(parent, name)


def bins(mp) -> tuple:
    """(Schnippo, Schnippo/Versionen). AddSubFolder also makes the new bin current: the caller's bin is restored."""
    cur = mp.GetCurrentFolder() if hasattr(mp, "GetCurrentFolder") else None
    root = _sub(mp, mp.GetRootFolder(), ROOT_BIN)
    ver = _sub(mp, root, VERSIONS_BIN)
    if cur is not None and hasattr(mp, "SetCurrentFolder"):
        mp.SetCurrentFolder(cur)
    return root, ver


def _timelines(p) -> dict:
    return {t.GetName(): t for t in (p.GetTimelineByIndex(i + 1) for i in range(p.GetTimelineCount())) if t is not None}


def fingerprint(tl) -> list:
    """What must be the same in a copy: every item of every track with position, length, source in-point, plus the markers."""
    out = []
    for kind in ("video", "audio"):
        for k in range(1, (tl.GetTrackCount(kind) or 0) + 1):
            out.append((kind, k, sorted((i.GetStart(), i.GetDuration(), i.GetLeftOffset() or 0) for i in tl.GetItemListInTrack(kind, k) or [])))
    return out + [sorted((tl.GetMarkers() or {}).keys())]


def _in_bin(ver) -> set[str]:
    return {c.GetName() for c in ver.GetClipList() or [] if c.GetClipProperty("Type") == "Timeline"}


def backup(p, work_tl, label: str, keep: int = KEEP_DEFAULT, now: datetime | None = None) -> dict:
    """Duplicate into Schnippo/Versionen and verify the copy; raises BackupFailed, the caller then changes nothing."""
    mp = p.GetMediaPool()
    work = work_tl.GetName()
    _, ver = bins(mp)
    current = p.GetCurrentTimeline()
    name = version_name(work, label, now)
    if name in _timelines(p):
        time.sleep(1.1)  # two backups within a second
        name = version_name(work, label)
    copy = work_tl.DuplicateTimeline(name)
    if copy is None:
        raise BackupFailed(f"Sicherung von „{work}“ fehlgeschlagen: Resolve hat das Duplizieren abgelehnt. Nichts geändert.")
    try:
        if fingerprint(copy) != fingerprint(work_tl):
            mp.DeleteTimelines([copy])
            raise BackupFailed(f"Sicherung von „{work}“ weicht vom Original ab. Nichts geändert.")
        item = copy.GetMediaPoolItem()
        if item is None or not mp.MoveClips([item], ver):
            raise BackupFailed(f"Sicherung „{name}“ ließ sich nicht in den Bin {ROOT_BIN}/{VERSIONS_BIN} legen. Nichts geändert.")
    finally:
        back = current if current is not None and current.GetName() != name else work_tl
        p.SetCurrentTimeline(back)
    removed = prune(p, work, keep)
    return {"name": name, "label": label, "removed": removed}


def versions_of(p, work: str) -> list[dict]:
    """Backups of a working timeline, newest first."""
    _, ver = bins(p.GetMediaPool())
    out = [{"name": n, **parse(n)} for n in _in_bin(ver) if parse(n) and parse(n)["work"] == work]
    return sorted(out, key=lambda v: v["when"], reverse=True)


def prune(p, work: str, keep: int = KEEP_DEFAULT) -> list[str]:
    """Older backups of this working timeline go. Only names of the backup pattern in the backup bin, never anything else."""
    mp = p.GetMediaPool()
    drop = [v["name"] for v in versions_of(p, work)[max(keep, 1):]]
    if not drop:
        return []
    have = _timelines(p)
    tls = [have[n] for n in drop if n in have]
    if tls and not mp.DeleteTimelines(tls):
        return []
    return drop


def restore(p, version: str, keep: int = KEEP_DEFAULT) -> dict:
    """A backup becomes the working timeline again. The state being replaced is backed up first."""
    info = parse(version)
    if info is None:
        raise ValueError(f"„{version}“ ist keine Schnippo-Sicherung")
    mp = p.GetMediaPool()
    root, ver = bins(mp)
    if version not in _in_bin(ver):
        known = ", ".join(v["name"] for v in versions_of(p, info["work"])) or "keine"
        raise LookupError(f"Sicherung „{version}“ liegt nicht in {ROOT_BIN}/{VERSIONS_BIN}. Vorhanden: {known}")
    have = _timelines(p)
    src, work = have[version], have.get(info["work"])
    before = backup(p, work, "vor Wiederherstellung", keep=keep + 1) if work is not None else None
    tmp_name = f"{info['work']}{SEP}wiederherstellen"
    if tmp_name in have:
        raise RuntimeError(f"„{tmp_name}“ existiert schon (abgebrochene Wiederherstellung?). Bitte in Resolve löschen.")
    tmp = src.DuplicateTimeline(tmp_name)
    if tmp is None or fingerprint(tmp) != fingerprint(src):
        raise RuntimeError(f"„{version}“ ließ sich nicht kopieren. Die Arbeits-Timeline ist unverändert.")
    p.SetCurrentTimeline(tmp)
    if work is not None and not mp.DeleteTimelines([work]):
        mp.DeleteTimelines([tmp])
        raise RuntimeError("Die alte Arbeits-Timeline ließ sich nicht ersetzen. Sie ist unverändert.")
    if not tmp.SetName(info["work"]):
        raise RuntimeError(f"Umbenennen abgelehnt: die Wiederherstellung heißt „{tmp_name}“.")
    item = tmp.GetMediaPoolItem()
    if item is not None:
        mp.MoveClips([item], root)
    prune(p, info["work"], keep)
    return {"work": info["work"], "from": version, "before": before["name"] if before else None, "when": info["when"], "label": info["label"]}
