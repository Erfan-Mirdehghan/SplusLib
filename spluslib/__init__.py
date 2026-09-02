"""
spluslib - High-level Soroush Plus library: SplusClient (MTProto userbot)
and BotClient (official HTTP Bot API).

This package is fully self-contained: the underlying MTProto engine
(originally the standalone "spluspy" library, itself a Soroush Plus
fork of Telethon) lives inside this package at spluslib/_base/.
There is no separate "spluspy" pip package to install -- everything
ships in this one "spluslib" folder.

A single `pip install spluslib` installs everything needed for BOTH
clients -- there's no separate "bot" vs "userbot" package to choose
between, and no extras required for either one to work:

    from spluslib import BotClient      # HTTP Bot API client
    from spluslib import SplusClient    # MTProto userbot client

SplusClient (logs in as a real account) and BotClient (logs in as a bot
with a token from splus.ir/fatherbot) are otherwise independent code
paths -- BotClient never touches the MTProto engine (`_base`) at all.
That engine, along with `events`/`CallAudioSession`, is still loaded
*lazily* here (on first access of the name, not at `import spluslib`
time) purely so a process that only uses BotClient doesn't pay the
cost of importing the much larger MTProto/TL layer -- not because of
any missing-dependency concern, since both are installed together now.
"""

import sys as _sys

__version__ = "3.0.0"
__author__ = "Erfan Mirdehghan"

__all__ = [
    "SplusClient",
    "BotClient",
    "BotMessage",
    "BotCallbackQuery",
    "events",
    "errors",
    "CallAudioSession",
    "inline_keyboard",
    "reply_keyboard",
    "remove_keyboard",
    "force_reply",
]

_MTPROTO_NAMES = {"SplusClient", "events", "CallAudioSession"}
_BOT_NAMES = {
    "BotClient", "BotMessage", "BotCallbackQuery",
    "inline_keyboard", "reply_keyboard", "remove_keyboard", "force_reply",
}
# errors is intentionally in neither set above -- spluslib.errors has no
# MTProto/_base dependency at all (its one RPC-error mapping table is
# itself built lazily, see errors.py), so it's imported directly and
# unconditionally right here, safe for both SplusClient and BotClient
# code (including bot_client.py's own `from . import errors`) to rely on.
from . import errors

_mtproto_loaded = False


def _load_mtproto():
    """
    Import the vendored MTProto engine (spluslib/_base/, a Soroush
    Plus fork of Telethon) and everything built on it (SplusClient,
    events, errors, CallAudioSession), exactly once.

    A handful of files inside _base/ do internal lazy imports like
    `from spluspy import events` (a pattern inherited from Telethon,
    used to avoid circular imports). Since spluspy no longer exists as
    an installable top-level package, we register the vendored _base
    package under the name "spluspy" in sys.modules before anything
    else is imported, so those internal imports keep resolving
    correctly without needing to patch every one of those call sites
    individually.
    """
    global _mtproto_loaded
    if _mtproto_loaded:
        return
    _mtproto_loaded = True

    from . import _base as _base_pkg
    _sys.modules.setdefault("spluspy", _base_pkg)

    from .client import SplusClient
    from . import events

    globals()["SplusClient"] = SplusClient
    globals()["events"] = events

    # CallAudioSession depends on the optional `livekit` package
    # (install with `pip install spluslib[calls]` or `pip install
    # livekit` directly). Only needed for joining conference calls and
    # playing audio in them -- imported lazily here too so a missing
    # `livekit` doesn't break SplusClient/events/errors, which don't
    # need it at all.
    try:
        from .call_audio import CallAudioSession
        globals()["CallAudioSession"] = CallAudioSession
    except ImportError:
        globals()["CallAudioSession"] = None


def __getattr__(name):
    if name in _MTPROTO_NAMES:
        _load_mtproto()
        value = globals().get(name)
        if name == "CallAudioSession" and value is None:
            raise ImportError(
                "CallAudioSession requires the optional 'livekit' package. "
                "Install it with: pip install spluslib[calls]  "
                "(or: pip install livekit)"
            )
        return value

    if name in _BOT_NAMES:
        from . import bot_client as _bot_client_mod
        value = getattr(_bot_client_mod, name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")