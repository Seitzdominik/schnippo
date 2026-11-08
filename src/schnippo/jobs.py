"""Job state for long tools (build, transcription): what was asked, which stage is done, how it ended. A job still
marked "läuft" that no thread of this server process runs anymore was interrupted (crash, kill, app quit)."""

from __future__ import annotations

from . import platforms
import json
import os
import time
import uuid
from pathlib import Path

_ACTIVE: set[str] = set()  # job ids running in THIS process


class Jobs:
    def __init__(self, root: Path):
        self.dir = Path(root) / "jobs"

    def _file(self, jid: str) -> Path:
        return self.dir / f"{jid}.json"

    def _write(self, job: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        job["updated"] = time.time()
        tmp = self._file(job["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        platforms.replace(tmp, self._file(job["id"]))

    def start(self, kind: str, request: dict, label: str, folder: str | None) -> dict:
        job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "kind": kind, "label": label,
               "folder": folder, "request": request, "stages": [], "info": {}, "status": "läuft", "error": None,
               "started": time.time()}
        _ACTIVE.add(job["id"])
        self._write(job)
        return job

    def stage(self, job: dict, name: str, info: dict | None = None) -> None:
        job["stages"].append(name)
        if info:
            job["info"].update(info)
        self._write(job)

    def finish(self, job: dict, status: str, error: str | None = None, **info) -> None:
        job["status"], job["error"] = status, error
        job["info"].update(info)
        _ACTIVE.discard(job["id"])
        self._write(job)

    def load(self, jid: str) -> dict:
        f = self._file(jid)
        if not f.exists():
            raise KeyError(f"Auftrag {jid} unbekannt")
        job = json.loads(f.read_text(encoding="utf-8"))
        if job["status"] == "läuft" and job["id"] not in _ACTIVE:
            job["status"] = "unterbrochen"
        return job

    def open_jobs(self) -> list[dict]:
        """Interrupted or failed jobs, newest first (finished and resumed ones are not listed)."""
        out = []
        for f in sorted(self.dir.glob("*.json"), reverse=True) if self.dir.exists() else []:
            try:
                job = self.load(f.stem)
            except (OSError, ValueError, KeyError):
                continue
            if job["status"] in ("unterbrochen", "fehlgeschlagen"):
                out.append(job)
        return out
