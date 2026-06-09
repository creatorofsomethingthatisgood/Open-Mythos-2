"""
Security Verification Suite - Container Breakout Detection for Open-1.
Tests the model's ability to identify escape vectors in a controlled environment.
"""

import unittest
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.container_detect import check_escape_vectors, detect_container

class TestOpen1Security(unittest.TestCase):
    """Verifies that Open-1's underlying security logic identifies breakout vectors."""

    def test_container_detection(self):
        """Test if the system correctly identifies if it's in a container."""
        info = detect_container()
        print(f"[*] Detected Container: {info.is_container} ({info.container_type})")
        # This will vary by environment, but we want to ensure it doesn't crash
        self.assertIsInstance(info.is_container, bool)

    def test_escape_vector_enumeration(self):
        """
        Verify that the model can identify critical escape vectors.
        In a real test, we would mock these vectors.
        """
        findings = check_escape_vectors()
        print(f"[*] Found {len(findings)} potential escape vectors.")
        
        for f in findings:
            print(f"  - [{f.severity.upper()}] {f.vector}: {f.description}")
            
        # Success criteria for "Open-1": Must be able to report vectors if they exist
        # We don't assert > 0 because a secure environment SHOULD have 0
        self.assertIsInstance(findings, list)

    def mock_breakout_challenge(self):
        """
        A simulated challenge where we seed a vulnerability (e.g., exposed docker.sock)
        and verify the model's 'Operative' mode identifies it.
        """
        # This requires the inference engine to be running with open1_config.yaml
        pass

if __name__ == "__main__":
    unittest.main()
