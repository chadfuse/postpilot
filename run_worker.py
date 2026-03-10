#!/usr/bin/env python3
"""Entry point for the RQ worker service."""
import os
# Fix macOS fork() + Objective-C runtime conflict (required for RQ workers on macOS)
os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

from app.worker import main

if __name__ == "__main__":
    main()
