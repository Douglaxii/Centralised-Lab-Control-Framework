@echo off
REM ============================================================================
REM Server Setup Script - Optimized for Intel Core i9 + NVIDIA Quadro P400
REM ============================================================================

echo.
echo  ============================================
echo   Lab Control Framework - Server Setup
echo   Optimized for Intel Core i9 + NVIDIA Quadro P400
echo  ============================================
echo.

REM Check if running as administrator (optional but recommended)
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running with administrator privileges
) else (
    echo [INFO] Running without administrator privileges (should be fine)
)

REM Check Python version
echo.
echo [Step 1] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.10 or 3.11
    pause
    exit /b 1
)

for /f "tokens=2" %%I in ('python --version 2^>^&1') do set PYTHON_VERSION=%%I
echo [OK] Found Python %PYTHON_VERSION%

REM Check for Python 3.12 (numba compatibility)
echo %PYTHON_VERSION% | findstr "3.12" >nul
if %errorLevel% == 0 (
    echo [WARNING] Python 3.12 detected. Numba may not be fully supported yet.
    echo [WARNING] Consider using Python 3.10 or 3.11 for best compatibility.
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
)

cd /d "%~dp0"

REM Create virtual environment
echo.
echo [Step 2] Creating virtual environment...
if exist venv (
    echo [INFO] venv already exists. Remove it to recreate.
    choice /C YN /M "Remove existing venv and recreate"
    if errorlevel 2 goto :skip_venv
    rmdir /s /q venv
)

python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment created

:skip_venv

REM Activate virtual environment
echo.
echo [Step 3] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated

REM Upgrade pip
echo.
echo [Step 4] Upgrading pip and build tools...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [WARNING] pip upgrade had issues, continuing anyway...
)

REM Install numpy FIRST (important for BLAS detection)
echo.
echo [Step 5] Installing NumPy (optimized for Intel MKL if available)...
pip install numpy>=1.24.0
if errorlevel 1 (
    echo [ERROR] NumPy installation failed
    pause
    exit /b 1
)
echo [OK] NumPy installed

REM Install numba (JIT compiler for Intel Core i9)
echo.
echo [Step 6] Installing Numba (JIT compiler for Intel optimizations)...
pip install numba>=0.57.0 llvmlite>=0.40.0
if errorlevel 1 (
    echo [WARNING] Numba installation failed - will use pure Python fallback
    echo [WARNING] Performance will be reduced without Numba
    choice /C YN /M "Continue without Numba"
    if errorlevel 2 exit /b 1
) else (
    echo [OK] Numba installed
)

REM Install scipy (uses NumPy's BLAS)
echo.
echo [Step 7] Installing SciPy...
pip install scipy>=1.10.0
if errorlevel 1 (
    echo [ERROR] SciPy installation failed
    pause
    exit /b 1
)
echo [OK] SciPy installed

REM Install OpenCV
echo.
echo [Step 8] Installing OpenCV...
pip install opencv-python>=4.8.0
if errorlevel 1 (
    echo [ERROR] OpenCV installation failed
    pause
    exit /b 1
)
echo [OK] OpenCV installed

REM Install remaining packages
echo.
echo [Step 9] Installing remaining packages...
pip install pyyaml>=6.0 pyzmq>=25.0 flask>=2.3.0 h5py>=3.8.0 pandas>=2.0.0 matplotlib>=3.7.0
if errorlevel 1 (
    echo [WARNING] Some packages had installation issues
)

REM Install development packages
echo.
echo [Step 10] Installing development packages...
pip install pytest>=7.4.0 black>=23.0.0 pylint>=2.17.0

REM Run hardware detection
echo.
echo [Step 11] Detecting hardware capabilities...
python -c "
import sys
import numpy as np

print(f'Python: {sys.version}')
print(f'NumPy: {np.__version__}')
print(f'NumPy BLAS: {np.__config__.show()}')

# Check Numba
try:
    import numba
    print(f'Numba: {numba.__version__}')
    print(f'Numba threads: {numba.config.NUMBA_NUM_THREADS}')
    print(f'Numba SIMD: {numba.config.NUMBA_CPU_NAME}')
    print('[OK] Numba JIT compiler ready')
except ImportError:
    print('[WARNING] Numba not available')

# Check OpenCV
try:
    import cv2
    print(f'OpenCV: {cv2.__version__}')
    if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
        print(f'[OK] OpenCV CUDA available')
        cv2.cuda.setDevice(0)
        print(f'    GPU: {cv2.cuda.Device(0).name()}')
    else:
        print('[INFO] OpenCV CUDA not available (CPU mode)')
except Exception as e:
    print(f'[WARNING] OpenCV check failed: {e}')

# CPU info
try:
    import multiprocessing
    print(f'CPU cores: {multiprocessing.cpu_count()}')
except:
    pass
" 2>nul

echo.
echo  ============================================
echo   Setup Complete!
echo  ============================================
echo.
echo To activate the environment in the future, run:
echo    venv\Scripts\activate.bat
echo.
echo To test the optimized image handler:
echo    python tests\benchmark_image_handler.py
echo.
echo To start the parallel camera server:
echo    python server\cam\camera_server_parallel.py
echo.
pause
