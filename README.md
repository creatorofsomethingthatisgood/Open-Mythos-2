# 🌟 Mythos Local

A complete, production-ready Python project for running high-quality local language models optimized for **AMD hardware on Fedora Linux**.

Built to match or exceed the quality of "Mythos" - featuring advanced reasoning, creative writing, coding assistance, and instruction following.

## ✨ Features

### Core Capabilities
- **🚀 AMD GPU Acceleration** - Vulkan backend for Radeon GPUs, OpenBLAS CPU fallback
- **🧠 High-Quality Inference** - Optimized for Qwen2.5, Mistral, Llama 3.1 models
- **💬 Dual Interfaces** - Beautiful terminal UI (Rich) + web interface (Gradio)
- **📚 RAG Pipeline** - Retrieval-Augmented Generation with ChromaDB
- **🔄 Self-Reflection** - Quality enhancement through iterative improvement
- **📊 Benchmarking** - Comprehensive evaluation suite
- **💾 Conversation Memory** - Persistent chat history with smart context management
- **🎨 Multiple Personalities** - System prompts for creative, analytical, coding, roleplay modes

### Advanced Features
- **Streaming Generation** - Token-by-token output with speed metrics
- **Context Window Management** - Sliding window + auto-summarization
- **Document Indexing** - PDF, TXT, MD, code files for RAG
- **Multi-Model Support** - Easy model switching and fallbacks
- **Fine-Tuning Pipeline** - LoRA training (educational, CPU-based)
- **Export & Persistence** - Save conversations, benchmark results

## 🖥️ Hardware Requirements

### Minimum
- **OS:** macOS 13+ (Apple Silicon recommended) or Fedora Linux
- **CPU:** AMD Ryzen AI 5 or equivalent (6+ threads)
- **RAM:** 8GB (model + system)
- **Storage:** 10GB free space

### Recommended
- **RAM:** 16GB (for larger context windows)
- **GPU:** AMD Radeon RDNA iGPU with Vulkan support
- **Storage:** SSD for faster model loading

### Notes
- **macOS:** Uses Metal GPU acceleration on Apple Silicon (M1/M2/M3/M4). No CUDA needed.
- **Linux:** ⚠️ NO CUDA. NO NVIDIA. AMD only.
- Uses Vulkan for GPU acceleration on Linux (falls back to CPU if unavailable)
- ROCm is optional (Vulkan preferred for compatibility)
- Models are shared in system RAM (integrated graphics)

## 📦 Installation

### Quick Start

**macOS (Apple Silicon or Intel):**

```bash
cd amd-vulkan-llm-project1
chmod +x setup-macos.sh
./setup-macos.sh
```

**Fedora Linux:**

```bash
# Clone or download this project
cd mythos_local

# Run the setup script (handles everything)
chmod +x setup.sh
./setup.sh
```

The setup script will:
1. Install system dependencies (Vulkan, OpenBLAS, build tools)
2. Create Python virtual environment
3. Build llama-cpp-python with Vulkan support
4. Install all Python dependencies
5. Download the default model (~4.5GB)
6. Run a test inference

### Manual Installation

```bash
# Install system dependencies
sudo dnf install -y gcc gcc-c++ make cmake git \
    vulkan-loader vulkan-headers mesa-vulkan-drivers \
    openblas-devel python3 python3-pip python3-devel

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install llama-cpp-python with Vulkan
CMAKE_ARGS="-DGGML_VULKAN=on" pip install llama-cpp-python --no-cache-dir

# If Vulkan fails, use OpenBLAS:
# CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python --no-cache-dir

# Install other dependencies
pip install -r requirements.txt

# Download default model
python3 main.py --mode download
```

## 🚀 Usage

### Terminal Chat (Default)

```bash
source venv/bin/activate
python3 main.py --mode chat
```

**Commands:**
- `/help` - Show all commands
- `/clear` - Clear conversation
- `/save` - Save conversation
- `/load` - Load previous conversation
- `/system <prompt>` - Change personality
- `/temp 0.9` - Adjust temperature
- `/reflect on` - Enable self-reflection
- `/rag on` - Enable document retrieval
- `/benchmark` - Run quality tests
- `/quit` - Exit

