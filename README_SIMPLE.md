# Mythos Local - Simple Start Guide

**Status: ✅ FIXED & VERIFIED**

The configuration has been completely rewritten with correct model URLs.

## 🚀 Quickest Start (3 commands)

```bash
cd ~/mythos_local/amd-vulkan-llm-project
source venv/bin/activate
./run_chat.sh
```

That's it! The model will auto-download on first run.

---

## 📋 What's Available

### Option 1: Terminal Chat (Recommended First)
```bash
./run_chat.sh
```
- Clean terminal interface
- Streaming responses
- Commands like `/help`, `/benchmark`, `/temp 0.9`

### Option 2: Web Interface (Pretty UI)
```bash
./run_web.sh
```
- Opens at http://localhost:7860
- Sliders for temperature, top-p, etc.
- Upload documents for RAG

### Option 3: Just Download Model
```bash
source venv/bin/activate
python3 test_download.py
```

### Option 4: Verify Everything First
```bash
source venv/bin/activate
./verify_setup.sh
```

---

## 🔍 Verify Config is Correct

```bash
./show_config.sh
```

**You should see:**
```
✓✓✓ CORRECT - Using bartowski repos ✓✓✓
```

**NOT:**
```
❌❌❌ WRONG - NOT using bartowski! ❌❌❌
```

---

## ⚡ Performance Expectations

**First Run:**
- Download: 5-10 minutes (~4.7GB)
- Model loading: 15-20 seconds
- Then ready to chat!

**Subsequent Runs:**
- Model loading: 10-15 seconds
- Ready immediately

**Speed:**
- CPU-only: 5-15 tokens/second
- With Vulkan: 15-30 tokens/second
- RAM usage: 6-10GB

---

## 🎯 What Was Fixed

1. **config.yaml** - Completely rewritten
   - ✅ Now uses: `bartowski/Qwen2.5-7B-Instruct-GGUF`
   - ❌ Was using: `Qwen/Qwen2.5-7B-Instruct-GGUF` (404 error)

2. **Added verification scripts:**
   - `show_download_url.py` - Shows exact download URL
   - `debug_config.py` - Debug config loading
   - `test_download.py` - Test download only
   - `verify_setup.sh` - Full verification
   - `show_config.sh` - Quick config check

3. **Added simple runners:**
   - `run_chat.sh` - One-command start for terminal
   - `run_web.sh` - One-command start for web UI

---

## 🐛 Troubleshooting

### Still seeing 404 errors?

1. **Check you're in the right directory:**
   ```bash
   pwd
   # Should show: /home/a4/mythos_local/amd-vulkan-llm-project
   ```

2. **Verify config:**
   ```bash
   grep "repo_id" config.yaml | head -1
   # Should show: repo_id: "bartowski/Qwen2.5-7B-Instruct-GGUF"
   ```

3. **Clear Python cache:**
   ```bash
   rm -rf __pycache__ engine/__pycache__ ui/__pycache__
   ```

4. **Show actual download URL:**
   ```bash
   python3 show_download_url.py
   # Should show "bartowski" and "✓✓✓ CORRECT"
   ```

---

## 📚 Documentation Files

- **FINAL_INSTRUCTIONS.txt** - Most detailed guide
- **START_HERE.txt** - Comprehensive start guide
- **FIXED_README.txt** - What was fixed and why
- **README.md** - Full technical documentation
- **README_SIMPLE.md** - This file (simple guide)

---

## 🎓 Chat Commands (Terminal Mode)

Once running, type these:

- `/help` - Show all commands
- `/benchmark` - Test model quality
- `/system creative` - Creative writing mode
- `/system coding` - Coding assistant mode
- `/temp 0.9` - More creative responses
- `/reflect on` - Better quality (slower)
- `/quit` - Exit

---

## ✅ Success Checklist

Before running, verify:

- [ ] You're in `~/mythos_local/amd-vulkan-llm-project`
- [ ] Virtual environment is activated `(venv)`
- [ ] `./show_config.sh` shows "bartowski"
- [ ] You have ~6GB free disk space for model
- [ ] You have ~10GB free RAM

Then run: `./run_chat.sh`

---

## 🚀 Ready!

```bash
cd ~/mythos_local/amd-vulkan-llm-project
source venv/bin/activate
./run_chat.sh
```

The first run will download the model. Be patient!

Enjoy your Mythos-tier local LLM! 🎉
