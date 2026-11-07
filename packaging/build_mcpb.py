"""Build dist/schnippo-<version>.mcpb: copy the runtime files into packaging/build/schnippo, write the manifest,
run `mcpb validate` and `mcpb pack` (via npx @anthropic-ai/mcpb). No .venv, no tests, no testdata.

    uv run python packaging/build_mcpb.py
"""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging"
BUILD = PKG / "build" / "schnippo"
DIST = ROOT / "dist"
MCPB = ["npx", "-y", "@anthropic-ai/mcpb@2.1.2"]


def main() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    for f in ("pyproject.toml", "uv.lock", ".python-version", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / f, BUILD / f)
    shutil.copytree(ROOT / "src", BUILD / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(PKG / "bundle_main.py", BUILD / "bundle_main.py")
    sys.path.insert(0, str(ROOT / "src"))
    from schnippo import branding as b
    shutil.copy2(b.brand_file("icon.png", PKG / "icon.png"), BUILD / "icon.png")  # the placeholder until the logo is there
    shutil.copy2(PKG / "mcpbignore", BUILD / ".mcpbignore")
    text = (PKG / "manifest.template.json").read_text(encoding="utf-8")
    for key, value in {"__VERSION__": version, "__DISPLAY_NAME__": b.DISPLAY_NAME, "__TAGLINE__": b.TAGLINE, "__AUTHOR__": b.AUTHOR, "__AUTHOR_URL__": b.AUTHOR_URL, "__HOMEPAGE__": b.HOMEPAGE,
                       "__REPOSITORY__": b.REPOSITORY, "__DOCS_URL__": b.DOCS_URL, "__SUPPORT_URL__": b.SUPPORT_URL, "__PRIVACY_URL__": b.PRIVACY_URL}.items():
        text = text.replace(key, value)
    manifest = json.loads(text)
    (BUILD / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    leaked = [p for p in BUILD.rglob("*") if p.is_file() and "/Users/" in p.read_text(errors="ignore")]
    if leaked:
        sys.exit(f"Pfade aus der Entwicklungsumgebung im Paket: {[str(p.relative_to(BUILD)) for p in leaked]}")
    subprocess.run(MCPB + ["validate", str(BUILD / "manifest.json")], check=True)
    DIST.mkdir(exist_ok=True)
    out = DIST / f"schnippo-{version}.mcpb"
    subprocess.run(MCPB + ["pack", str(BUILD), str(out)], check=True)
    print(f"{out} · {out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