### Web Interface

```bash
python3 main.py --mode web
```

Then open http://localhost:7860 in your browser.

Features:
- Beautiful chat interface with streaming
- Sidebar with all generation settings
- Temperature, top-p, top-k, repeat penalty sliders
- System prompt editor
- Self-reflection toggle
- RAG document upload
- Conversation export
- Dark theme

### Advanced Modes

```bash
# Run benchmarks
python3 main.py --mode benchmark

# Download a model
python3 main.py --mode download

# Index RAG documents
python3 main.py --mode rag-index

# Fine-tune (educational, very slow on CPU)
python3 main.py --mode finetune

# Use custom config
python3 main.py --config my_config.yaml

# Web UI on custom port with public link
python3 main.py --mode web --port 8080 --share
```

## 📁 Project Structure

```
mythos_local/
├── main.py                    # Main entry point
├── config.yaml                # Configuration file
├── setup.sh                   # Fedora setup script
├── requirements.txt           # Python dependencies
├── README.md                  # This file
│
├── engine/                    # Core engine modules
│   ├── inference.py           # Inference with Vulkan/CPU fallback
│   ├── model_manager.py       # Model download & management
│   ├── prompt_manager.py      # System prompts & templates
│   ├── memory.py              # Conversation history
│   ├── rag.py                 # RAG with ChromaDB
│   ├── self_reflect.py        # Quality enhancement
│   └── benchmark.py           # Evaluation suite
│
├── ui/                        # User interfaces
│   ├── terminal_ui.py         # Rich terminal interface
│   └── web_ui.py              # Gradio web interface
│
├── training/                  # Fine-tuning (optional)
│   ├── prepare_data.py        # Dataset preparation
│   ├── finetune.py            # LoRA training
│   └── merge_lora.py          # Merge adapter
│
├── prompts/                   # System prompt templates
│   ├── default.txt            # Default Mythos prompt
│   ├── creative.txt           # Creative writing mode
│   ├── coding.txt             # Coding assistant mode
│   ├── analytical.txt         # Analysis mode
│   └── roleplay.txt           # Roleplay mode
│
├── models/                    # Downloaded models (.gguf)
├── rag_docs/                  # Documents for RAG
├── conversations/             # Saved conversations
├── benchmarks/                # Benchmark results
└── lora/                      # LoRA adapters
```

## ⚙️ Configuration

Edit `config.yaml` to customize:

### Model Settings
```yaml
model:
  name: "qwen2.5-7b-instruct"
  context_length: 8192
  n_gpu_layers: 0      # -1 for all on GPU, 0 for CPU only
  n_threads: 0         # 0 = auto (half of CPU cores)
  n_batch: 512
```

### Generation Settings
```yaml
generation:
  temperature: 0.7     # 0.0 = deterministic, 2.0 = very creative
  top_p: 0.9
  top_k: 40
  repeat_penalty: 1.1
  max_tokens: 2048
```

### RAG Settings
```yaml
rag:
  enabled: false
  chunk_size: 500      # Tokens per chunk
  top_k: 3            # Chunks to retrieve
  embedding_model: "all-MiniLM-L6-v2"
```

### Memory Settings
```yaml
memory:
  max_history_turns: 50
  auto_summarize: true
  save_conversations: true
```

## 🎯 Models

### Default Model
**Qwen2.5-7B-Instruct-Q4_K_M** (~4.5GB)
- Excellent reasoning and instruction following
- Strong multilingual support
- Good balance of quality and speed

### Fallback Models
1. **Mistral-7B-Instruct-v0.3** - Great for creative writing
2. **Llama-3.1-8B-Instruct** - Strong coding and analysis

All models use Q4_K_M quantization for optimal quality/size ratio.

### Using Custom Models

1. Download a GGUF model to `models/` directory
2. Update `config.yaml` with the path
3. Or use: `python3 main.py --model path/to/model.gguf`

