"""API keys in the macOS keychain, for hosts where the settings cannot ask for them. The key goes from a system dialog straight into the keychain; it never passes through the chat or a command line."""

from __future__ import annotations

import subprocess
import sys

from .branding import SLUG

SERVICES = {"gladia": "Gladia", "freesound": "Freesound", "elevenlabs": "ElevenLabs"}


def read(account: str, run=subprocess.run) -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        r = run(["security", "find-generic-password", "-s", SLUG, "-a", account, "-w"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (r.stdout or "").strip() or None if r.returncode == 0 else None


def ask(label: str, run=subprocess.run) -> str | None:
    """Hidden input in a system dialog. None if cancelled."""
    script = f'display dialog "{label}-API-Key einfügen. Er wird im Schlüsselbund gespeichert." default answer "" with hidden answer buttons {{"Abbrechen", "Speichern"}} default button "Speichern" with title "{SLUG.capitalize()}"\ntext returned of result'
    r = run(["osascript", "-e", script], capture_output=True, text=True, timeout=300)
    return (r.stdout or "").strip() or None if r.returncode == 0 else None


def write(account: str, key: str, run=subprocess.run) -> bool:
    """Through security's own command prompt: an argument would show up in the process list."""
    if any(c in key for c in '"\\\n'):
        return False
    line = f'add-generic-password -U -s {SLUG} -a {account} -w "{key}"\n'
    return run(["security", "-i"], input=line, capture_output=True, text=True, timeout=10).returncode == 0
