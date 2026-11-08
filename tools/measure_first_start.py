"""What happens the first time Claude Desktop starts the extension: a fresh uv cache and a fresh Python, the same command the manifest runs.

    uv run python tools/measure_first_start.py dist/schnippo-*.mcpb

Prints a table and writes first_start.json: time to the first MCP answer, the same with a warm cache, download and installed size per package."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def wheel_sizes(lock: Path, tag: str) -> dict[str, tuple[str, int]]:
    """Name → (version, download bytes) of the wheel for this platform, read from uv.lock."""
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    out = {}
    for pkg in data["package"]:
        wheels = [w for w in pkg.get("wheels", []) if re.search(tag, w["url"]) or "none-any" in w["url"]]
        if wheels:
            best = next((w for w in wheels if "none-any" not in w["url"] and "cp314" in w["url"]), None) or next((w for w in wheels if "none-any" not in w["url"]), wheels[0])
            out[pkg["name"]] = (pkg["version"], best.get("size", 0))
    return out


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


async def handshake(folder: Path, env: dict, timeout: float = 900.0) -> tuple[float, int]:
    params = StdioServerParameters(command="uv", args=["run", "--directory", str(folder), "--frozen", "--no-dev", "bundle_main.py"], env=env)
    t = time.perf_counter()
    async with asyncio.timeout(timeout):
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                return time.perf_counter() - t, len(tools.tools)


def main(bundle: str) -> None:
    tag = "win_amd64" if sys.platform == "win32" else "macosx.*arm64" if sys.platform == "darwin" else "manylinux.*x86_64"
    root = Path(tempfile.mkdtemp(prefix="firststart_"))
    folder = root / "bundle"
    with zipfile.ZipFile(bundle) as z:
        z.extractall(folder)
    env = {**os.environ, "UV_CACHE_DIR": str(root / "uv-cache"), "UV_PYTHON_INSTALL_DIR": str(root / "uv-python"), "SCHNIPPO_UPDATE_CHECK": "0", "SCHNIPPO_NO_MIGRATE": "1", "SCHNIPPO_CONFIG": str(root / "c" / "config.toml"), "SCHNIPPO_CACHE": str(root / "cache"), "PYTHONUTF8": "1"}
    env.pop("GLADIA_API_KEY", None)
    cold, tools = asyncio.run(handshake(folder, env))
    warm, _ = asyncio.run(handshake(folder, env))
    venv = folder / ".venv"
    site = next(venv.rglob("site-packages"))
    rows = []
    known = wheel_sizes(folder / "uv.lock", tag)
    for d in sorted(site.glob("*.dist-info")):
        meta = (d / "METADATA").read_text(encoding="utf-8", errors="ignore")
        name = re.search(r"^Name: (.+)$", meta, re.M).group(1).strip().lower().replace("_", "-")
        total = 0
        for line in (d / "RECORD").read_text(encoding="utf-8", errors="ignore").splitlines():
            f = site / line.split(",")[0]
            if f.is_file():
                total += f.stat().st_size
        rows.append({"package": name, "download_mb": round(known.get(name, ("", 0))[1] / 1e6, 1), "installed_mb": round(total / 1e6, 1)})
    rows.sort(key=lambda r: -r["download_mb"])
    py = dir_size(root / "uv-python") if (root / "uv-python").exists() else 0
    # first use of ffmpeg: the wheel unpacks an archive
    t = time.perf_counter()
    r = subprocess.run([str(next(venv.rglob("python*")) if sys.platform != "win32" else venv / "Scripts" / "python.exe"), "-c", "import schnippo.ffmpeg_dist as f; print(f.path('ffmpeg'))"], env=env, capture_output=True, text=True, cwd=folder)
    unpack = time.perf_counter() - t
    defender = ""
    if sys.platform == "win32":
        ps = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-MpComputerStatus).RealTimeProtectionEnabled"], capture_output=True, text=True)
        defender = ps.stdout.strip()
    res = {"platform": sys.platform, "cold_start_s": round(cold, 1), "warm_start_s": round(warm, 1), "tools": tools, "bundle_mb": round(Path(bundle).stat().st_size / 1e6, 1), "python_install_mb": round(py / 1e6, 1),
           "venv_mb": round(dir_size(venv) / 1e6, 1), "ffmpeg_first_use_s": round(unpack, 1), "ffmpeg_ok": r.returncode == 0, "defender_realtime": defender, "packages": rows}
    Path("first_start.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "packages"}, indent=2))
    print(f"{'Paket':34} Download  installiert (MB)")
    for row in rows[:16]:
        print(f"{row['package']:34} {row['download_mb']:8} {row['installed_mb']:8}")
    print(f"gesamt {sum(x['download_mb'] for x in rows):.0f} MB Download, {sum(x['installed_mb'] for x in rows):.0f} MB installiert")
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1])
