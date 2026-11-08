"""API keys in the system's credential store (macOS keychain, Windows Credential Manager), through keyring, for hosts where the settings cannot ask for them. The key goes from a system
dialog straight into the store; it never passes through the chat or a log."""

from __future__ import annotations

from . import platforms
from .branding import SLUG

SERVICES = {"gladia": "Gladia", "freesound": "Freesound", "elevenlabs": "ElevenLabs"}


def read(account: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(SLUG, account) or None
    except Exception:  # no store on this machine, locked, or refused: same as no key
        return None


def ask(label: str, run=platforms.run) -> str | None:
    """Hidden input in a system dialog. None if cancelled."""
    if platforms.is_windows():
        script = (f"$c = Get-Credential -UserName '{label}' -Message '{label}-API-Key als Kennwort einfügen. Er wird in der Windows-Anmeldeinformationsverwaltung gespeichert.'; "
                  "if ($c) { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $c.GetNetworkCredential().Password }")
        r = run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=300)
    else:
        script = f'display dialog "{label}-API-Key einfügen. Er wird im Schlüsselbund gespeichert." default answer "" with hidden answer buttons {{"Abbrechen", "Speichern"}} default button "Speichern" with title "{SLUG.capitalize()}"\ntext returned of result'
        r = run(["osascript", "-e", script], capture_output=True, text=True, timeout=300)
    return (r.stdout or "").strip() or None if r.returncode == 0 else None


def write(account: str, key: str) -> bool:
    try:
        import keyring
        keyring.set_password(SLUG, account, key)
    except Exception:
        return False
    return True
