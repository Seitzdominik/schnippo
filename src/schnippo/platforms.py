"""What differs between macOS and Windows, in one place. Everything else in the package goes through here."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .branding import SLUG

LOCKED_WINERRORS = {5, 32, 33}  # access denied, sharing violation, lock violation
LONG_PATH = 240  # some Windows calls fail from 248 on, the documented limit is 260
_WIN_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class FileLocked(OSError):
    """A file another program holds open. The text is written for the user."""


def is_windows() -> bool:
    return sys.platform == "win32"


# ---------- folders ----------
def config_dir() -> Path:
    if is_windows():
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / SLUG
    return Path.home() / ".config" / SLUG


def cache_dir() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / SLUG / "Cache"
    return Path.home() / "Library" / "Caches" / SLUG


def font_dirs() -> list[Path]:
    if is_windows():
        return [Path(os.environ.get("WINDIR") or r"C:\Windows") / "Fonts", Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Microsoft" / "Windows" / "Fonts"]
    return [Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]


def ui_font(size: int):
    """A plain font for contact sheets; PIL's built-in one if the system has none."""
    from PIL import ImageFont
    name = str(font_dirs()[0] / "arial.ttf") if is_windows() else "/System/Library/Fonts/Supplemental/Arial.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


# ---------- DaVinci Resolve ----------
MAC_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
MAC_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
WIN_LIB_TAIL = Path("Blackmagic Design") / "DaVinci Resolve" / "fusionscript.dll"


def _registry_install_dirs() -> list[Path]:
    """InstallLocation of DaVinci Resolve from the uninstall entries, for installs outside the program folder."""
    try:
        import winreg
    except ImportError:
        return []
    found = []
    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                        if "DaVinci Resolve" in str(winreg.QueryValueEx(key, "DisplayName")[0]):
                            found.append(Path(winreg.QueryValueEx(key, "InstallLocation")[0]))
                except OSError:
                    continue
    except OSError:
        return []
    return found


def _windows_lib() -> str:
    default = Path(os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files") / WIN_LIB_TAIL
    candidates = [default] + [d / "fusionscript.dll" for d in _registry_install_dirs()]
    candidates += [Path(f"{letter}:\\Program Files") / WIN_LIB_TAIL for letter in "DEFG"]
    return str(next((c for c in candidates if c.exists()), default))


def resolve_paths() -> tuple[str, str]:
    """(folder of DaVinciResolveScript.py, fusionscript library). RESOLVE_SCRIPT_API and RESOLVE_SCRIPT_LIB win, as in the README that ships with Resolve."""
    api, lib = os.environ.get("RESOLVE_SCRIPT_API"), os.environ.get("RESOLVE_SCRIPT_LIB")
    if is_windows():
        data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        modules = str(Path(api) / "Modules") if api else str(Path(data) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting" / "Modules")
        return modules, lib or _windows_lib()
    return (str(Path(api) / "Modules") if api else MAC_MODULES), lib or MAC_LIB


def resolve_running() -> bool:
    import psutil
    wanted = {"resolve.exe"} if is_windows() else {"resolve"}
    try:
        return any((p.info.get("name") or "").lower() in wanted for p in psutil.process_iter(["name"]))
    except psutil.Error:
        return False


# ---------- processes ----------
def _long(arg):
    if isinstance(arg, str) and is_windows() and len(arg) >= LONG_PATH and _WIN_PATH.match(arg):
        return extended(arg)
    return arg


def _prepare(cmd, kw: dict) -> tuple[list, dict]:
    if is_windows():
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)  # every ffmpeg call would open a console when the server has none
        cmd = [_long(a) for a in cmd]
    if kw.get("text") and "encoding" not in kw:
        kw.update(encoding="utf-8", errors="replace")
    return cmd, kw


def run(cmd, **kw) -> subprocess.CompletedProcess:
    cmd, kw = _prepare(cmd, kw)
    return subprocess.run(cmd, **kw)


def popen(cmd, **kw) -> subprocess.Popen:
    cmd, kw = _prepare(cmd, kw)
    return subprocess.Popen(cmd, **kw)


def find_uv() -> str | None:
    home = Path.home()
    known = [home / ".local/bin/uv.exe", home / ".cargo/bin/uv.exe"] if is_windows() else [Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv"), home / ".local/bin/uv"]
    return os.environ.get("UV") or shutil.which("uv") or next((str(p) for p in known if p.exists()), None)


def tool_dirs() -> tuple[str, ...]:
    """Where to look when the host starts the server with a minimal PATH (Claude Desktop on macOS)."""
    return () if is_windows() else ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")


# ---------- paths ----------
def extended(path: str | Path) -> str:
    """Path text with the \\\\?\\ prefix Windows needs beyond 260 characters. Only for paths that long: Resolve and some tools do not take it."""
    text = os.path.normpath(str(path))
    if text.startswith("\\\\?\\"):
        return text
    return "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text


def plain(path: str | Path) -> str:
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    return text[4:] if text.startswith("\\\\?\\") else text


def fs(path: str | Path) -> Path:
    """The path to hand to a file operation."""
    return Path(extended(path)) if is_windows() and len(str(path)) >= LONG_PATH else Path(path)


def read_text(path: Path) -> str:
    """A text the user wrote: UTF-8 with or without the mark Notepad puts first, otherwise the old Windows encoding."""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def safe_filename(name: str) -> str:
    """A file name both systems accept."""
    out = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).rstrip(" .") or "export"
    return f"_{out}" if out.split(".")[0].lower() in RESERVED else out


def cloud_placeholder(path: Path) -> bool:
    """A file that exists only in the cloud (OneDrive and the like). Reading it would start a download or fail."""
    attrs = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attrs & (0x400000 | 0x40000 | 0x1000))  # RECALL_ON_DATA_ACCESS, RECALL_ON_OPEN, OFFLINE


