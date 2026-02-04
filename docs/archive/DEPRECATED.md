# Deprecated Documentation

The following documentation files in the root `docs/` directory are **deprecated** and will be removed in a future release. Please use the reorganized documentation structure instead.

## Deprecated Files

| Deprecated File | New Location | Status |
|-----------------|--------------|--------|
| `ARCHITECTURE.md` | [`architecture/overview.md`](architecture/overview.md) | ✅ Migrated |
| `API_REFERENCE.md` | [`api/reference.md`](api/reference.md) | ✅ Migrated |
| `COMMUNICATION_PROTOCOL.md` | [`architecture/communication.md`](architecture/communication.md) | ✅ Migrated |
| `DATA_INTEGRATION.md` | [`reference/data_formats.md`](reference/data_formats.md) | ✅ Migrated |
| `LABVIEW_INTEGRATION.md` | [`hardware/labview.md`](hardware/labview.md) | ✅ Migrated |
| `OPTIMIZATION_GUIDE.md` | [`reference/optimization.md`](reference/optimization.md) | ✅ Migrated |
| `BO.md` | [`reference/bo_architecture.md`](reference/bo_architecture.md) | ✅ Migrated |
| `SECULAR_COMPARISON.md` | [`reference/secular_comparison.md`](reference/secular_comparison.md) | ✅ Migrated |

## New Documentation Structure

```
docs/
├── README.md                    # Main documentation index
├── index.md                     # GitHub/GitLab pages support
├── DEPRECATED.md                # This file
├── architecture/                # System architecture
│   ├── README.md
│   ├── overview.md             # From ARCHITECTURE.md
│   └── communication.md        # From COMMUNICATION_PROTOCOL.md
├── api/                         # API documentation
│   ├── README.md
│   └── reference.md            # From API_REFERENCE.md
├── guides/                      # User guides (existing)
│   ├── CONDA_SETUP.md
│   ├── CAMERA_ACTIVATION.md
│   └── SAFETY_KILL_SWITCH.md
├── hardware/                    # Hardware integration
│   ├── README.md
│   ├── labview.md              # From LABVIEW_INTEGRATION.md
│   └── camera.md               # From CAMERA_HARDWARE.md
├── development/                 # Developer docs
│   ├── README.md
│   ├── naming_conventions.md   # From reference/NAMING_CONVENTIONS.md
│   └── testing.md              # From tests/TESTING.md
└── reference/                   # Reference materials
    ├── README.md
    ├── data_formats.md         # From DATA_INTEGRATION.md
    ├── optimization.md         # From OPTIMIZATION_GUIDE.md
    ├── bo_architecture.md      # From BO.md
    └── secular_comparison.md   # From SECULAR_COMPARISON.md
```

## Migration Guide

### For Users

1. Start with the new [`README.md`](README.md) for documentation navigation
2. Use the table of contents in each section's README
3. Update bookmarks to point to new locations

### For Developers

1. Update any internal links to point to new locations
2. The old files will be removed in version 3.0
3. See [`development/naming_conventions.md`](development/naming_conventions.md) for documentation conventions

## Timeline

- **2026-02-02**: New documentation structure created
- **2026-02-02**: Deprecated files marked (this document)
- **Version 2.5**: Deprecation warnings added to old files
- **Version 3.0**: Old files removed

## Questions?

If you can't find something in the new structure:
1. Check the main [`README.md`](README.md) navigation
2. Use the search function in your documentation viewer
3. Check the section README files for indexes
