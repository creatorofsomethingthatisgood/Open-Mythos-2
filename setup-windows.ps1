# Mythos Local - Windows Setup (PowerShell)
# Run as: .\setup-windows.ps1
# Requires: Python 3.10+, PowerShell 5.1+

$ErrorActionPreference = "Stop"

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Mythos Local - Windows Setup" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ──────────────────────────────────────────────────────
Write-Host "Checking Python installation..." -ForegroundColor White

$pythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonCmd = $cmd
                Write-Host "  Found $ver" -ForegroundColor Green
                break
            } else {
                Write-Host "  $ver found but Python 3.10+ is required" -ForegroundColor Yellow
            }
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Host "  Python 3.10+ not found." -ForegroundColor Red
    Write-Host "  Install from: https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "  Make sure to check 'Add Python to PATH' during install." -ForegroundColor Red
    exit 1
}

# ── Check for C++ build tools ─────────────────────────────────────────
Write-Host ""
Write-Host "Checking C++ build tools (required for llama-cpp-python)..." -ForegroundColor White

$hasCl = $false
try {
    $clTest = & cl 2>&1
    if ($LASTEXITCODE -ne 1) { $hasCl = $true }  # cl with no args exits 1 but is found
    $hasCl = $true
} catch {
    $hasCl = $false
}

# Check for Visual Studio / Build Tools
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$hasBuildTools = $false
if (Test-Path $vsWhere) {
    $vsPath = & $vsWhere -latest -property installationPath 2>$null
    if ($vsPath) {
        $msvcPath = Get-ChildItem "$vsPath\VC\Tools\MSVC" -ErrorAction SilentlyContinue | Sort-Object -Descending | Select-Object -First 1
        if ($msvcPath) { $hasBuildTools = $true }
    }
}

if (-not $hasCl -and -not $hasBuildTools) {
    Write-Host "  Microsoft C++ Build Tools not found." -ForegroundColor Yellow
    Write-Host "  llama-cpp-python requires them to compile." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Install one of:" -ForegroundColor Yellow
    Write-Host "    1. Visual Studio Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor White
    Write-Host "       (Select 'Desktop development with C++' workload)" -ForegroundColor White
    Write-Host "    2. Or full Visual Studio (Community is free)" -ForegroundColor White
    Write-Host ""
    $reply = Read-Host "Continue anyway? (y/n)"
    if ($reply -notmatch "^[Yy]") { exit 1 }
}

# ── Check for CMake ───────────────────────────────────────────────────
Write-Host ""
Write-Host "Checking CMake..." -ForegroundColor White
$cmakeFound = $false
try {
    $cmakeVer = & cmake --version 2>&1
    Write-Host "  CMake found: $($cmakeVer[0])" -ForegroundColor Green
    $cmakeFound = $true
} catch {
    Write-Host "  CMake not found." -ForegroundColor Yellow
    Write-Host "  Install via: winget install Kitware.CMake" -ForegroundColor Yellow
    Write-Host "  Or from: https://cmake.org/download/" -ForegroundColor Yellow
}

if (-not $cmakeFound) {
    $reply = Read-Host "Continue without CMake? (y/n)"
    if ($reply -notmatch "^[Yy]") { exit 1 }
}

# ── Create virtual environment ────────────────────────────────────────
Write-Host ""
Write-Host "Creating Python virtual environment..." -ForegroundColor White

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $scriptDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (Test-Path $venvDir) {
    # Check if venv was created on a different platform
    $pyvenvCfg = Join-Path $venvDir "pyvenv.cfg"
    if (Test-Path $pyvenvCfg) {
        $cfgContent = Get-Content $pyvenvCfg -Raw
        if ($cfgContent -match "/home/" -or $cfgContent -match "/Users/") {
            Write-Host "  Existing venv was created on another OS - recreating..." -ForegroundColor Yellow
            Remove-Item -Recurse -Force $venvDir
        } else {
            Write-Host "  Virtual environment already exists." -ForegroundColor Green
        }
    }
}

if (-not (Test-Path $venvDir)) {
    & $pythonCmd -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Failed to create venv. Make sure python -m venv works." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Virtual environment created." -ForegroundColor Green
}

# ── Activate and install deps ─────────────────────────────────────────
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor White
& $venvPython -m pip install --upgrade pip setuptools wheel

# ── Build llama-cpp-python ────────────────────────────────────────────
Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Building llama-cpp-python (first run only - may take several minutes)..." -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

$llamaInstalled = $false

