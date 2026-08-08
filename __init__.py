"""
spluslib - High-level Soroush Plus userbot library
A clean, simplified API for building userbots on Soroush Plus platform.

This package is fully self-contained: the underlying MTProto engine
(originally the standalone "spluspy" library, itself a Soroush Plus
fork of Telethon) lives inside this package at spluslib/_base/.
There is no separate "spluspy" pip package to install -- everything
ships in this one "spluslib" folder.

A handful of files inside _base/ do internal lazy imports like
`from spluspy import events` (a pattern inherited from Telethon, used
to avoid circular imports). Since spluspy no longer exists as an
installable top-level package, we register the vendored _base
package under the name "spluspy" in sys.modules before anything else
is imported, so those internal imports keep resolving correctly
without needing to patch every one of those call sites individually.
"""

import sys as _sys

from . import _base as _base_pkg

_sys.modules.setdefault("spluspy", _base_pkg)

from .client import SplusClient
from . import events
from . import errors
from .call_audio import CallAudioSession

__version__ = "1.0.0"
__author__ = "Erfan Mirdehghan"

__all__ = [
    "SplusClient",
    "events",
    "errors",
    "CallAudioSession",
]