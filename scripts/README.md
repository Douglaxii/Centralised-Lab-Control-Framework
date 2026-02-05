# MLS Scripts

Utility scripts for the Multi-Species Loading System.

## Scripts

### `setup_env.py`

Environment detection and directory setup.

```bash
python scripts/setup_env.py          # Auto-detect environment
python scripts/setup_env.py --dev    # Force development mode
python scripts/setup_env.py --prod   # Force production mode
python scripts/setup_env.py --check  # Check current setup
```

### `switch_env.py`

Switch between development and production environments.

```bash
python scripts/switch_env.py         # Show current environment
python scripts/switch_env.py dev     # Switch to development
python scripts/switch_env.py prod    # Switch to production
```

## Usage

Run scripts from the project root:

```bash
cd /path/to/mls
python scripts/setup_env.py
python scripts/switch_env.py dev
```
