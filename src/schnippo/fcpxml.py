"""Minimal FCPXML writer for a cut plan (one video+audio track of asset-clips, markers).

Used as fallback to give a timeline a frame rate different from the project's: Resolve takes the timeline
format from the file on import (verified empirically). All times are exact rationals of the
frame duration (fps_den/fps_num seconds), so 29.97 / 23.976 stay frame-exact.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr


def _t(frames: int, num: int, den: int) -> str:
    f = Fraction(frames * den, num)
    return f"{f.numerator}s" if f.denominator == 1 else f"{f.numerator}/{f.denominator}s"


def tc_start_frames(num: int, den: int) -> int:
    """01:00:00:00 in frames, counted like Resolve (nominal rate for NTSC: 108000 @ 29.97 NDF)."""
    return 3600 * round(num / den)


def write_fcpxml(path: Path, name: str, num: int, den: int, width: int, height: int, assets: dict,
                 pieces: list[tuple[str, int, int]], markers: list[tuple[int, str, str]] = (), version: str = "1.10",
                 captions: list[tuple[int, int, str]] = (), caption_lang: str = "de") -> Path:
    """assets: id -> {path, frames, tc_frames, name, audio_channels}; pieces: (asset id, start_frame, end_frame) in
    source frames; markers: (timeline frame offset from start, name, note)."""
    fmt = f"r_fmt"
    res = [f'<format id="{fmt}" frameDuration="{_t(1, num, den)}" width="{width}" height="{height}" '
           f'colorSpace="1-1-1 (Rec. 709)"/>']
    for aid, a in assets.items():
        url = "file://" + quote(str(Path(a["path"]).resolve()))
        res.append(f'<asset id="a_{aid}" name={quoteattr(a["name"])} start="{_t(a.get("tc_frames", 0), num, den)}" '
                   f'duration="{_t(a["frames"], num, den)}" hasVideo="1" hasAudio="1" format="{fmt}" audioSources="1" '
                   f'audioChannels="{a.get("audio_channels", 2)}" audioRate="48000">'
                   f'<media-rep kind="original-media" src={quoteattr(url)}/></asset>')
    tc0 = tc_start_frames(num, den)
    total = sum(e - s for _, s, e in pieces)
    spine, rec = [], 0
    mk = sorted(markers)
    caps = sorted(captions)
    for aid, s, e in pieces:
        a = assets[aid]
        src0 = a.get("tc_frames", 0) + s
        inner = []
        for off, mname, note in mk:
            if rec <= off < rec + (e - s):
                inner.append(f'<marker start="{_t(src0 + off - rec, num, den)}" duration="{_t(1, num, den)}" '
                             f'value={quoteattr(mname)} note={quoteattr(note)}/>')
        for c0, c1, text in caps:  # captions are connected to the spine clip in which they start
            if rec <= c0 < rec + (e - s):
                lines = "".join(f'<text-style ref="ts1">{escape(t)}</text-style>' + ("&#10;" if k + 1 < len(text.split(chr(10))) else "")
                                for k, t in enumerate(text.split("\n")))
                inner.append(f'<caption lane="1" offset="{_t(src0 + c0 - rec, num, den)}" duration="{_t(c1 - c0, num, den)}" '
                             f'role="iTT?captionFormat=ITT.{caption_lang}"><text placement="bottom">{lines}</text>'
                             f'<text-style-def id="ts1"><text-style font="Helvetica" fontSize="13" fontColor="1 1 1 1"/>'
                             f'</text-style-def></caption>')
        spine.append(f'<asset-clip ref="a_{aid}" name={quoteattr(a["name"])} offset="{_t(tc0 + rec, num, den)}" '
                     f'start="{_t(src0, num, den)}" duration="{_t(e - s, num, den)}" format="{fmt}" tcFormat="NDF">'
                     + "".join(inner) + "</asset-clip>")
        rec += e - s
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="{version}">\n'
           f'<resources>{"".join(res)}</resources>\n'
           f'<library><event name={quoteattr(escape(name))}><project name={quoteattr(name)}>'
           f'<sequence format="{fmt}" duration="{_t(total, num, den)}" tcStart="{_t(tc0, num, den)}" tcFormat="NDF" '
           f'audioLayout="stereo" audioRate="48k"><spine>\n' + "\n".join(spine) +
           '\n</spine></sequence></project></event></library>\n</fcpxml>\n')
    Path(path).write_text(xml, encoding="utf-8")
    return Path(path)
