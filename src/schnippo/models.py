"""Core data model (pydantic).

Word IDs are the *only* way Claude references material. IDs are assigned to ASR tokens
(kind word|filler) only, so changing analysis parameters (pause threshold, filler list)
never renumbers words. Gap entries (pauses, unrecognised speech) carry IDs derived from
the preceding ASR word: ``p0005`` = pause after w0005, ``u0005`` = speech without a word
after w0005 (``p0000``/``u0000`` = before the first word).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, Field, computed_field

WordKind = Literal["word", "filler", "pause", "breath"]


class Clip(BaseModel):
    id: str  # c01, c02, ...
    path: str
    fingerprint: str
    duration_s: float
    fps_num: int
    fps_den: int
    avg_fps: float | None = None
    vfr: bool = False
    vfr_detail: str | None = None
    width: int | None = None
    height: int | None = None
    rotation: int = 0
    video_codec: str | None = None
    audio_channels: int = 0
    audio_sample_rate: int | None = None
    start_tc: str | None = None
    start_time_s: float = 0.0
    nb_frames: int | None = None
    # Filled when the clip is imported into Resolve. Phase 0 showed that Resolve, not ffprobe,
    # defines the frame grid (e.g. VFR clips are conformed to Resolve's FPS by timestamp).
    resolve_fps: float | None = None
    resolve_frames: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den

    def fps_fraction(self) -> Fraction:
        return Fraction(self.fps_num, self.fps_den)

    @property
    def name(self) -> str:
        from pathlib import Path

        return Path(self.path).name


class Still(BaseModel):
    """A still image found next to the takes (later: B-roll/inserts). Never transcribed."""

    id: str  # i01, i02, ... (s### are segments)
    path: str
    fingerprint: str
    width: int
    height: int
    rotation: int = 0  # EXIF orientation as rotation in degrees
    codec: str | None = None

    @property
    def name(self) -> str:
        from pathlib import Path

        return Path(self.path).name

    def display_size(self) -> tuple[int, int]:
        return (self.height, self.width) if abs(self.rotation) % 180 == 90 else (self.width, self.height)

    def aspect(self) -> str:
        from fractions import Fraction

        w, h = self.display_size()
        r = Fraction(w, h)
        for label, (a, b) in {"1:1": (1, 1), "3:2": (3, 2), "2:3": (2, 3), "4:3": (4, 3), "3:4": (3, 4), "16:9": (16, 9),
                              "9:16": (9, 16), "5:4": (5, 4), "4:5": (4, 5), "21:9": (21, 9)}.items():
            if abs(float(r) - a / b) < 0.01:
                return label
        return f"{float(r):.3f}:1"


class Word(BaseModel):
    id: str  # w0001 (ASR token) | p0005 (pause) | u0005 (voiced sound w/o word) | b0005 (breath)
    text: str
    start_s: float
    end_s: float
    confidence: float | None = None
    kind: WordKind = "word"
    flags: list[str] = Field(default_factory=list)
    speaker: int | None = None  # diarization (0, 1, …) – shown as S1, S2


class Finding(BaseModel):
    """A structured analysis hint. Never a deletion decision."""

    type: Literal["repeat", "restart_candidate", "unrecognized_speech", "long_pause"]
    first: tuple[str, str]  # (from_id, to_id) of the earlier occurrence / the flagged span
    second: tuple[str, str] | None = None  # the later occurrence it repeats
    note: str = ""


class RawTranscript(BaseModel):
    """Provider output normalised to plain ASR tokens (no analysis applied)."""

    provider: str
    language: str
    tokens: list[Word]  # kind == "word" for all, ids assigned
    audio_duration_s: float | None = None
    billing_s: float | None = None
    processing_s: float | None = None
    provider_job_id: str | None = None
    options: dict = Field(default_factory=dict)


class AnalyzedTranscript(BaseModel):
    clip_id: str
    provider: str
    language: str
    entries: list[Word]  # ASR tokens + gap entries, in time order
    findings: list[Finding] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
