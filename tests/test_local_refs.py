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
_redact_secret_lines = _mod._redact_secret_lines


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


def test_build_context_missing_file(tmp_path):
    sample = tmp_path / "vuln.py"
    msg = f"review {sample}"
    ctx, notices = build_local_file_context(
        msg,
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
    assert "supersecret123" not in ctx
    assert any("Loaded" in n for n in notices)
    assert "STATIC SCAN FINDINGS" in ctx


def test_redact_pem_block_covers_body(tmp_path):
    """SEC001 flags the BEGIN line; the key body and END line must also be redacted."""
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBogIBAAJBALRiMLAHudeSA/x3hB2f+8sU\n"
        "ZxW1x2p9CvUjW8K3hQIDAQAB\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    sample = tmp_path / "key.pem"
    sample.write_text(pem, encoding="utf-8")
    msg = f"review {sample}"
    ctx, _ = build_local_file_context(
        msg,
        config={"chat": {"local_files": {"enabled": True, "static_scan": True}}},
    )
    assert "MIIBogIBAAJ" not in ctx
    assert "-----END RSA" not in ctx
    assert "<redacted" in ctx


def test_redact_secret_lines_offset():
    """_redact_secret_lines with line_offset=1 maps finding lines correctly."""
    from types import SimpleNamespace

    finding = SimpleNamespace(rule_id="SEC003", line=2)  # 1-based, line 2 in file
    header = "--- FILE: test.py (99 bytes) ---\n"
    body = "import os\npassword = 'hunter2'\nprint('hi')\n"
    text = header + body
    result = _redact_secret_lines(text, [finding], line_offset=1)
    assert "hunter2" not in result
    assert "import os" in result
    assert "print('hi')" in result
