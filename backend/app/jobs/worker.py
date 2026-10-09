"""Standalone worker: ``python -m app.jobs.worker`` (run several for more throughput) or ``--once`` to drain the queue."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from app.jobs.runner import drain, run_loop
from app.logging_config import configure_logging


async def _main(once: bool) -> None:
    if once:
        n = await drain()
        print(f"processed {n} job(s)")
        return
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    await run_loop(stop)


def main() -> None:
    parser = argparse.ArgumentParser(description="GeoTrace analysis worker")
    parser.add_argument("--once", action="store_true", help="drain the queue and exit")
    args = parser.parse_args()
    configure_logging()
    logging.getLogger(__name__).info("worker starting")
    asyncio.run(_main(args.once))


if __name__ == "__main__":
    main()
