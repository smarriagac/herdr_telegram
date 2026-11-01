#!/usr/bin/env python3
"""Herdr Telegram Bridge daemon entry point.

Clean Architecture wrapper maintaining backward-compatibility with
systemd, launchd, and Windows Task Scheduler scripts.
"""

import os
import sys

# Ensure current script directory is in sys.path to resolve 'bridge'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from bridge.main import main

if __name__ == "__main__":
    main()
