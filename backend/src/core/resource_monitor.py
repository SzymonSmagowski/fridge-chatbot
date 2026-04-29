"""Lightweight CPU/RAM logger for diagnosing local pegging.

Sampled in a background asyncio task. Logs once every `interval_seconds` to the
shared stdlib logger. Disabled by default; turn on with the
`BACKEND_RESOURCE_MONITOR=1` env var (read by `Settings`).

Why a custom probe instead of `top`/`htop`?  The dev-container's `top` reports
the whole container, not just the uvicorn worker. This isolates the FastAPI
process so a CPU spike can be attributed correctly.
"""
from __future__ import annotations

import asyncio
import os

import psutil

from src.services.logger import get_logger

logger = get_logger("resource_monitor")


async def run_resource_monitor(
    *, stop_event: asyncio.Event, interval_seconds: float = 5.0
) -> None:
    proc = psutil.Process(os.getpid())
    # First call to cpu_percent() with interval=None returns 0.0; prime it so
    # the first real sample is meaningful.
    proc.cpu_percent(interval=None)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except asyncio.TimeoutError:
            pass

        try:
            cpu_pct = proc.cpu_percent(interval=None)
            mem_mib = proc.memory_info().rss / (1024 * 1024)
            num_threads = proc.num_threads()
            num_fds = proc.num_fds() if hasattr(proc, "num_fds") else -1
            logger.info(
                "[resource] cpu=%.1f%% rss=%.0fMiB threads=%d fds=%d",
                cpu_pct,
                mem_mib,
                num_threads,
                num_fds,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            logger.warning("resource_monitor sample failed: %s", exc)
            return
