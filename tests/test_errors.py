import errno

from schnippo.errors import plain
from schnippo.media import MediaError
from schnippo.render import RenderError
from schnippo.transcribe.base import TranscriptionError


def test_plain_errors_name_the_next_step():
    assert "Platz schaffen" in plain(OSError(errno.ENOSPC, "No space left on device"))
    assert "Festplattenvollzugriff" in plain(PermissionError(errno.EACCES, "denied", "/Volumes/X/take.mov"))
    assert "API-Key" in plain(TranscriptionError("Gladia POST /upload -> HTTP 401: invalid key"))
    assert "warten" in plain(TranscriptionError("Gladia GET /pre-recorded/x -> HTTP 429: slow down"))
    assert "Internetverbindung" in plain(TranscriptionError("Gladia nicht erreichbar: ConnectError"))
    assert "resume_job" in plain(RenderError("StartRendering startet nicht"))
    assert "QuickTime" in plain(MediaError("ffprobe failed: moov atom not found"))
    assert plain(ValueError("Cutlist ungültig")) is None  # readable own messages stay
