"""
Shared, dependency-free progress-bar helpers used by both SplusClient
(spluslib.client, MTProto) and BotClient (spluslib.bot_client, HTTP Bot
API) for their `progress=` kwargs on file-sending methods.

This module only uses the standard library on purpose -- it must not
import anything from spluslib._base (the MTProto engine, which needs
pyaes/rsa/pysocks) or from spluslib.bot_client (which needs aiohttp),
so that importing SplusClient never requires aiohttp and importing
BotClient never requires pyaes/rsa/pysocks.
"""

import os
import sys
import time
from typing import Callable, Optional, Union


def human_size(num_bytes: float) -> str:
    """Format a byte count as a short human-readable string (KB/MB/GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f}{unit}" if unit != "B" else f"{int(num_bytes)}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}GB"


def file_label(file: Union[str, bytes]) -> str:
    """A short label for progress output: the filename if we have a
    path, otherwise a generic placeholder for raw bytes/URLs."""
    if isinstance(file, str) and not file.startswith(("http://", "https://")):
        return os.path.basename(file) or file
    if isinstance(file, str):
        return file
    return "file"


def make_console_progress_printer(label: str):
    """
    Build a progress_callback(sent, total) that prints a live-updating
    single-line progress bar to the console, e.g.:

        Uploading song.mp3: [##########----------]  50% (2.4/4.8 MB)

    Throttled to at most ~10 updates/second so it doesn't spam the
    terminal on fast local uploads.
    """
    state = {"last_print": 0.0}

    def _callback(sent: int, total: int) -> None:
        now = time.monotonic()
        is_done = total > 0 and sent >= total
        if not is_done and (now - state["last_print"]) < 0.1:
            return
        state["last_print"] = now

        pct = int(sent * 100 / total) if total else 0
        bar_width = 20
        filled = int(bar_width * pct / 100)
        bar = "#" * filled + "-" * (bar_width - filled)
        sys.stdout.write(
            f"\rUploading {label}: [{bar}] {pct:3d}% "
            f"({human_size(sent)}/{human_size(total)})"
        )
        sys.stdout.flush()
        if is_done:
            sys.stdout.write("\n")
            sys.stdout.flush()

    return _callback


def resolve_progress_callback(
    file: Union[str, bytes],
    progress: Union[bool, Callable[[int, int], None], None],
) -> Optional[Callable]:
    """
    Turn the `progress=` argument accepted by send_file/send_photo/etc
    into an actual progress_callback to hand to the underlying engine.

    progress=True (default) -> built-in console progress bar
    progress=False / None   -> no progress reporting
    progress=<callable>     -> that callable, used as-is (called with
                                (bytes_sent, total_bytes); may be sync
                                or async)
    """
    if progress is False or progress is None:
        return None
    if progress is True:
        return make_console_progress_printer(file_label(file))
    if callable(progress):
        return progress
    return None


def finish_progress_line(file: Union[str, bytes], progress) -> None:
    """No-op placeholder kept for symmetry/readability at call sites;
    the console printer already emits its own trailing newline once
    sent >= total, so there is nothing extra to do here."""
    return