# ---------- files other programs hold open ----------
def _locked(e: OSError) -> bool:
    return is_windows() and (isinstance(e, PermissionError) or getattr(e, "winerror", None) in LOCKED_WINERRORS)


def retry_locked(fn, what: str, tries: int = 6, wait: float = 0.5, sleep=time.sleep):
    """Windows refuses to replace or delete a file someone has open, often only for a moment."""
    for attempt in range(tries):
        try:
            return fn()
        except OSError as e:
            if not _locked(e):
                raise
            if attempt == tries - 1:
                raise FileLocked(f"{what} ist noch geöffnet. Bitte in DaVinci Resolve oder im Player schließen und erneut versuchen.") from e
            sleep(wait * (attempt + 1))


def replace(src: Path, dst: Path) -> None:
    retry_locked(lambda: os.replace(src, dst), f"„{Path(dst).name}“")


def unlink(path: Path) -> None:
    retry_locked(lambda: Path(path).unlink(missing_ok=True), f"„{Path(path).name}“")


def rmtree(path: Path) -> None:
    """Removes what it can; files still held open stay behind and are reported in the log only."""
    def go():
        shutil.rmtree(path)
    try:
        retry_locked(go, f"Ordner „{Path(path).name}“")
    except (FileLocked, FileNotFoundError):
        shutil.rmtree(path, ignore_errors=True)


def copy(src: Path, dst: Path) -> None:
    retry_locked(lambda: shutil.copy2(src, dst), f"„{Path(dst).name}“")


# ---------- text for the user ----------
def key_store() -> str:
    return "Anmeldeinformationsverwaltung" if is_windows() else "Schlüsselbund"


def key_store_place() -> str:
    return "der Anmeldeinformationsverwaltung" if is_windows() else "den Schlüsselbund"


def how_to_copy_path() -> str:
    if is_windows():
        return "Pfad kopieren unter Windows: Im Explorer Umschalt gedrückt halten, Rechtsklick auf den Ordner, „Als Pfad kopieren“."
    return "Pfad kopieren am Mac: Rechtsklick auf den Ordner, Wahltaste (⌥) halten, „… als Pfadname kopieren“ (oder ⌥⌘C im Finder)."


def find_folder_hint() -> str:
    return "Shift + Rechtsklick im Explorer → „Als Pfad kopieren“" if is_windows() else "Rechtsklick im Finder → „Kopieren als Pfadname“"


def resolve_scripting_steps() -> str:
    if is_windows():
        return "In Resolve: DaVinci Resolve → Preferences → System → General → „External scripting using“ auf „Local“ stellen"
    return "In Resolve: DaVinci Resolve → Einstellungen → System → Allgemein → „External scripting using“ auf „Local“ stellen"


def install_ffmpeg_hint() -> str:
    return "Die Erweiterung neu installieren (ffmpeg ist eigentlich enthalten)." if is_windows() else "Die Erweiterung neu installieren (ffmpeg ist eigentlich enthalten) oder ffmpeg installieren (brew install ffmpeg)."