# Check if already installed
try {
    & $venvPython -c "from llama_cpp import Llama" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  llama-cpp-python already installed (skipping rebuild)" -ForegroundColor Green
        $llamaInstalled = $true
    }
} catch {}

if (-not $llamaInstalled) {
    # Try CUDA first (if nvidia-smi is available)
    $hasCuda = $false
    try {
        $nvidiaSmi = & nvidia-smi 2>&1
        if ($LASTEXITCODE -eq 0) { $hasCuda = $true }
    } catch {}

    if ($hasCuda) {
        Write-Host "  NVIDIA GPU detected - attempting CUDA build..." -ForegroundColor White
        $env:CMAKE_ARGS = "-DGGML_CUDA=on"
        try {
            & $venvPython -m pip install llama-cpp-python --no-cache-dir 2>&1 | Tee-Object -Variable buildLog
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  CUDA backend installed successfully!" -ForegroundColor Green
                $llamaInstalled = $true
            }
        } catch {
            Write-Host "  CUDA build failed, trying CPU fallback..." -ForegroundColor Yellow
        }
        Remove-Item Env:\CMAKE_ARGS -ErrorAction SilentlyContinue
    }

    # Try Vulkan (if GPU present)
    if (-not $llamaInstalled) {
        $vulkanDll = "${env:VULKAN_SDK}\Bin\vulkaninfo.exe"
        if (Test-Path $vulkanDll) {
            Write-Host "  Vulkan SDK detected - attempting Vulkan build..." -ForegroundColor White
            $env:CMAKE_ARGS = "-DGGML_VULKAN=on"
            try {
                & $venvPython -m pip install llama-cpp-python --no-cache-dir 2>&1 | Tee-Object -Variable buildLog
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  Vulkan backend installed successfully!" -ForegroundColor Green
                    $llamaInstalled = $true
                }
            } catch {
                Write-Host "  Vulkan build failed, trying CPU fallback..." -ForegroundColor Yellow
            }
            Remove-Item Env:\CMAKE_ARGS -ErrorAction SilentlyContinue
        }
    }

    # CPU fallback (OpenBLAS or plain)
    if (-not $llamaInstalled) {
        Write-Host "  Installing CPU-only build (no GPU acceleration)..." -ForegroundColor Yellow
        try {
            & $venvPython -m pip install llama-cpp-python --no-cache-dir
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  CPU backend installed successfully." -ForegroundColor Green
                $llamaInstalled = $true
            }
        } catch {
            Write-Host "  CPU build also failed. Try installing prebuilt wheel:" -ForegroundColor Red
            Write-Host "    pip install llama-cpp-python" -ForegroundColor White
        }
    }
}

if (-not $llamaInstalled) {
    Write-Host ""
    Write-Host "  Warning: llama-cpp-python not installed." -ForegroundColor Red
    Write-Host "  You may need to install build tools first (see above)." -ForegroundColor Red
    Write-Host "  After installing build tools, re-run this script." -ForegroundColor Red
}

# ── Install Mythos Python dependencies ────────────────────────────────
Write-Host ""
Write-Host "Installing Mythos package..." -ForegroundColor White
& $venvPython -m pip install -e ".[web]"
Write-Host "  Mythos CLI registered." -ForegroundColor Green

# ── Initialize user config ────────────────────────────────────────────
Write-Host ""
Write-Host "Initializing user config (~/.config/mythos)..." -ForegroundColor White
try {
    & $venvPython -m mythos_cli.main init 2>$null
} catch {
    try {
        & $venvPython -c "from mythos_cli.config_store import init_config; init_config(quiet=True); print('  User config ready')"
    } catch {
        Write-Host "  Config init skipped (will run on first launch)." -ForegroundColor Yellow
    }
}

# ── Create project directories ────────────────────────────────────────
Write-Host ""
Write-Host "Creating project directories..." -ForegroundColor White
foreach ($dir in @("models", "prompts", "rag_docs", "conversations", "benchmarks", "lora")) {
    $dirPath = Join-Path $scriptDir $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    }
    $gitkeep = Join-Path $dirPath ".gitkeep"
    if (-not (Test-Path $gitkeep)) {
        New-Item -ItemType File -Path $gitkeep -Force | Out-Null
    }
}
Write-Host "  Project directories created." -ForegroundColor Green

