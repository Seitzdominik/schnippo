import subprocess

import pytest

from schnippo.render import RenderError, render_timeline


class FakeProject:
    """StartRendering refuses twice (as right after a build); the first job renders audio only (stuck state)."""

    def __init__(self, out, stuck=True):
        self.out, self.stuck, self.jobs, self.starts, self.settings = out, stuck, {}, 0, {}
        self.toggled = False

    def SetCurrentTimeline(self, tl): return True
    def IsRenderingInProgress(self): return False
    def SetCurrentRenderFormatAndCodec(self, f, c): return True

    def SetRenderSettings(self, d):
        if d.get("ExportVideo") and d.get("ExportAudio") is False:
            self.toggled = True
        self.settings.update(d)
        return True

    def AddRenderJob(self):
        j = f"job{len(self.jobs)}"
        self.jobs[j] = dict(self.settings)
        return j

    def StartRendering(self, jobs):
        self.starts += 1
        if self.starts <= 2:
            return False
        s = self.jobs[jobs[0]]
        video = s["ExportVideo"] and (self.toggled or not self.stuck)
        assert s["ExportVideo"], "audio-only renders are never started by Resolve – always render video too"
        f = f"{s['TargetDir']}/{s['CustomName']}.mov"
        cmd = ["ffmpeg", "-y", "-v", "error"]
        cmd += ["-f", "lavfi", "-i", "color=s=64x64:d=0.2"] if video else []
        cmd += ["-f", "lavfi", "-i", "sine=d=0.2", "-c:a", "pcm_s16le"] + (["-c:v", "mpeg4"] if video else []) + [f]
        subprocess.run(cmd, check=True)
        self.jobs[jobs[0]]["done"] = True
        return True

    def GetRenderJobStatus(self, j): return {"JobStatus": "Complete" if self.jobs[j].get("done") else "Ready"}
    def DeleteRenderJob(self, j): return True


def test_render_retries_start_and_unsticks_video(tmp_path):
    p = FakeProject(tmp_path)
    f = render_timeline(p, object(), tmp_path, "chk", sleep=lambda s: None)
    assert f.exists() and p.toggled and p.starts == 3 and p.jobs["job0"]["TargetDir"] == str(tmp_path.resolve())


def test_render_reports_missing_stream(tmp_path, monkeypatch):
    p = FakeProject(tmp_path)
    monkeypatch.setattr(p, "SetRenderSettings", lambda d: p.settings.update(d) or True)  # toggle not honoured
    with pytest.raises(RenderError, match="erwartet \\['video', 'audio'\\]"):
        render_timeline(p, object(), tmp_path, "chk", sleep=lambda s: None)