## 📚 RAG (Retrieval-Augmented Generation)

### Setup

1. Place documents in `rag_docs/`:
   ```bash
   cp my_document.pdf rag_docs/
   cp my_notes.md rag_docs/
   ```

2. Index documents:
   ```bash
   python3 main.py --mode rag-index
   ```

3. Enable in chat:
   ```
   /rag on
   ```

### Supported Formats
- `.txt` - Plain text
- `.md` - Markdown
- `.pdf` - PDF documents
- `.py` - Python code
- `.json` - JSON data

The system automatically chunks documents, generates embeddings, and retrieves relevant context for your queries.

## 📊 Benchmarking

Run comprehensive quality tests:

```bash
python3 main.py --mode benchmark
```

Tests 20 scenarios across 4 categories:
- **Reasoning** - Logic puzzles, math, syllogisms
- **Creative Writing** - Stories, poetry, dialogue
- **Coding** - Algorithms, data structures, API design
- **Instruction Following** - Format compliance, constraints

Results are scored 0-10 and saved to `benchmarks/`.

## 🎨 System Prompts

Switch personalities for different tasks:

### Creative Writing
```
/system creative
```
Vivid imagery, emotional depth, storytelling mastery.

### Coding Assistant
```
/system coding
```
Clean code, best practices, thoughtful architecture.

### Analytical Mode
```
/system analytical
```
Rigorous logic, critical thinking, evidence-based reasoning.

### Roleplay
```
/system roleplay
```
Character embodiment, immersive storytelling.

### Custom Prompt
```
/system You are a helpful assistant specializing in...
```

## 🔧 Performance Tuning

### GPU Acceleration

If you have AMD Vulkan support:
```yaml
model:
  n_gpu_layers: -1  # Use all layers on GPU
```

Check with: `vulkaninfo` (should show your AMD GPU)

### CPU Optimization

For CPU-only mode:
```yaml
model:
  n_gpu_layers: 0
  n_threads: 6        # Half of your CPU threads
  use_mmap: true      # Faster loading
  use_mlock: false    # Set true if you have RAM to spare
```

### Memory Management

Reduce RAM usage:
```yaml
model:
  context_length: 4096  # Smaller context
  
memory:
  max_history_turns: 20  # Fewer turns in memory
```

### Speed vs Quality

Faster (lower quality):
```yaml
generation:
  temperature: 0.8
  max_tokens: 1024

system:
  self_reflect: false
```

Higher quality (slower):
```yaml
generation:
  temperature: 0.7
  max_tokens: 2048

system:
  self_reflect: true
```

## 🐛 Troubleshooting

### Vulkan Build Failed

If Vulkan compilation fails:
```bash
# Fall back to OpenBLAS
CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python --no-cache-dir
```

### Model Download Fails

Download manually from HuggingFace:
```bash
# Visit: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF
# Download: qwen2.5-7b-instruct-q4_k_m.gguf
# Place in: models/
```

### Out of Memory

1. Reduce context length in `config.yaml`
2. Use smaller model
3. Close other applications
4. Set `n_gpu_layers: 0` (CPU-only)

### Slow Performance

1. Check if GPU is actually being used (see logs at startup)
2. Reduce `n_batch` if memory constrained
3. Increase `n_threads` for CPU mode
4. Disable self-reflection for faster responses

### RAG Not Working

```bash
# Check ChromaDB installation
pip install chromadb sentence-transformers

# Re-index documents
python3 main.py --mode rag-index
```

## 🎓 Fine-Tuning (Advanced)

**Warning:** CPU training is very slow. Educational only.

```bash
# Prepare dataset (downloads 100 samples)
python3 main.py --mode finetune
```

For production fine-tuning:
- Use cloud GPU (RunPod, Vast.ai, Google Colab)
- Use `unsloth` library for faster training
- Consider 4-bit quantization with QLoRA

## 📝 Examples

### Example Session

```
You: Explain quantum computing to a 10-year-old