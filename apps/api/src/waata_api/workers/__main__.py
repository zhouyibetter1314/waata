"""Start the WAATA C6 worker process."""

import asyncio
import logging
import signal
from contextlib import suppress

from waata_api.infrastructure.config import Settings

from .runtime import run_worker


async def _run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    await run_worker(Settings.from_env(), stop)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except (ValueError, RuntimeError):
        logging.getLogger(__name__).error(
            "Worker startup failed; check the model, deployment and database configuration"
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
