#!/usr/bin/env python3
"""
Debug script to verify config loading
"""

import yaml
import os
from pathlib import Path

# Make sure we're in the project directory
os.chdir(Path(__file__).parent)

config_path = Path("config.yaml")

print("=" * 60)
print("CONFIG DEBUG")
print("=" * 60)
print(f"\nReading config from: {config_path.absolute()}")
print(f"File exists: {config_path.exists()}")

if config_path.exists():
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print("\n" + "=" * 60)
    print("MODEL CONFIGURATION")
    print("=" * 60)
    
    model = config.get('model', {})
    print(f"\nName: {model.get('name')}")
    print(f"Path: {model.get('path')}")
    print(f"Repo ID: {model.get('repo_id')}")
    print(f"Filename: {model.get('filename')}")
    
    if 'download_url' in model:
        print(f"Download URL (OLD FORMAT): {model.get('download_url')}")
    
    print("\n" + "=" * 60)
    print("FALLBACK MODELS")
    print("=" * 60)
    
    for i, fallback in enumerate(model.get('fallbacks', []), 1):
        print(f"\nFallback {i}:")
        print(f"  Name: {fallback.get('name')}")
        print(f"  Repo ID: {fallback.get('repo_id')}")
        print(f"  Filename: {fallback.get('filename')}")
    
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    
    repo_id = model.get('repo_id', '')
    if 'bartowski' in repo_id:
        print("\n✓ Config is using bartowski repo (CORRECT)")
    elif 'Qwen' in repo_id and 'bartowski' not in repo_id:
        print("\n✗ Config is using official Qwen repo (WRONG - needs bartowski)")
    else:
        print(f"\n? Unexpected repo: {repo_id}")
    
    print("\n" + "=" * 60)
else:
    print("\n✗ Config file not found!")
