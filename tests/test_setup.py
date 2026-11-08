from pathlib import Path

import pytest

from schnippo import setup_check
from schnippo import resolve_bridge


class FakeProject:
    def __init__(self, name="Testprojekt"): self.name = name
    def GetName(self): return self.name


class FakePM:
    def __init__(self, project): self.p = project
    def GetCurrentProject(self): return self.p


class FakeResolve:
    def __init__(self, product="DaVinci Resolve Studio", version=(21, 1, 2, 10, ""), project=FakeProject()):
        self.product, self.version, self.project = product, version, project
    def GetProductName(self): return self.product
    def GetVersion(self): return list(self.version)
    def GetVersionString(self): return ".".join(str(x) for x in self.version[:4])
    def GetProjectManager(self): return FakePM(self.project)


class Bridge:
    def __init__(self, r): self.r = r
    def resolve(self):
        if self.r is None:
            raise resolve_bridge.ResolveUnavailable("no")
        return self.r


@pytest.fixture
def installed(monkeypatch, tmp_path):
    lib, mod = tmp_path / "fusionscript.so", tmp_path / "Modules"
    lib.write_text("x")
    mod.mkdir()
    monkeypatch.setattr(resolve_bridge, "LIB", str(lib))
    monkeypatch.setattr(resolve_bridge, "MODULES", str(mod))


def run(cfg, r=FakeResolve(), running=True, key_ok=(True, "Key gültig"), tools=True):
    which = (lambda n: (f"/usr/bin/{n}", "System")) if tools else (lambda n: (None, None))
    return {c.id: c for c in setup_check.run(cfg, Bridge(r), gladia=lambda k: key_ok, running=lambda: running, which=which)}


def test_all_good(cfg, installed):
    cfg.gladia_api_key = "k"
    checks = run(cfg)
    assert all(c.ok for c in checks.values()), [c for c in checks.values() if not c.ok]
    s = setup_check.summary(list(checks.values()))
    assert s["ready"] and s["failed"] == 0 and "alles bereit" in setup_check.text(list(checks.values()))


def test_resolve_closed_dependent_checks_are_skipped(cfg, installed):
    checks = run(cfg, r=None, running=False)
    assert checks["running"].ok is False and "öffnen" in checks["running"].fix
    assert checks["scripting"].ok is None and checks["studio"].ok is None and checks["project"].ok is None
    assert not setup_check.summary(list(checks.values()))["ready"]


def test_scripting_off_free_version_old_version_no_project(cfg, installed):
    checks = run(cfg, r=None, running=True)
    assert checks["scripting"].ok is False and "External scripting using" in checks["scripting"].fix and "Local" in checks["scripting"].fix
    checks = run(cfg, r=FakeResolve(product="DaVinci Resolve", version=(20, 3, 0, 1, ""), project=None))
    assert checks["studio"].ok is False and checks["version"].ok is False and checks["project"].ok is False


def test_key_ffmpeg_cache(cfg, installed, tmp_path):
    cfg.gladia_api_key = None
    checks = run(cfg, key_ok=(False, "kein Key eingetragen"), tools=False)
    assert checks["gladia"].ok is False and "Erweiterungen" in checks["gladia"].fix
    assert checks["ffmpeg"].ok is False and checks["ffprobe"].ok is False
    assert checks["cache"].ok is True and "disk_cache" in checks
    (tmp_path / "datei").write_text("x")
    cfg.cache_dir = tmp_path / "datei" / "cache"  # below a file: not creatable anywhere
    assert run(cfg)["cache"].ok is False


def test_gladia_check_uses_listing_endpoint(monkeypatch):
    import httpx
    seen = {}

    def get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, key=headers.get("x-gladia-key"))
        return httpx.Response(401 if headers["x-gladia-key"] == "bad" else 200, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    assert setup_check._gladia("good") == (True, "Key gültig")
    assert setup_check._gladia("bad")[0] is False
    assert seen["url"].endswith("/v2/pre-recorded") and seen["params"] == {"limit": 1}
    assert setup_check._gladia(None)[0] is False


def test_tools_return_setup_checklist_instead_of_connection_error(monkeypatch, installed):
    import asyncio

    from mcp.client import Client

    import schnippo.server as srv

    def down():
        raise resolve_bridge.ResolveUnavailable("Resolve not reachable")
    monkeypatch.setattr(srv._bridge, "resolve", down)
    monkeypatch.setattr(srv._bridge, "project", down)
    monkeypatch.setattr(setup_check, "_resolve_running", lambda: False)
    monkeypatch.setattr(setup_check, "_gladia", lambda k: (True, "Key gültig"))

    async def go():
        async with Client(srv.mcp) as c:
            r = await c.call_tool("run_qc", {"timeline": "X"})
            setup = await c.call_tool("check_setup", {})
            return r, setup
    r, setup = asyncio.run(go())
    text = r.content[0].text
    assert r.is_error and "Resolve nicht erreichbar" in text and "❌ Resolve läuft" in text and "öffnen" in text
    assert "Traceback" not in text
    assert setup.structured_content["ready"] is False
    assert any(c["id"] == "running" and c["ok"] is False for c in setup.structured_content["checks"])


def test_key_source_and_restart_hint(cfg, installed):
    cfg.gladia_api_key, cfg.gladia_key_source = "k", "Erweiterung (Einstellungen in Claude)"
    assert "gelesen aus: Erweiterung" in run(cfg)["gladia"].detail
    cfg.gladia_api_key = None
    c = run(cfg, key_ok=(False, "kein Key eingetragen"))["gladia"]
    assert "SPEICHERN" in c.fix and "Konfigurieren" in c.fix and "k" != c.detail
