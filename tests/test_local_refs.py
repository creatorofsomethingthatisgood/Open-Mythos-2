"""Tests for chat local file reference parsing."""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "local_refs", _ROOT / "engine" / "local_refs.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

extract_local_refs = _mod.extract_local_refs
ref_to_path = _mod.ref_to_path
build_local_file_context = _mod.build_local_file_context


def test_extract_file_url():
    msg = "Check file:///Users/dev/app/main.py for SQL injection"
    refs = extract_local_refs(msg)
    assert any("file://" in r for r in refs)


def test_extract_quoted_path():
    msg = "find vulns in '/Users/ludwing/Documents/GitHub/carla-chat'"
    refs = extract_local_refs(msg)
    assert any("carla-chat" in r for r in refs)


def test_extract_tilde_path():
    msg = "Audit ~/projects/payments-api/handlers/auth.py"
    refs = extract_local_refs(msg)
    assert any("~/projects" in r for r in refs)


def test_ref_to_path_file_url():
    p = ref_to_path("file:///tmp/example.py")
    assert str(p).endswith("/tmp/example.py")


def test_build_context_missing_file():
    ctx, notices = build_local_file_context(
        "review /this/path/does/not/exist.py",
        config={"chat": {"local_files": {"enabled": True}}},
    )
    assert ctx == ""
    assert any("Not found" in n for n in notices)


def test_build_context_loads_file(tmp_path):
    sample = tmp_path / "vuln.py"
    sample.write_text('password = "supersecret123"\n', encoding="utf-8")
    msg = f"Find issues in {sample}"
    ctx, notices = build_local_file_context(
        msg,
        config={"chat": {"local_files": {"enabled": True, "static_scan": True}}},
    )
    assert "supersecret123" in ctx
    assert any("Loaded" in n for n in notices)
    assert "STATIC SCAN FINDINGS" in ctx
