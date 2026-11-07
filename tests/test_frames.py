import io
import subprocess

import pytest
from PIL import Image

from schnippo import frames as fr
from schnippo import workspace as wsmod
from schnippo.workspace import Workspace

from conftest import make_raw


class FakeProvider:
    name = "gladia"

    def __init__(self, cfg): pass
    def option_fingerprint(self): return "fake"

    def transcribe(self, wav, language, raw_out=None):
        return make_raw([("Eins", 0.2, 0.5), ("zwei.", 0.6, 0.9), ("Drei", 1.8, 2.1), ("vier.", 2.2, 2.6)])


@pytest.fixture
def ws(cfg, tmp_path, monkeypatch):
    folder = tmp_path / "f"
    folder.mkdir()
    # portrait clip with frame counter: rotation via metadata is covered by ffprobe tests; here plain 180x320
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=25:d=3", "-f", "lavfi",
                    "-i", "sine=f=300:d=3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(folder / "take.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=600x400", "-frames:v", "1",
                    str(folder / "b.jpg")], check=True)
    monkeypatch.setattr(wsmod, "get_provider", lambda name, c: FakeProvider(c))
    w = Workspace(cfg)
    w.ingest(folder)
    w.transcribe("all")
    return w


def test_frame_ids():
    assert fr.frame_id("c01", 7) == "c01:f0007" and fr.parse_frame_id("c01:f0123") == ("c01", 123)
    with pytest.raises(ValueError):
        fr.parse_frame_id("f12")
    assert fr.image_tokens(840, 1022) == 1145 and fr.image_tokens(3000, 3000) == fr.image_tokens(1568, 1568)


def test_segment_strip_portrait_tiles_and_ids(ws):
    text, jpgs = ws.get_frames("c01", "segment_strip")
    assert len(jpgs) == 1
    im = Image.open(io.BytesIO(jpgs[0]))
    tile_w, tile_h = im.width / 6, im.height - 22  # one row of 6 tiles under a 22 px header
    assert max(im.size) <= 1024 and tile_h > tile_w * 1.5  # portrait material → portrait tiles
    assert "c01:s001 w0001–w0002: c01:f0005 c01:f0013 c01:f0022" in text and "Bild-Token" in text
    assert (ws.cache.media_dir(ws.clip("c01").fingerprint) / "frames" / "f000005.jpg").exists()


def test_interval_wordrange_and_paging(ws):
    text, jpgs = ws.get_frames("c01:w0001-w0004", "interval", interval_s=0.04, max_images=1)
    assert "von 4" in text and "page=2" in text and len(jpgs) == 1
    text2, _ = ws.get_frames("c01:w0001-w0004", "interval", interval_s=0.04, page=4)
    assert "Abzug 4–4 von 4" in text2 and "page=" not in text2


def test_stills_overview_and_bad_targets(ws):
    text, jpgs = ws.get_frames("stills")
    assert "i01 b.jpg 600x400 3:2 Quer" in text and len(jpgs) == 1
    with pytest.raises(KeyError):
        ws.get_frames("i09")
    with pytest.raises(ValueError):
        ws.get_frames("c01:x12")


def test_motion_energy_shape(ws):
    m = ws.motion(ws.clip("c01"))
    assert len(m) == 75 and m[0] == 0 and float(m[1:].mean()) > 0  # testsrc2 moves every frame


def test_preview_cuts_pairs(ws):
    from schnippo.cutlist import Cutlist
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0002"},
                        {"clip": "c01", "from_word": "w0003", "to_word": "w0004"}])
    text, jpgs = ws.preview_cuts(cl, top_n=0)
    assert "3 von 3 Schnitten" in text and "S01 #01→#02" in text and len(jpgs) == 1
    assert max(Image.open(io.BytesIO(jpgs[0])).size) <= 1024


def test_take_frames_by_segment_list_and_unknown_group(ws):
    text, jpgs = ws.take_frames("c01:s001,s002")
    assert "eine Zeile pro Versuch" in text and "c01:s002" in text and len(jpgs) == 1
    with pytest.raises(KeyError):
        ws.take_frames("c01:G07")


def test_short_face_dropouts_are_bridged():
    import numpy as np

    from schnippo.frames import bridge_face_gaps, cut_motion
    face = np.array([1, 1, 0, 0, 1, 1] + [0] * 20 + [1, 1], bool)
    b = bridge_face_gaps(face, max_gap=12)
    assert b[2] and b[3] and not b[10]  # 2-frame dropout bridged, 20-frame absence stays
    boxes = np.where(face[:, None], 10, -1).repeat(4, axis=1)
    m = cut_motion({"boxes": boxes, "person": np.ones(len(face), np.float32), "global": np.ones(len(face), np.float32)})
    assert m[2] == 1.0 and m[10] >= 40
