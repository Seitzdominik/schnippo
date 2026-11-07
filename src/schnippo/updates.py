"""Tells when a newer version exists: one small request to the GitHub Releases API, at most once a day. Sends nothing but the request itself. No self-update."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from .branding import RELEASES_URL, REPO_SLUG

DAY = 86400


def _parts(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def newer(latest: str, current: str) -> bool:
    return _parts(latest) > _parts(current)


def notes(body: str, n: int = 4) -> list[str]:
    return [ln.strip(" -*").strip()[:120] for ln in (body or "").splitlines() if ln.lstrip().startswith(("-", "*"))][:n]


def check(current: str, cache_file: Path, force: bool = False, client=None, now=None) -> dict | None:
    """{"version", "url", "notes"} if something newer is out, else None. Network trouble never reaches the user."""
    now = now or time.time()
    cache_file = Path(cache_file)
    data = {}
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    if not force and "checked_at" in data and now - data["checked_at"] < DAY:
        return None if data.get("told") == data.get("version") else _found(data, current)
    try:
        http = client or httpx.Client(timeout=3, follow_redirects=True)
        r = http.get(f"https://api.github.com/repos/{REPO_SLUG}/releases/latest", headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return None
        rel = r.json()
    except (httpx.HTTPError, ValueError, OSError):
        return None
    data.update({"checked_at": now, "version": rel.get("tag_name", "").lstrip("v"), "url": rel.get("html_url") or RELEASES_URL, "notes": notes(rel.get("body", ""))})
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return _found(data, current)


def _found(data: dict, current: str) -> dict | None:
    v = data.get("version")
    return {"version": v, "url": data.get("url", RELEASES_URL), "notes": data.get("notes", [])} if v and newer(v, current) else None


def told(cache_file: Path, version: str) -> None:
    """The daily note is shown once per version; check_setup always shows it."""
    f = Path(cache_file)
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    data["told"] = version
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def text(info: dict) -> str:
    lines = [f"Neue Version {info['version']} verfügbar: {info['url']}"]
    lines += [f"• {n}" for n in info["notes"]]
    return "\n".join(lines)
