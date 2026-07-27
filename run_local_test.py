"""Local-only launcher for Windows dev testing.

ProactorEventLoop (asyncio's default on Windows) fails to establish outbound
HTTPS connections to api.telegram.org via aiohttp in this environment
(ConnectionResetError / WinError 121) even though plain curl works fine.
SelectorEventLoop doesn't have this problem. This file is Windows/local-dev
only — the production server runs main.py directly and never touches this.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from main import main

if __name__ == "__main__":
    asyncio.run(main())
