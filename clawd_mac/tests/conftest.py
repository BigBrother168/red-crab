# -*- coding: utf-8 -*-
"""pytest setup for the macOS tests: the repository root on sys.path (clawd_mac, clawd.py, ... import from there)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
