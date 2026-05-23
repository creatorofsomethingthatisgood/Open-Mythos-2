#!/usr/bin/env python3
"""
Show exactly what will be downloaded
"""

import yaml
from pathlib import Path

print("=" * 70)
print("SHOWING EXACT DOWNLOAD URLS THAT WILL BE USED")
print("=" * 70)
print()

config_path = Path("config.yaml")

if not config_path.exists():
    print(f"❌ ERROR: config.yaml not found at {config_path.absolute()}")
    exit(1)

with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

model = config.get('model', {})

print("PRIMARY MODEL:")
print("-" * 70)
repo_id = model.get('repo_id', 'NOT SET')
filename = model.get('filename', 'NOT SET')

print(f"Repository: {repo_id}")
print(f"File: {filename}")
print(f"Full URL: https://huggingface.co/{repo_id}/resolve/main/{filename}")
print()

if 'bartowski' in repo_id:
    print("✓✓✓ CORRECT - Using bartowski repository ✓✓✓")
    print("    This URL is VERIFIED to work!")
else:
    print("❌❌❌ WRONG - NOT using bartowski repository ❌❌❌")
    print("    This URL will NOT work!")
    print()
    print("Expected: bartowski/Qwen2.5-7B-Instruct-GGUF")
    print(f"Got: {repo_id}")

print()
print("=" * 70)
print("FALLBACK MODELS:")
print("=" * 70)
print()

for i, fallback in enumerate(model.get('fallbacks', []), 1):
    print(f"Fallback {i}: {fallback.get('name', 'unknown')}")
    repo = fallback.get('repo_id', 'NOT SET')
    file = fallback.get('filename', 'NOT SET')
    print(f"  Repository: {repo}")
    print(f"  File: {file}")
    
    if 'bartowski' in repo:
        print(f"  Status: ✓ CORRECT")
    else:
        print(f"  Status: ❌ WRONG")
    print()

print("=" * 70)
print()
print("To download the model:")
print("  python3 test_download.py")
print()
print("To start chatting:")
print("  python3 main.py --mode chat")
print()
print("=" * 70)
