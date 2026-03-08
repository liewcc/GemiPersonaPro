@echo off
setlocal enabledelayedexpansion

:: Project: GemiPersona
:: Purpose: Automated environment setup using uv

echo [1/5] Checking for uv installation...
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] uv is not installed. 
    echo Please run: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b
)

echo [2/5] Initializing Python 3.12 environment in .venv...
:: We use 3.12 here for maximum compatibility with AI libraries
uv venv --python 3.12

echo [3/5] Installing dependencies...
set /p gpu_choice=">>> Enable GPU (NVIDIA CUDA) acceleration? [Y/N]: "
if /i "%gpu_choice%"=="Y" (
    echo [INFO] Installing PyTorch with CUDA 12.1 support...
    uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
)

echo [INFO] Installing standard requirements...
uv pip install -r requirements.txt

echo [INFO] Installing Playwright browser binaries...
set NODE_NO_WARNINGS=1
.venv\Scripts\python -m playwright install chromium
set NODE_NO_WARNINGS=

echo [4/5] Downloading AI Models (LaMa)...
:: Run the refiner script directly to trigger download (shows progress bar)
.venv\Scripts\python lama_refiner.py
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Model download/initialization failed.
    echo If you see "OSError: [WinError 126]", Microsoft Visual C++ Redistributable is missing.
    echo Please download and install it from: 
    echo https://aka.ms/vs/17/release/vc_redist.x64.exe
    pause
    exit /b
)

echo [5/5] Setup Complete!
echo --------------------------------------------------
echo To start your Streamlit app, run:
echo .venv\Scripts\activate
echo streamlit run HOME.py
echo --------------------------------------------------
pause