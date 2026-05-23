#!/usr/bin/env python3
"""
Quick test script to verify model download
"""

import sys
import os
from pathlib import Path

# Make sure we're using the config from current directory
os.chdir(Path(__file__).parent)

from engine.model_manager import ModelManager

def main():
    print("Testing model download...")
    print("-" * 50)
    
    try:
        # Initialize model manager
        manager = ModelManager()
        
        # Try to download
        model_path = manager.download_default()
        
        # Check file exists and size
        if model_path.exists():
            file_size = model_path.stat().st_size / (1024 ** 3)  # GB
            print(f"\n✓ Success! Model downloaded to: {model_path}")
            print(f"  File size: {file_size:.2f} GB")
            return 0
        else:
            print(f"\n✗ Error: Model file not found at {model_path}")
            return 1
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
