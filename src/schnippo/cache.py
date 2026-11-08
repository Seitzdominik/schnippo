"""Content-addressed analysis cache.

Key = sha256(size + first MiB + last MiB). mtime is deliberately *not* part of the key:
copying takes to another drive (which often resets mtime) must not trigger a re-transcription
(= real money). mtime is stored alongside and reported if it changed.

Layout::

    <cache_dir>/media/<fp>/audio16k.wav
                          /acoustic.npz                       RMS envelope + voicing (10 ms)
                          /raw.<provider>.<lang>.json        provider response (as received)
                          /tokens.<provider>.<lang>.json     normalised RawTranscript
    <cache_dir>/workspaces/<sha1(folder)>.json               clip-id registry per ingested folder
"""

from __future__ import annotations

from . import platforms
import hashlib
import json
import os
from pathlib import Path

CHUNK = 1024 * 1024


def fingerprint(path: Path) -> str:
    size = path.stat().st_size
    h = hashlib.sha256()
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(CHUNK))
        if size > CHUNK:
            f.seek(max(size - CHUNK, CHUNK))
            h.update(f.read(CHUNK))
    return h.hexdigest()[:24]


class Cache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def media_dir(self, fp: str) -> Path:
        d = self.root / "media" / fp
        d.mkdir(parents=True, exist_ok=True)
        return d

    def workspace_file(self, folder: Path) -> Path:
        d = self.root / "workspaces"
        d.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(str(folder.resolve()).encode()).hexdigest()[:16]
        return d / f"{key}.json"

    @staticmethod
    def read_json(p: Path):
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    @staticmethod
    def write_json(p: Path, data) -> None:
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        platforms.replace(tmp, p)
