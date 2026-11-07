"""Optional sources with the user's own keys. Everything lands in the user's sound folder, nothing in the repo or the package.

Freesound: search and download of the MP3 preview with a plain token; the original file would need OAuth2 (docs: sounds/<id>/download).
ElevenLabs: POST /v1/sound-generation. Pixabay: its API documents images and videos only, so there is no audio source to connect."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import httpx

from .sfx import decode, library_dir
from .sfx_profile import distance, profile

FREESOUND = "https://freesound.org/apiv2"
ELEVENLABS = "https://api.elevenlabs.io/v1/sound-generation"
LICENSES = {"cc0": ('"Creative Commons 0"',), "cc-by": ('"Creative Commons 0"', '"Attribution"')}  # NonCommercial is never searched
GROUP_OF = {"swish": "whoosh", "tick": "click", "impact_soft": "impact", "alarm": "clock", "applause": "atmo"}
SKIP = {"typing": ("rt60_ms", "tail_share", "attack_ms"), "clock": ("rt60_ms", "tail_share", "attack_ms"), "atmo": ("rt60_ms", "tail_share", "attack_ms", "fall20_ms")}
QUERY = {"impact_soft": "soft impact", "tick": "ui tick", "click": "mouse click", "typing": "keyboard typing", "clock": "clock ticking", "alarm": "alarm clock",
         "downer": "tape stop", "atmo": "birds ambience", "applause": "applause", "ding": "notification ding"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "sound"


def _ranges(category: str) -> tuple[dict | None, tuple]:
    f = library_dir() / "analysis" / "groups.json"
    group = GROUP_OF.get(category, category)
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return data.get(group), SKIP.get(group, ())


def score(path: Path, category: str) -> float | None:
    """Distance of a sound to the reference group of its category: 0 = sounds like the group by key figures."""
    r, skip = _ranges(category)
    return distance(profile(decode(path)), r, skip)["total"] if r else None


def _store(folder: Path, name: str, data: bytes, meta: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / name
    f.write_bytes(data)
    f.with_name(f.name + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return f


def freesound_search(key: str, category: str, query: str | None = None, license: str = "cc0", limit: int = 5, max_s: float = 8.0, client: httpx.Client | None = None) -> list[dict]:
    """Candidates of a category, ranked by distance to the reference group (previews are measured in a temporary file, then deleted)."""
    if license not in LICENSES:
        raise ValueError("license: cc0 oder cc-by (nicht-kommerzielle Lizenzen sind ausgeschlossen)")
    http = client or httpx.Client(timeout=30, follow_redirects=True)
    head = {"Authorization": f"Token {key}"}
    lic = " OR ".join(LICENSES[license])
    r = http.get(f"{FREESOUND}/search/", headers=head, params={"query": query or QUERY.get(category, category), "filter": f"license:({lic})", "page_size": 15,
                                                               "fields": "id,name,username,license,duration,previews,url"})
    r.raise_for_status()
    rows = [s for s in r.json().get("results", []) if s.get("duration", 0) <= max_s and "NonCommercial" not in s.get("license", "")]
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in rows[:max(limit * 2, 8)]:
            url = s["previews"]["preview-hq-mp3"]
            p = http.get(url, headers=head)
            d = None
            if p.status_code == 200:
                f = Path(tmp) / f"{s['id']}.mp3"
                f.write_bytes(p.content)
                try:
                    d = score(f, category)
                except Exception:
                    d = None
            out.append({"id": s["id"], "name": s["name"], "author": s["username"], "license": s["license"], "duration_s": s["duration"], "url": s.get("url", ""), "distance": d})
    out.sort(key=lambda c: (c["distance"] is None, c["distance"] or 0))
    return out[:limit]


def freesound_fetch(key: str, sound_id: int, category: str, folder: Path, client: httpx.Client | None = None) -> Path:
    http = client or httpx.Client(timeout=60, follow_redirects=True)
    head = {"Authorization": f"Token {key}"}
    r = http.get(f"{FREESOUND}/sounds/{int(sound_id)}/", headers=head, params={"fields": "id,name,username,license,url,previews"})
    r.raise_for_status()
    s = r.json()
    if "NonCommercial" in s["license"] or "noncommercial" in s["license"].lower():
        raise ValueError(f"{s['name']}: nicht-kommerzielle Lizenz, wird nicht geladen")
    a = http.get(s["previews"]["preview-hq-mp3"], headers=head)
    a.raise_for_status()
    cc0 = "Creative Commons 0" in s["license"] or "publicdomain/zero" in s["license"]
    credit = "" if cc0 else f"„{s['name']}“ von {s['username']} ({s.get('url', '')}), Lizenz {s['license']}"
    return _store(folder / "freesound" / category, f"{s['id']}_{_slug(s['name'])}.mp3", a.content,
                  {"source": "Freesound", "author": s["username"], "license": s["license"], "url": s.get("url", ""), "credit": credit, "quality": "Vorschau, MP3 128 kBit/s"})


def elevenlabs_generate(key: str, text: str, category: str, folder: Path, seconds: float | None = None, loop: bool = False, client: httpx.Client | None = None) -> Path:
    if seconds is not None and not 0.5 <= seconds <= 30:
        raise ValueError("seconds: 0,5 bis 30")
    http = client or httpx.Client(timeout=120)
    body: dict = {"text": text, "loop": loop}
    if seconds is not None:
        body["duration_seconds"] = seconds
    r = http.post(ELEVENLABS, headers={"xi-api-key": key}, json=body, params={"output_format": "mp3_44100_128"})
    r.raise_for_status()
    name = f"{_slug(text)}_{abs(hash((text, seconds))) % 10000:04d}.mp3"
    return _store(folder / "elevenlabs" / category, name, r.content, {"source": "ElevenLabs", "author": "", "license": "ElevenLabs, eigener Plan (kommerziell ab Starter)", "url": "", "credit": "",
                                                                      "prompt": text})
