"""Check before every commit and release: nothing private may reach this public repository.

    uv run python tools/check_public.py            # files git would publish
    uv run python tools/check_public.py --all      # every file in the folder
    uv run python tools/check_public.py --history  # every version of every file in every commit, and the commit messages

Finds faces in images, media outside the allowed places, names from test projects (kept here only as salted hashes, so the
list itself gives nothing away), known reference audio, API keys and personal paths. Exit code 1 on any finding."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DENY = Path(__file__).with_name("public_denylist.json")

MEDIA = {".mov", ".mp4", ".m4v", ".mxf", ".braw", ".avi", ".mkv", ".webm", ".wav", ".aif", ".aiff", ".mp3", ".m4a", ".flac",
         ".ogg", ".png", ".jpg", ".jpeg", ".gif", ".heic", ".tif", ".tiff", ".webp", ".bmp"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ALLOWED_MEDIA = ("src/schnippo/data/sfx/wav/*.wav", "docs/hoerbeispiele/*.m4a", "packaging/icon.png", "assets/brand/*.png",
                 "plugin/icon.png", "plugin/.claude-plugin/icon.png", "docs/bilder/*.png", "docs/bilder/*.gif", "website/meta/*.png", "website/assets/*.png")
SKIP_TEXT = ("uv.lock", "tools/public_denylist.json", "tools/check_public.py", "tests/test_check_public.py")
KEYS = {
    "OpenAI/Anthropic-Key": r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}",
    "GitHub-Token": r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}",
    "PyPI-Token": r"\bpypi-[A-Za-z0-9_\-]{30,}",
    "AWS-Key": r"\bAKIA[0-9A-Z]{16}\b",
    "Slack-Token": r"\bxox[abps]-[A-Za-z0-9\-]{10,}",
    "Key im Klartext": r"(?i)(?:api[_-]?key|x-gladia-key|xi-api-key|token)[\"']?\s*[:=]\s*[\"']?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "Privater Schlüssel": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}
PATHS = r"/Users/(?!me\b|name\b|du\b|runner\b|<)[A-Za-z0-9._\-]+|/Volumes/(?!<|Name\b|SSD\b|Projekte\b|X\b)[A-Za-z0-9._\-]+"
WORD = re.compile(r"[^\W_]+(?:[@.\-][^\W_]+)*", re.UNICODE)


def fingerprint(text: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{text.casefold()}".encode()).hexdigest()[:20]


def tracked(all_files: bool) -> list[Path]:
    if not all_files and (REPO / ".git").exists():
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=REPO, text=True,
                             capture_output=True, check=True).stdout
        return [REPO / p for p in out.split("\0") if p and (REPO / p).is_file()]
    skip = {".git", ".venv", "__pycache__", ".pytest_cache", "dist", "testdata"}
    return [p for p in REPO.rglob("*") if p.is_file() and not skip & set(p.relative_to(REPO).parts)]


def faces(path: Path) -> int:
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        return 0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    found = 0
    for model in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        det = cv2.CascadeClassifier(cv2.data.haarcascades + model)
        found += len(det.detectMultiScale(gray, 1.1, 6, minSize=(40, 40)))
    return found


def names_in(text: str, salt: str, names: set[str]) -> set[str]:
    words = WORD.findall(text)
    hits = set()
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            f = fingerprint(" ".join(words[i:i + n]), salt)
            if f in names:
                hits.add(" ".join(words[i:i + n]))
    return hits


def check_file(path: Path, rel: str, deny: dict) -> list[str]:
    out = []
    salt, names, audio = deny["salt"], set(deny["names"]), set(deny["files"])
    suffix = path.suffix.lower()
    for hit in names_in(rel, salt, names):
        out.append(f"{rel}: Dateiname enthält bekannten Namen „{hit}“")
    if suffix in MEDIA:
        if not any(fnmatch.fnmatch(rel, p) for p in ALLOWED_MEDIA):
            out.append(f"{rel}: Mediendatei außerhalb der erlaubten Orte")
        if hashlib.sha256(path.read_bytes()).hexdigest()[:32] in audio:
            out.append(f"{rel}: bekannte Referenzdatei, darf nie ins Repository")
        if suffix in IMAGES and (n := faces(path)):
            out.append(f"{rel}: {n} Gesicht(er) erkannt")
        return out
    if rel in SKIP_TEXT or path.stat().st_size > 5_000_000:
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return out
    for no, line in enumerate(text.splitlines(), 1):
        for label, rx in KEYS.items():
            if re.search(rx, line):
                out.append(f"{rel}:{no}: {label}")
        if m := re.search(PATHS, line):
            out.append(f"{rel}:{no}: persönlicher Pfad {m.group(0)}")
        for hit in names_in(line, salt, names):
            out.append(f"{rel}:{no}: bekannter Name „{hit}“")
    return out


def history(deny: dict) -> tuple[int, int, list[str]]:
    """What a public repository shows forever: every blob of every commit under every path it had, plus the commit messages."""
    import tempfile
    git = lambda *a: subprocess.run(["git", *a], cwd=REPO, capture_output=True, check=True).stdout
    commits = git("rev-list", "--all").decode().split()
    seen, problems = set(), []
    for c in commits:
        msg = git("log", "-1", "--format=%an%n%ae%n%B", c).decode("utf-8", "replace")
        for label, rx in KEYS.items():
            if re.search(rx, msg):
                problems.append(f"Commit {c[:8]}: {label} in der Nachricht")
        if m := re.search(PATHS, msg):
            problems.append(f"Commit {c[:8]}: persönlicher Pfad {m.group(0)}")
        for hit in names_in(msg, deny["salt"], set(deny["names"])):
            problems.append(f"Commit {c[:8]}: bekannter Name „{hit}“")
        for row in git("ls-tree", "-r", "-z", c).decode("utf-8", "surrogateescape").split("\0"):
            if not row:
                continue
            meta, path = row.split("\t", 1)
            _, kind, sha = meta.split()
            if kind == "blob":
                seen.add((path, sha))
    with tempfile.TemporaryDirectory() as tmp:
        for path, sha in sorted(seen):
            f = Path(tmp) / ("blob" + Path(path).suffix)
            f.write_bytes(git("cat-file", "blob", sha))
            problems += [f"{p} (Blob {sha[:8]})" for p in check_file(f, path, deny)]
    return len(commits), len(seen), sorted(set(problems))


def main(argv: list[str]) -> int:
    deny = json.loads(DENY.read_text(encoding="utf-8"))
    if "--history" in argv:
        n, blobs, problems = history(deny)
        for p in problems:
            print("✗", p)
        print(f"Prüfskript Historie: {n} Commits, {blobs} Dateiversionen, {len(problems)} Befund(e)")
        return 1 if problems else 0
    files = tracked("--all" in argv)
    problems = [p for f in files for p in check_file(f, f.relative_to(REPO).as_posix(), deny)]
    for p in problems:
        print("✗", p)
    print(f"Prüfskript: {len(files)} Dateien, {len(problems)} Befund(e)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
