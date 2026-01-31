# MLS Conda Environment Setup Guide

This guide explains how to set up the MLS (Multi-Ion Lab System) project using a Conda virtual environment with VS Code.

---

## Prerequisites

1. **Miniconda** or **Anaconda** installed
   - Download from: https://docs.conda.io/en/latest/miniconda.html
   - Verify installation: `conda --version`

2. **VS Code** installed
   - Download from: https://code.visualstudio.com/

3. **VS Code Extensions** (recommended)
   - Python (ms-python.python)
   - Pylance (ms-python.vscode-pylance)

---

## Quick Start (Automated)

### Option 1: Python Setup Script (Recommended)

```bash
# Navigate to the MLS directory
cd D:\MLS

# Run the setup script
python setup_conda.py

# Or with custom environment name
python setup_conda.py --env-name my-mls-env
```

### Option 2: Batch Script (Windows)

```cmd
cd D:\MLS
setup_conda.bat

# Or with custom environment name
setup_conda.bat my-mls-env
```

### Option 3: Manual Setup

```bash
# Create environment from environment.yml
conda env create -f environment.yml

# Activate environment
conda activate mls

# Verify installation
python -c "import flask, zmq, numpy, cv2; print('All OK!')"
```

---

## VS Code Configuration

### 1. Select Python Interpreter

After setup, VS Code should automatically detect the conda environment. If not:

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
2. Type "Python: Select Interpreter"
3. Choose `mls` (or your custom environment name)

### 2. Verify Terminal Integration

Open a new terminal in VS Code (`Ctrl+~`):

```bash
# The environment should auto-activate
# You should see (mls) in your prompt

# Verify
which python  # Should point to conda environment
python --version  # Should be 3.11.x
```

### 3. Use VS Code Tasks

Press `Ctrl+Shift+P` → "Run Task" to see available tasks:

- **Start All Services (Launcher)** - Runs launcher.py
- **Start Manager** - Runs manager only
- **Start Flask Server** - Runs Flask web interface
- **Start Camera Server** - Runs camera server
- **Run Tests** - Runs pytest on tests/
- **Format Code (Black)** - Formats all Python code
- **Lint Code (Pylint)** - Runs pylint checks
- **Clean Python Cache** - Removes __pycache__ directories

### 4. Debug Configurations

Press `F5` or go to Run → Start Debugging:

- **Python: Flask Server** - Debug Flask with auto-reload
- **Python: Manager** - Debug the manager
- **Python: Camera Server** - Debug camera server
- **Python: Launcher (All Services)** - Debug launcher
- **Launch All Services** - Compound config for all services

---

## Running MLS

### Method 1: Using VS Code Tasks (Recommended)

```bash
# Ctrl+Shift+P -> "Run Task" -> "Start All Services (Launcher)"
```

### Method 2: Using Terminal

```bash
# Ensure you're in the MLS directory and environment is activated
cd D:\MLS
conda activate mls

# Start all services
python launcher.py

# Or start individually in separate terminals:
python -m server.communications.manager
python -m server.Flask.flask_server
python -m server.cam.camera_server
```

### Method 3: Using Debug Mode

```bash
# Press F5 in VS Code and select "Launch All Services"
# This starts Manager, Camera, and Flask with debugging enabled
```

---

## Accessing the Dashboard

Once services are running:

1. **Web Dashboard**: http://localhost:5000
2. **Health Check**: http://localhost:5000/health
3. **API Status**: http://localhost:5000/api/status

---

## Environment Management

### Update Environment

After pulling changes that update `environment.yml`:

```bash
# Option 1: Using VS Code Task
# Ctrl+Shift+P -> "Run Task" -> "Update Conda Environment"

# Option 2: Command line
conda activate mls
conda env update -f environment.yml --prune
```

### Remove Environment

```bash
conda deactivate
conda env remove -n mls
```

### List Environments

```bash
conda env list
```

---

## Troubleshooting

### Issue: "conda command not found"

**Solution**: Add conda to your PATH or use Anaconda Prompt

```powershell
# Find where conda is installed
where conda
# or
Get-Command conda

# Add to PATH (adjust path as needed)
$env:PATH += ";C:\Users\YOURNAME\miniconda3\Scripts"
```

### Issue: "ModuleNotFoundError" after setup

**Solution**: Ensure environment is activated

```bash
# Check current Python
which python

# Should show something like:
# C:\Users\YOURNAME\miniconda3\envs\mls\python.exe

# If not, activate manually
conda activate mls
```

### Issue: VS Code not finding interpreter

**Solution**: Manually select interpreter

1. `Ctrl+Shift+P` → "Python: Select Interpreter"
2. Click "Enter interpreter path..."
3. Navigate to: `C:\Users\YOURNAME\miniconda3\envs\mls\python.exe`

### Issue: Port already in use

**Solution**: Kill existing processes or change ports

```bash
# Find process using port 5000 (Flask)
netstat -ano | findstr :5000

# Kill process (replace PID with actual number)
taskkill /PID <PID> /F
```

### Issue: ZMQ errors on startup

**Solution**: Check if ports are available in `config/settings.yaml`

```yaml
network:
  cmd_port: 5555      # Change if occupied
  data_port: 5556
  client_port: 5557
  camera_port: 5558
```

---

## File Structure

```
MLS/
├── .vscode/                    # VS Code configuration
│   ├── settings.json           # Editor and Python settings
│   ├── launch.json             # Debug configurations
│   ├── tasks.json              # Build and run tasks
│   └── extensions.json         # Recommended extensions
├── .env.example                # Environment variables template
├── environment.yml             # Conda environment specification
├── setup_conda.py              # Python setup script
├── setup_conda.bat             # Windows batch setup script
├── CONDA_SETUP.md              # This file
├── launcher.py                 # Main entry point
├── requirements.txt            # Pip dependencies (fallback)
└── ...
```

---

## VS Code Features

### IntelliSense & Autocompletion

- Full IntelliSense for Python with Pylance
- Auto-import suggestions
- Type checking enabled

### Code Quality

- **Black** formatter (formats on save)
- **Pylint** linting
- **MyPy** type checking

### Debugging

- Breakpoint support
- Variable inspection
- Call stack navigation
- Multi-process debugging

### Terminal Integration

- Auto-activates conda environment
- Keyboard shortcut: `` Ctrl+` ``

---

## Advanced Configuration

### Custom Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
# Edit .env with your settings
```

### Jupyter Notebooks

The environment includes Jupyter support:

```bash
# In VS Code, create a new file with .ipynb extension
# Or run from terminal:
jupyter notebook
```

### Adding New Packages

```bash
# Activate environment
conda activate mls

# Install via conda (preferred)
conda install package-name

# Or via pip
pip install package-name

# Update environment.yml
conda env export > environment.yml
```

---

## Support

For issues:
1. Check logs in `logs/` directory
2. Review [docs/](docs/) documentation
3. Run diagnostics: `python launcher.py --status`

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Activate env | `conda activate mls` |
| Deactivate env | `conda deactivate` |
| Start services | `python launcher.py` |
| Run tests | `pytest tests/` |
| Format code | `black .` |
| Lint code | `pylint server/ core/` |
| Clean cache | Remove `__pycache__` folders |

**VS Code Shortcuts:**
- `F5` - Start debugging
- `Ctrl+F5` - Run without debugging
- `Ctrl+Shift+P` - Command palette
- `` Ctrl+` `` - Toggle terminal
- `Ctrl+Shift+B` - Run build task
