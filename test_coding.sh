#!/bin/bash
# Quick test of Mythos coding capabilities

echo "═══════════════════════════════════════════════════════════════"
echo "  MYTHOS CODING MODE TEST"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "This will test the coding prompt by asking the model to solve"
echo "a classic algorithm problem and verify its 5-pass approach."
echo ""

# Activate venv
source venv/bin/activate

# Create a test Python script
cat > /tmp/mythos_code_test.py << 'EOF'
from engine.inference import InferenceEngine
from engine.prompt_manager import PromptManager
import yaml

# Load coding prompt
prompt_mgr = PromptManager()
prompt_mgr.set_prompt(prompt_mgr.load_prompt("coding"))

# Initialize engine
engine = InferenceEngine()

# Test prompt - classic algorithm problem
test_prompt = """Write a Python function to find the longest common subsequence (LCS) of two strings.

Requirements:
- Use dynamic programming
- Handle edge cases (empty strings, single character)
- Time complexity: O(m*n)
- Space complexity: O(m*n)
- Include clear comments
- Provide example usage
"""

print("Testing Mythos Coding Mode...")
print("=" * 60)
print("PROMPT:")
print(test_prompt)
print("=" * 60)
print("\nGENERATING RESPONSE (this may take 30-60 seconds)...\n")
print("=" * 60)

# Format with system prompt
system_prompt = prompt_mgr.get_prompt()
messages = [{"role": "user", "content": test_prompt}]
full_prompt = engine.format_chat_prompt(messages, system_prompt)

# Generate
response = engine.generate(full_prompt, max_tokens=1500, stream=False)

print("MYTHOS RESPONSE:")
print("=" * 60)
print(response)
print("=" * 60)

# Check for quality indicators
checks = {
    "Code block present": "```python" in response or "def " in response,
    "Edge cases mentioned": any(word in response.lower() for word in ["edge", "empty", "boundary", "null", "none"]),
    "Complexity discussed": any(word in response for word in ["O(", "complexity", "time", "space"]),
    "Comments/explanation": "#" in response or "explanation" in response.lower(),
    "Verification/testing": any(word in response.lower() for word in ["verify", "test", "example", "usage"]),
}

print("\n\nQUALITY CHECKS:")
print("=" * 60)
for check, passed in checks.items():
    status = "✓" if passed else "✗"
    print(f"{status} {check}")

passed_count = sum(checks.values())
total_count = len(checks)
print("=" * 60)
print(f"Score: {passed_count}/{total_count} ({100*passed_count//total_count}%)")

if passed_count >= 4:
    print("\n🎉 EXCELLENT! Coding mode is working at high quality!")
elif passed_count >= 3:
    print("\n👍 GOOD! Coding mode is functional.")
else:
    print("\n⚠️  Needs tuning. Consider adjusting temperature or using /reflect on")

EOF

# Run the test
python3 /tmp/mythos_code_test.py

# Cleanup
rm /tmp/mythos_code_test.py

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Test complete! To use coding mode interactively:"
echo "  python3 main.py --mode chat"
echo "  Then type: /system coding"
echo "═══════════════════════════════════════════════════════════════"