# ── Create default prompt template ────────────────────────────────────
$promptsDir = Join-Path $scriptDir "prompts"
$defaultPrompt = Join-Path $promptsDir "default.txt"
if (-not (Test-Path $defaultPrompt)) {
    $promptContent = @"
You are Mythos, an advanced AI assistant with extraordinary capabilities in reasoning, creativity, analysis, and communication. You approach every task with depth, nuance, and precision.

CORE BEHAVIORS:
- Think deeply before responding. Use internal reasoning chains.
- When solving problems, break them into steps and validate each step.
- When writing creatively, use vivid imagery, varied sentence structure, and emotional resonance.
- When coding, write clean, commented, production-quality code.
- When analyzing, consider multiple perspectives and edge cases.
- Acknowledge uncertainty honestly rather than fabricating information.
- Adapt your communication style to match the user's needs.

REASONING FRAMEWORK:
1. Understand the request fully before beginning
2. Consider what approach will yield the best result
3. Execute with attention to detail
4. Review your output for accuracy and completeness
5. Present your response clearly and structured

You are not just an assistant - you are a thinking partner who elevates every interaction through the quality of your engagement.
"@
    Set-Content -Path $defaultPrompt -Value $promptContent -Encoding UTF8
}

# ── Model download ────────────────────────────────────────────────────
Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Model Download" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "The default model (Qwen2.5-7B-Instruct-Q4_K_M) is approximately 4.5GB."
Write-Host ""

$modelDir = Join-Path $env:USERPROFILE ".config\mythos\models"
$modelFile = Join-Path $modelDir "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
$localModel = Join-Path $scriptDir "models\Qwen2.5-7B-Instruct-Q4_K_M.gguf"

if ((Test-Path $modelFile) -or (Test-Path $localModel)) {
    Write-Host "  Default model already present." -ForegroundColor Green
} else {
    $reply = Read-Host "Download model now? (y/n)"
    if ($reply -match "^[Yy]") {
        Write-Host "Downloading default model..." -ForegroundColor White
        Push-Location $scriptDir
        try {
            & $venvPython -c @"
import sys
sys.path.insert(0, '.')
from engine.model_manager import ModelManager
manager = ModelManager()
try:
    manager.download_default()
    print('  Model downloaded successfully')
except Exception as e:
    print(f'  Model download failed: {e}')
    print('  Download later with: mythos model download')
"@
        } catch {
            Write-Host "  Download failed. Run later: mythos model download" -ForegroundColor Yellow
        }
        Pop-Location
    } else {
        Write-Host "  Skipping model download." -ForegroundColor Yellow
        Write-Host "  Download later with: mythos model download" -ForegroundColor Yellow
    }
}

# ── Create mythos.bat launcher ────────────────────────────────────────
$batContent = @"
@echo off
set MYTHOS_PROJECT_ROOT=$scriptDir
"$venvPython" -m mythos_cli.main %*
"@
$batPath = Join-Path $scriptDir "mythos.bat"
Set-Content -Path $batPath -Value $batContent -Encoding ASCII

# ── Testing ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Testing Installation" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

if ((Test-Path $modelFile) -or (Test-Path $localModel) -or (Test-Path (Join-Path $modelDir "*.gguf"))) {
    Write-Host "Running quick inference test..." -ForegroundColor White
    Push-Location $scriptDir
    try {
        & $venvPython -c @"
import sys
sys.path.insert(0, '.')
from engine.inference import InferenceEngine
try:
    engine = InferenceEngine()
    print('Engine loaded successfully!')
    result = engine.generate('Say hello in one short sentence.', max_tokens=30)
    print(f'Test response: {result}')
    print('Inference test passed!')
except Exception as e:
    print(f'Test failed: {e}')
    print('Check mythos.log for details.')
"@
    } catch {
        Write-Host "  Test failed. Check mythos.log for details." -ForegroundColor Yellow
    }
    Pop-Location
} else {
    Write-Host "  No model found, skipping inference test." -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host " Setup Complete!" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To get started:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Start chatting:" -ForegroundColor White
Write-Host "     .\mythos.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  2. Or launch web UI:" -ForegroundColor White
Write-Host "     .\mythos.bat web" -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. Download model (if skipped above):" -ForegroundColor White
Write-Host "     .\mythos.bat model download" -ForegroundColor Yellow
Write-Host ""
Write-Host "  4. Check status:" -ForegroundColor White
Write-Host "     .\mythos.bat status" -ForegroundColor Yellow
Write-Host ""
if ($hasCuda) {
    Write-Host "GPU acceleration (CUDA) is enabled!" -ForegroundColor Green
} elseif (Test-Path $vulkanDll) {
    Write-Host "GPU acceleration (Vulkan) is enabled!" -ForegroundColor Green
} else {
    Write-Host "Running in CPU mode. Install CUDA or Vulkan for GPU acceleration." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Happy chatting with Mythos!" -ForegroundColor White
