"""Provider interface. Deliberately thin: one call in, normalised tokens out."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import RawTranscript


class TranscriptionError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def transcribe(self, wav: Path, language: str, raw_out: Path | None = None) -> RawTranscript:
        """Transcribe a 16 kHz mono WAV. If raw_out is given, store the provider's raw response there."""
        ...

    def option_fingerprint(self) -> str:
        """Short string identifying result-relevant options (part of the cache key)."""
        ...


def get_provider(name: str, cfg) -> Provider:
    if name == "gladia":
        from .gladia import GladiaProvider

        return GladiaProvider(cfg)
    raise TranscriptionError(f"unknown provider {name!r} (available: gladia)")


def option_fingerprint(name: str, cfg) -> str:
    """Cache-key part for the *current* settings, computable without an API key."""
    if name == "gladia":
        from .gladia import option_fingerprint as fp

        return fp(cfg)
    raise TranscriptionError(f"unknown provider {name!r}")
