import asyncio
import json
import subprocess
from types import SimpleNamespace as NS

import httpx

from schnippo import keychain, prefs, updates
from schnippo.config import Config


def test_every_tool_has_title_and_hints():
    from schnippo import server
    tools = asyncio.run(server.mcp.list_tools())
    tools = tools if isinstance(tools, list) else tools.tools
    assert len(tools) >= 50
    for t in tools:
        a = t.annotations
        assert t.title and a and a.read_only_hint is not None and a.destructive_hint is not None, t.name
        assert not (a.read_only_hint and a.destructive_hint), t.name
        assert len(t.name) <= 64


def test_writing_tools_are_not_read_only():
    from schnippo.toolinfo import TOOLS
    for name in ("build_timeline", "revise", "export_reels", "clear_cache", "create_project", "store_api_key"):
        assert "d" in TOOLS[name][1]


def test_settings_typos_become_notes():
    c = Config()
    c.format, c.sfx_mode, c.language = "Reels", "subtill", "deutsch!"
    prefs.normalize(c)
    assert c.format == "reel" and c.sfx_mode == "subtil" and c.language == "de"
    assert len(c.setting_problems) == 2 and "off, subtil, normal" in c.setting_problems[0]


def test_friendly_settings_values_pass():
    c = Config()
    c.format, c.sfx_mode, c.language = "Interviews", "aus", "English"
    prefs.normalize(c)
    assert (c.format, c.sfx_mode, c.language, c.setting_problems) == ("youtube", "off", "en", [])


def _gh(version, seen=None):
    def handler(req):
        (seen if seen is not None else []).append(str(req.url))
        return httpx.Response(200, json={"tag_name": f"v{version}", "html_url": "https://example.org/r", "body": "Einleitung\n- Neu: Reels\n- Besser: Ton\n"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_update_found_with_notes(tmp_path):
    info = updates.check("0.11.0", tmp_path / "u.json", client=_gh("0.12.1"), now=1000.0)
    assert info == {"version": "0.12.1", "url": "https://example.org/r", "notes": ["Neu: Reels", "Besser: Ton"]}
    assert "0.12.1" in updates.text(info)


def test_same_version_says_nothing(tmp_path):
    assert updates.check("0.11.0", tmp_path / "u.json", client=_gh("0.11.0"), now=1000.0) is None


def test_asks_once_a_day_and_tells_once_per_version(tmp_path):
    f, seen = tmp_path / "u.json", []
    assert updates.check("0.11.0", f, client=_gh("0.12.0", seen), now=1000.0)
    updates.told(f, "0.12.0")
    assert updates.check("0.11.0", f, client=_gh("0.12.0", seen), now=2000.0) is None
    assert len(seen) == 1
    assert updates.check("0.11.0", f, force=True, client=_gh("0.12.0", seen), now=2000.0)
    assert len(seen) == 2


def test_network_trouble_stays_silent(tmp_path):
    def boom(req):
        raise httpx.ConnectError("x")
    assert updates.check("0.11.0", tmp_path / "u.json", client=httpx.Client(transport=httpx.MockTransport(boom))) is None
    gone = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert updates.check("0.11.0", tmp_path / "u.json", client=gone) is None


def test_keychain_key_never_on_the_command_line():
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return NS(returncode=0, stdout="")
    assert keychain.write("gladia", "geheim123", run=run)
    assert "geheim123" not in " ".join(calls[0][0]) and "geheim123" in calls[0][1]["input"]
    assert not keychain.write("gladia", 'a"b', run=run)


def test_keychain_read_and_cancelled_dialog(monkeypatch):
    monkeypatch.setattr(keychain.sys, "platform", "darwin")
    assert keychain.read("gladia", run=lambda *a, **k: NS(returncode=0, stdout="abc\n")) == "abc"
    assert keychain.read("gladia", run=lambda *a, **k: NS(returncode=44, stdout="")) is None
    assert keychain.ask("Gladia", run=lambda *a, **k: NS(returncode=1, stdout="")) is None


def test_manifest_has_author_homepage_privacy():
    from pathlib import Path
    t = (Path(__file__).parents[1] / "packaging" / "manifest.template.json").read_text(encoding="utf-8")
    m = json.loads(t)
    assert m["author"]["name"] == "__AUTHOR__" and m["homepage"] == "__HOMEPAGE__" and "__PRIVACY_URL__" in m["privacy_policies"]
