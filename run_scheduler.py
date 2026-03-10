#!/usr/bin/env python3
"""Entry point for the scheduler service."""
import asyncio
from app.scheduler import TikTokScheduler

if __name__ == "__main__":
    scheduler = TikTokScheduler()
    try:
        asyncio.run(scheduler.start())
    except KeyboardInterrupt:
        scheduler.stop()
        print("Scheduler stopped by user")
