"""What the directory checks in plugin/, kept true by tests. Rules and sources: docs/EINREICHUNG.md."""
import asyncio
import inspect
import json
import re
import tomllib
from pathlib import Path

from schnippo.toolinfo import TOOLS

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
READ_ONLY = {
    "analyze_audio", "check_setup", "design_preview", "detect_format", "find_reel_candidates", "get_edit_context", "get_frames", "get_take_frames", "get_transcript", "list_clips",
    "list_sfx", "list_versions", "locate", "merge_cutlists", "preview_cuts", "preview_graphic", "reel_cutlist", "resolve_status", "setup_design", "suggest_corrections", "validate_cutlist",
}
CHANGES_RESOLVE_OR_FILES = {
    "add_graphics", "add_overlays", "add_sfx", "apply_zooms", "build_timeline", "clear_cache", "complete_cut", "create_project", "export_final", "export_reels", "export_transcript",
    "master_audio", "prepare_recordings", "restore_version", "resume_job", "revise", "save_brand", "set_glossary", "store_api_key",
}
DISPLAY_ONLY_HOSTS = {"sdv.design", "schnippo.com", "creativecommons.org"}


def _manifest():
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))


def _server():
    return json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["schnippo"]


def _readme():
    return (PLUGIN / "README.md").read_text(encoding="utf-8")


def test_every_registered_tool_is_classified_once():
    from schnippo import server
    tools = asyncio.run(server.mcp.list_tools())
    tools = tools if isinstance(tools, list) else tools.tools
    assert {t.name for t in tools} == set(TOOLS)
    for name, (title, kind) in TOOLS.items():
        assert title and sum(c in kind for c in "rwd") == 1, name


def test_a_new_read_only_tool_is_a_conscious_decision():
    assert {name for name, (_, kind) in TOOLS.items() if "r" in kind} == READ_ONLY


def test_tools_that_change_resolve_or_files_are_destructive():
    assert CHANGES_RESOLVE_OR_FILES <= {name for name, (_, kind) in TOOLS.items() if "d" in kind}


def test_deleting_the_cache_needs_confirmation():
    from schnippo import server
    target = getattr(server.clear_cache, "__wrapped__", server.clear_cache)
    assert inspect.signature(target).parameters["confirm"].default is False


def test_only_the_manifest_lives_in_claude_plugin():
    assert [p.name for p in (PLUGIN / ".claude-plugin").iterdir()] == ["plugin.json"]


def test_directory_file_rules():
    files = [p for p in PLUGIN.rglob("*") if p.is_file()]
    assert len(files) <= 512
    for p in files:
        assert p.name not in {".DS_Store", "Thumbs.db", "desktop.ini"}, p
        assert not p.is_symlink(), p
        if p.suffix.lower() not in IMAGES:
            assert p.stat().st_size < 256 * 1024, p
            p.read_text(encoding="utf-8")


def test_package_is_pinned_to_this_release():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    server = _server()
    assert server["command"] == "uvx" and server["args"] == [f"schnippo=={version}"]
    assert _manifest()["version"] == version
    assert not list(PLUGIN.rglob("uv.toml")) and not list(PLUGIN.rglob(".npmrc"))


def test_cowork_can_load_the_server():
    """Cowork does not prompt and ignores a server when a referenced option has no default."""
    options = _manifest()["userConfig"]
    used = re.findall(r"\$\{user_config\.(\w+)\}", json.dumps(_server()))
    assert used
    for key in used:
        assert "default" in options[key], key


def test_keys_are_asked_for_and_marked_sensitive():
    assert _manifest()["userConfig"]["gladia_api_key"]["sensitive"] is True
    assert re.search(r"\bGLADIA_API_KEY\b", _readme()) is None


def test_own_sound_folder_can_be_set_in_the_plugin():
    assert _server()["env"]["SCHNIPPO_SFX_FOLDER"] == "${user_config.sfx_folder}"
    assert _manifest()["userConfig"]["sfx_folder"]["type"] == "directory"


def test_no_generated_audio_and_no_sound_services():
    """Policy 4.B. Only the source of the shipped CC0 recordings may name Freesound: data/sfx, THIRD_PARTY_NOTICES."""
    gone = re.compile(r"elevenlabs|freesound|generate_sfx|fetch_sfx|find_sfx", re.I)
    files = [*(ROOT / "src" / "schnippo").rglob("*.py"), ROOT / "packaging" / "manifest.template.json", *(p for p in PLUGIN.rglob("*") if p.is_file() and p.suffix.lower() not in IMAGES)]
    assert not [p for p in files if gone.search(p.read_text(encoding="utf-8"))]


def test_listing_texts_are_english():
    manifest = _manifest()
    assert manifest["description"].startswith("AI rough cuts for DaVinci Resolve")
    german = re.compile(r"\b(für|oder|und|Ordner|Schnitt)\b")
    for key, option in manifest["userConfig"].items():
        assert not german.search(option["title"] + " " + option["description"]), key
    assert "rough-cut" in [p.name for p in (PLUGIN / "skills").iterdir()]


def test_readme_meets_the_listing_rules():
    text = _readme()
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    assert len(prose.split()) >= 40
    assert "## Privacy Policy" in text and "https://schnippo.com/en/privacy/" in text and "https://schnippo.com/datenschutz/" in text
    prompts = re.findall(r"^\d+\. \"", text, flags=re.M)
    assert len(prompts) >= 3


def test_first_start_note_is_at_the_top():
    head = _readme().split("## English summary")[0]
    assert '"Failed to connect", click "Reconnect" once' in head and "„Failed to connect“" in head


def test_start_stays_lean():
    """uvx installs all of this before the server can answer, and Claude Code gives up after 30 s."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = " ".join(project["dependencies"])
    assert "[" not in deps and not re.search(r"opencv|ffmpeg|playwright", deps)
    for p in (ROOT / "src" / "schnippo").rglob("*.py"):
        assert not re.search(r"^\s*(from|import) (typer|rich|dotenv)\b", p.read_text(encoding="utf-8"), flags=re.M), p


def test_readme_names_every_network_destination():
    hosts = set()
    for p in (ROOT / "src" / "schnippo").rglob("*.py"):
        hosts |= set(re.findall(r"https?://([a-zA-Z0-9.-]+\.[a-z]{2,})", p.read_text(encoding="utf-8")))
    hosts = {h for h in hosts if not h.endswith(("example.org", "example.com", "w3.org")) and h not in DISPLAY_ONLY_HOSTS}
    assert hosts
    text = _readme()
    assert not [h for h in hosts if h not in text]
