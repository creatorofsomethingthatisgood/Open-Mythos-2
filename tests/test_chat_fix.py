"""Tests for chat fix intent and patch parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.chat_config import apply_unlimited_chat_limits, file_limit, merge_chat_defaults
from engine.local_refs import extract_local_refs
from engine.chat_fix import (
    _files_to_rewrite,
    extract_patches_from_response,
    is_placeholder_patch_path,
    user_confirms_rewrite,
    user_wants_apply,
    user_wants_fix,
    user_wants_rewrite,
)


def test_fix_intent():
    assert user_wants_fix("fix the vulns in ~/app")
    assert user_wants_fix("please patch SQL injection issues")
    assert not user_wants_fix("find vulnerabilities only")


def test_apply_intent():
    assert user_wants_apply("apply fixes to ~/app")
    assert not user_wants_apply("fix vulns in ~/app")


def test_rewrite_intent():
    assert user_wants_rewrite("rewrite the fixed file in ~/app/main.py")
    assert user_wants_apply("rewrite ~/app/main.py")


def test_confirm_rewrite_intent():
    assert user_confirms_rewrite("i confirm")
    assert user_confirms_rewrite("yes")
    assert not user_confirms_rewrite("fix the vulns in ~/app")


def test_quoted_unix_path_in_message():
    refs = extract_local_refs(
        "fix a bug in this '/Users/me/Documents/GitHub/carla-agent' rewrite"
    )
    assert any("carla-agent" in r for r in refs)


def test_reject_placeholder_patch_path():
    assert is_placeholder_patch_path(Path("/absolute/path/to/file.py"))
    assert not is_placeholder_patch_path(Path("/tmp/demo.py"))


def test_extract_markdown_heading_patch():
    text = '''
### MYTHOS_PATCH Blocks

#### `/tmp/demo.py`

```python
x = 1
y = 2
z = 3
```
'''
    patches = extract_patches_from_response(text)
    assert len(patches) == 1
    assert patches[0][0] == Path("/tmp/demo.py")


def test_extract_patch_block():
    text = '''
Here is the fix:

<<<MYTHOS_PATCH path="/tmp/demo.py">>>
```python
x = 1
```
<<<END_PATCH>>>
'''
    patches = extract_patches_from_response(text)
    assert len(patches) == 1
    assert patches[0][0] == Path("/tmp/demo.py")
    assert "x = 1" in patches[0][1]


def test_unlimited_rewrite_files():
    assert file_limit(0) is None
    assert file_limit(-1) is None
    assert file_limit(3) == 3
    paths = _files_to_rewrite(
        [],
        [],
        {"chat": {"fix": {"max_rewrite_files": 0}}},
    )
    assert paths == []


def test_merge_forces_unlimited_even_if_user_config_caps():
    merged = merge_chat_defaults(
        {"chat": {"fix": {"max_rewrite_files": 5}, "local_files": {"max_files": 10}}}
    )
    assert merged["chat"]["fix"]["max_rewrite_files"] == 0
    assert merged["chat"]["local_files"]["max_files"] == 0
    assert apply_unlimited_chat_limits({})["fix"]["max_rewrite_files"] == 0
