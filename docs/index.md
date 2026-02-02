---
layout: default
title: MLS Documentation
---

# Multi-Ion Lab System (MLS) Documentation

Welcome to the MLS documentation portal. This documentation covers the complete lab control framework for mixed-species ion trap experiments.

## Navigation

- [Architecture](architecture/) - System design and protocols
- [API Reference](api/) - Complete API documentation  
- [Guides](guides/) - User guides and tutorials
- [Hardware](hardware/) - Hardware integration
- [Development](development/) - Developer resources
- [Reference](reference/) - Technical reference

## Quick Links

- [System Overview](architecture/overview.md)
- [API Quick Reference](api/reference.md)
- [Safety Systems](guides/SAFETY_KILL_SWITCH.md)
- [Installation](guides/CONDA_SETUP.md)

## System Architecture

The MLS framework provides distributed control for ion trap experiments, coordinating:

- **ARTIQ** - Hardware control (DACs, DDS, TTL)
- **LabVIEW/SMILE** - High voltage RF, piezo, oven, e-gun control
- **Camera** - Image acquisition and processing
- **Two-Phase Optimizer** - TuRBO + MOBO Bayesian optimization
- **Web UI** - User interface and monitoring

---

*Documentation Version 2.0 - Last Updated: 2026-02-02*
