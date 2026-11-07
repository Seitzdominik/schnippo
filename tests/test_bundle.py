import json
from pathlib import Path

from schnippo import config as cfgmod
from schnippo import media

ROOT = Path(__file__).resolve().parents[1]


def test_bundle_env_values(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHNIPPO_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setenv("GLADIA_API_KEY", "abc")
    monkeypatch.setenv("SCHNIPPO_FORMAT", "YouTube")
    monkeypatch.setenv("SCHNIPPO_LANGUAGE", "en")
    monkeypatch.setenv("SCHNIPPO_EXPORT_FOLDER", "${user_config.export_folder}")  # unset optional field
    c = cfgmod.load_config()
    assert c.gladia_api_key == "abc" and c.format == "youtube" and c.language == "en" and c.export_folder is None
    monkeypatch.setenv("GLADIA_API_KEY", "")
    assert cfgmod.load_config().gladia_api_key is None
    assert "abc" not in repr(c)


def test_ffmpeg_lookup_order(monkeypatch):
    media.find_tool.cache_clear()
    monkeypatch.setattr(media, "_bundled", lambda n: f"/bundle/{n}")
    monkeypatch.setattr(media.shutil, "which", lambda n: None)
    monkeypatch.setattr(media, "SYSTEM_DIRS", ())
    assert media.find_tool("ffprobe") == ("/bundle/ffprobe", "mitgeliefert")
    media.find_tool.cache_clear()
    monkeypatch.setattr(media.shutil, "which", lambda n: f"/usr/local/bin/{n}")
    assert media.find_tool("ffmpeg") == ("/usr/local/bin/ffmpeg", "System")
    media.find_tool.cache_clear()
    monkeypatch.setenv("SCHNIPPO_FFMPEG", "bundled")
    assert media.find_tool("ffmpeg")[1] == "mitgeliefert"
    media.find_tool.cache_clear()


def test_manifest_template_matches_server_entry():
    m = json.loads((ROOT / "packaging/manifest.template.json").read_text())
    assert m["manifest_version"] == "0.4" and m["server"]["type"] == "uv"
    assert m["server"]["entry_point"] in m["server"]["mcp_config"]["args"]
    env = m["server"]["mcp_config"]["env"]
    assert set(env) == {"GLADIA_API_KEY", "SCHNIPPO_LANGUAGE", "SCHNIPPO_FORMAT", "SCHNIPPO_EXPORT_FOLDER", "SCHNIPPO_SFX_MODE",
                        "SCHNIPPO_SFX_FOLDER", "FREESOUND_API_KEY", "ELEVENLABS_API_KEY", "SCHNIPPO_PROJECTS_FOLDER", "SCHNIPPO_UPDATE_CHECK"}
    assert m["user_config"]["gladia_api_key"]["sensitive"] is True
    assert m["user_config"]["language"]["default"] == "de" and m["user_config"]["format"]["default"] == "auto"
    assert (ROOT / "packaging" / m["icon"]).exists()
