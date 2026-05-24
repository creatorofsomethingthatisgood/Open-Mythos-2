"""MYTHOS_PATCH parse and apply."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.chat_fix import extract_patches_from_response


def test_strict_patch_block():
    text = '''<<<MYTHOS_PATCH path="/tmp/demo.py">>>
```python
x = 1
y = 2
```
<<<END_PATCH>>>'''
    patches = extract_patches_from_response(text)
    assert len(patches) == 1
    assert patches[0][0] == Path("/tmp/demo.py")
    assert "x = 1" in patches[0][1]


def test_rejects_diff_only():
    text = """### Fix
```diff
diff --git a/foo.py b/foo.py
```
"""
    assert extract_patches_from_response(text) == []
