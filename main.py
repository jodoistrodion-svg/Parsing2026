"""Production process entry point for Parsing2026."""

import asyncio

from app.bootstrap import main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
