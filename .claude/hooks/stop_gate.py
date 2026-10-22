#!/usr/bin/env python3
"""Compatibility entry point; no transcript regex or stop_hook_active bypass."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".harness"))
from cli import hook

if __name__ == "__main__":
    raise SystemExit(hook("stop"))
