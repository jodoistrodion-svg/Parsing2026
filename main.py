"""Process entry point for Parsing2026.

Keep startup wiring here; application logic belongs to app.application.
"""

import asyncio

from app.application import main


if __name__ == "__main__":
    asyncio.run(main())
