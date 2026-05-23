╔════════════════════════════════════════════════════════════════╗
║                    MYTHOS LOCAL - FIXED!                       ║
║              Model Download URLs Are Now Correct               ║
╚════════════════════════════════════════════════════════════════╝

The config.yaml has been completely rewritten with the correct model URLs.

STEP-BY-STEP INSTRUCTIONS (Copy-paste these commands):

1. Navigate to project directory:
   cd ~/mythos_local/amd-vulkan-llm-project

2. Activate virtual environment:
   source venv/bin/activate

3. FIRST - Verify the config is correct:
   python3 debug_config.py

   You should see:
   ✓ Config is using bartowski repo (CORRECT)

4. Test model download:
   python3 test_download.py

   This will download ~4.7GB. Be patient.
   Expected output:
   ✓ Success! Model downloaded to: models/Qwen2.5-7B-Instruct-Q4_K_M.gguf
   File size: 4.68 GB

5. Start chatting:
   python3 main.py --mode chat

   OR for web interface:
   python3 main.py --mode web


═══════════════════════════════════════════════════════════════

WHAT WAS FIXED:

1. config.yaml - Completely rewritten to use bartowski repos:
   ✓ bartowski/Qwen2.5-7B-Instruct-GGUF (PRIMARY)
   ✓ bartowski/Mistral-7B-Instruct-v0.3-GGUF (FALLBACK 1)
   ✓ bartowski/Meta-Llama-3.1-8B-Instruct-GGUF (FALLBACK 2)

2. Added debug_config.py - Verify config loading

3. Added test_download.py - Test downloads before running main app

4. Enhanced logging in model_manager.py - Shows which repo/file is being used

═══════════════════════════════════════════════════════════════

TROUBLESHOOTING:

If you still see errors about "Qwen/Qwen2.5-7B-Instruct-GGUF" (without bartowski):

A. Make sure you're in the RIGHT directory:
   pwd
   
   Should show: /home/a4/mythos_local/amd-vulkan-llm-project

B. Check if there's another config.yaml somewhere:
   find ~ -name "config.yaml" -type f 2>/dev/null

C. Force reload by deleting any cached files:
   rm -rf __pycache__ engine/__pycache__ ui/__pycache__
   
D. Verify the config one more time:
   grep "repo_id" config.yaml
   
   Should show:
   repo_id: "bartowski/Qwen2.5-7B-Instruct-GGUF"

═══════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════

QUICK START - COPY THESE EXACT COMMANDS:

cd ~/mythos_local/amd-vulkan-llm-project
source venv/bin/activate
chmod +x *.sh
./show_config.sh
python3 test_download.py
python3 main.py --mode chat

═══════════════════════════════════════════════════════════════

OR FOR FULL VERIFICATION:

cd ~/mythos_local/amd-vulkan-llm-project
source venv/bin/activate
chmod +x verify_setup.sh
./verify_setup.sh
python3 test_download.py
python3 main.py --mode chat

═══════════════════════════════════════════════════════════════
