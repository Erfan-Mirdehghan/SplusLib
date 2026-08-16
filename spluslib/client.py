"""
High-level SplusClient wrapper for Soroush Plus userbot
"""

import asyncio
import os
import re
import sys
import time
from typing import (
    Optional, Union, List, Dict, Any, Callable, Awaitable, TypeVar,
    TYPE_CHECKING, overload,
)
from ._base import SoroushClient, events as splus_events
from ._base import errors as splus_errors
from ._base import helpers
from ._base import utils as splus_utils
from ._base.tl import types, functions

from . import events
from . import errors

if TYPE_CHECKING:
    # Only imported for static type-checking (Pylance/mypy). Zero
    # runtime cost/effect -- this whole block is skipped when the
    # module actually runs. It exists so on_message()/on_edited()/
    # on_update() can be given precise return types below, which is
    # what lets editors infer the type of an undecorated handler
    # parameter, e.g.:
    #
    #     @client.on_message()
    #     async def handler(msg):
    #         await msg.reply(...)  # msg is inferred as NewMessage.Event
    #
    # A generic `Callable` return type on the decorator (the old
    # signature) gives Pylance no link between the decorator and the
    # callback's parameter type, so autocomplete on `msg.` never had
    # anything to resolve against -- independent of whether
    # NewMessage.Event itself had a working stub.
    from ._base.events.newmessage import NewMessage as _NewMessageStub

    _MsgEvent = _NewMessageStub.Event
    _MsgHandler = Callable[[_MsgEvent], Awaitable[Any]]
else:
    # At runtime _F only needs to exist as a name (TypeVar() itself is
    # cheap and side-effect-free); its `bound=` is never evaluated
    # for anything real, so a plain Callable is enough here.
    _MsgHandler = Callable[..., Awaitable[Any]]

# NOTE: TypeVar must be created unconditionally (not inside
# `if TYPE_CHECKING`) -- Pylance evaluates the *type* of `_F` from
# this statement, but the name `_F` itself has to actually exist at
# runtime too, since `@overload`-decorated functions referencing it
# are still parsed and executed as real (if unused) function objects.
_F = TypeVar("_F", bound=_MsgHandler)


def _norm_chat_id(chat_id: Union[int, str, None]) -> Union[int, str, None]:
    """
    Normalize a chat/user id before handing it to get_input_entity().

    get_input_entity() only takes its fast, no-network path (cache
    lookup by numeric peer id) when it receives an actual `int`. If
    you pass the *same* id as a `str` -- e.g. "-1000023610475" instead
    of -1000023610475, which happens naturally since event objects
    like `msg.chat_id` hand you an int but it's easy to str()/format
    it along the way -- that int-cache branch is skipped, and the
    string instead falls through to username/phone/invite-link
    resolution, where a bare numeric string matches nothing and raises
    "Cannot find any entity corresponding to ...".

    This coerces any string that looks like a plain (optionally
    negative) integer into a real int first, so `"-1000023610475"`
    and `-1000023610475` behave identically. Actual usernames,
    "@name", phone numbers, "me"/"self", and invite links are left
    untouched and continue through the normal string resolution path.
    """
    if isinstance(chat_id, str):
        stripped = chat_id.strip()
        if stripped and (stripped[0] == '-' and stripped[1:].isdigit() or stripped.isdigit()):
            return int(stripped)
    return chat_id


def _human_size(num_bytes: float) -> str:
    """Format a byte count as a short human-readable string (KB/MB/GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f}{unit}" if unit != "B" else f"{int(num_bytes)}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}GB"


def _file_label(file: Union[str, bytes]) -> str:
    """A short label for progress output: the filename if we have a
    path, otherwise a generic placeholder for raw bytes/URLs."""
    if isinstance(file, str) and not file.startswith(("http://", "https://")):
        return os.path.basename(file) or file
    if isinstance(file, str):
        return file
    return "file"


def _make_console_progress_printer(label: str):
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
            f"({_human_size(sent)}/{_human_size(total)})"
        )
        sys.stdout.flush()
        if is_done:
            sys.stdout.write("\n")
            sys.stdout.flush()

    return _callback


def _resolve_progress_callback(
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
        return _make_console_progress_printer(_file_label(file))
    if callable(progress):
        return progress
    return None


def _finish_progress_line(file: Union[str, bytes], progress) -> None:
    """No-op placeholder kept for symmetry/readability at call sites;
    the console printer already emits its own trailing newline once
    sent >= total, so there is nothing extra to do here."""
    return


class SplusClient:
    """
    High-level client for Soroush Plus userbot.

    Usage:
        client = SplusClient("my_session")
        await client.start("+989123456789")

        @client.on_message()
        async def handler(event):
            await event.reply("Hello!")

        await client.run_until_disconnected()
    """

    def __init__(
        self,
        session_name: str = "splus_session",
        api_id: int = 1030400,
        api_hash: str = "6edb16cf88714a4e9a805e928c39c937",
        flood_sleep_threshold: float = 20.0,
        **kwargs
    ):
        """
        Initialize the client.

        Args:
            session_name: Name of the session file (without .session extension)
            api_id: API ID (default is Soroush Plus default)
            api_hash: API Hash (default is Soroush Plus default)
            flood_sleep_threshold: Auto-sleep on FloodWaitError below this threshold (seconds)
            **kwargs: Additional arguments passed to SoroushClient. Notably
                device_model -- shown as the device name in
                Settings > Devices on every logged-in client. Defaults
                to "<session_name> (SplusLib)" so each bot session is
                identifiable at a glance; pass device_model=... to
                override it.
        """
        kwargs.setdefault('device_model', f'{session_name} (SplusLib)')
        self._client = SoroushClient(
            session=session_name,
            api_id=api_id,
            api_hash=api_hash,
            flood_sleep_threshold=flood_sleep_threshold,
            **kwargs
        )
        self._started = False
        self._phone = None
        self._handlers = []

    # ==================== Connection & Lifecycle ====================

    async def start(
        self,
        phone: str = None,
        *,
        password: str = None,
        code_callback: Callable = None,
        force_sms: bool = False,
        first_name: str = 'New User',
        last_name: str = '',
        max_attempts: int = 3
    ) -> bool:
        """
        Connect and authorize the client using the robust built-in start method.

        Args:
            phone: Phone number with country code (e.g., "+989123456789")
            password: 2FA password if enabled
            code_callback: Callable that returns the verification code (for non-interactive use)
            force_sms: Force sending code via SMS
            first_name: First name for new account signup
            last_name: Last name for new account signup
            max_attempts: Max login attempts

        Returns:
            True if connected and authorized, False otherwise.
        """
        # Prepare code_callback if provided
        if code_callback is not None:
            if not callable(code_callback):
                raise ValueError('code_callback must be a callable that returns the code')

        # Use the underlying client's robust start() method
        # This handles all edge cases: reconnection, code resending, 2FA, etc.
        result = await self._client.start(
            phone=phone,
            password=password,
            force_sms=force_sms,
            code_callback=code_callback,
            first_name=first_name,
            last_name=last_name,
            max_attempts=max_attempts
        )

        self._started = True
        # NOTE: is_user_authorized() is async on the underlying engine --
        # `result` (what self._client.start() returns) is that same
        # engine instance, so this must always be awaited. A previous
        # version of this line called result.is_user_authorized()
        # without awaiting it whenever the attribute existed (which is
        # always), creating a coroutine that was never run/awaited --
        # that's what caused the "coroutine ... was never awaited"
        # RuntimeWarning some users saw, even though start() itself
        # still completed and returned a (nonsense/always-truthy) value.
        return await self._client.is_user_authorized()

    async def stop(self):
        """Disconnect the client gracefully."""
        if self._started:
            await self._client.disconnect()
            self._started = False

    async def run_until_disconnected(self):
        """Run the client until disconnected."""
        await self._client.run_until_disconnected()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    # ==================== Event Handlers ====================

    def on(self, event_type, *args, **kwargs):
        """
        Decorator to register an event handler using the underlying
        event classes directly (spluslib.events.NewMessage, etc).

        Usage:
            @client.on(events.NewMessage)
            async def handler(event):
                ...

            @client.on(events.NewMessage, pattern="^/start$")
            async def start_cmd(event):
                ...

        For most bots, the on_message()/on_edited()/on_callback()/etc
        shortcuts below are simpler and cover the same event types
        without needing to import spluslib.events at all.
        """
        def decorator(func: Callable):
            handler = self._client.add_event_handler(func, event_type(*args, **kwargs))
            self._handlers.append(handler)
            return func
        return decorator

    def add_event_handler(self, callback: Callable, event_type):
        """Add an event handler programmatically."""
        handler = self._client.add_event_handler(callback, event_type)
        self._handlers.append(handler)
        return handler

    def remove_event_handler(self, callback: Callable, event_type):
        """Remove an event handler."""
        self._client.remove_event_handler(callback, event_type)

    # ---- Simple named shortcuts, one per event type ------------------
    #
    # These are plain wrappers around on(events.X, ...) so you never
    # have to import spluslib.events yourself for the common case:
    #
    #     @bot.on_message()
    #     async def handler(event):
    #         await event.reply("hi")
    #
    #     @bot.on_message(pattern=r"^/start$")
    #     async def start_cmd(event):
    #         ...
    #
    # Every one of these accepts the same filter kwargs as the
    # matching spluslib.events.X class (pattern, chats, incoming,
    # outgoing, from_users, blacklist_chats, func, etc) -- see that
    # class's docstring for the full list, since they're passed
    # straight through.

    # -- Typed overloads (type-checker only) --------------------------
    #
    # @overload + a bare `...` body is the standard pattern Pylance
    # is built to read: it uses these signatures for inference and
    # completions, then ignores them at runtime in favour of the real
    # `def on_message(...)` implementation right below. This is what
    # actually lets `msg` in `async def handler(msg): await msg.reply`
    # get inferred as NewMessage.Event -- a plain `Callable` return
    # type has no per-decorator link to the callback's parameter, so
    # nothing was ever available for autocomplete to resolve against.
    @overload
    def on_message(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[_F], _F]: ...

    def on_message(self, *args, **kwargs):
        """Register a handler for new incoming/outgoing messages."""
        return self.on(events.NewMessage, *args, **kwargs)

    @overload
    def on_edited(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[_F], _F]: ...

    def on_edited(self, *args, **kwargs):
        """Register a handler for edited messages."""
        return self.on(events.MessageEdited, *args, **kwargs)

    @overload
    def on_update(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[_F], _F]: ...

    def on_update(self, *args, **kwargs):
        """
        Register a handler that fires for BOTH new messages and
        edited messages -- unlike on_message() (new only) or
        on_edited() (edits only). Useful when you don't care whether
        the message is new or was just edited, e.g. a moderation
        filter that should re-scan edited text too.

        Accepts the same filter kwargs as on_message()/on_edited()
        (pattern, chats, incoming, outgoing, from_users, etc), applied
        identically to both the new-message and edited-message streams.

            @bot.on_update(pattern=r"(?i)badword")
            async def moderate(event):
                # runs whether "badword" was in a brand new message
                # or was edited into an existing one
                await event.delete()
        """
        def decorator(func: Callable):
            for event_type in (events.NewMessage, events.MessageEdited):
                handler = self._client.add_event_handler(func, event_type(*args, **kwargs))
                self._handlers.append(handler)
            return func
        return decorator

    def on_deleted(self, *args, **kwargs):
        """Register a handler for deleted messages."""
        return self.on(events.MessageDeleted, *args, **kwargs)

    def on_read(self, *args, **kwargs):
        """Register a handler for read receipts (message seen)."""
        return self.on(events.MessageRead, *args, **kwargs)

    def on_reaction(self, *args, **kwargs):
        """Register a handler for reactions being added/changed/removed
        on a message. See events.MessageReaction for what's available
        on the event (total_count, added_by, get_reactions(), etc)."""
        return self.on(events.MessageReaction, *args, **kwargs)

    def on_chat_action(self, *args, **kwargs):
        """Register a handler for chat actions: user joined/left,
        title/photo changed, pinned message, group created, etc."""
        return self.on(events.ChatAction, *args, **kwargs)

    def on_user_update(self, *args, **kwargs):
        """Register a handler for user status updates (online/offline,
        typing, profile photo changed)."""
        return self.on(events.UserUpdate, *args, **kwargs)

    def on_callback(self, *args, **kwargs):
        """Register a handler for inline button (callback query)
        presses."""
        return self.on(events.CallbackQuery, *args, **kwargs)

    def on_inline(self, *args, **kwargs):
        """Register a handler for inline queries (@bot query)."""
        return self.on(events.InlineQuery, *args, **kwargs)

    def on_album(self, *args, **kwargs):
        """Register a handler for grouped media (albums)."""
        return self.on(events.Album, *args, **kwargs)

    def on_raw(self, *args, **kwargs):
        """Register a handler for raw, unprocessed updates -- for
        advanced use only; prefer the specific on_* methods above."""
        return self.on(events.Raw, *args, **kwargs)

    # ==================== Account Methods ====================

    async def get_me(self) -> Dict[str, Any]:
        """
        Get current account's info, including bio (which requires a
        separate full-user lookup -- the basic account object alone
        doesn't carry it).

        Returns:
            Dict with keys: id, first_name, last_name, username, phone, bio
        """
        me = await self._client.get_me()
        bio = ""
        try:
            full = await self._client(functions.users.GetFullUserRequest(id=me))
            bio = getattr(full.full_user, 'about', '') or ""
        except Exception:
            pass  # bio is a nice-to-have; don't fail get_me() over it
        return {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": me.phone,
            "bio": bio,
            "is_bot": me.bot,
            "is_premium": getattr(me, 'premium', False),
            "is_verified": getattr(me, 'verified', False),
        }

    async def update_profile(
        self,
        first_name: str = None,
        last_name: str = None,
        about: str = None
    ) -> bool:
        """Update profile information."""
        try:
            if first_name is not None or last_name is not None:
                await self._client(functions.account.UpdateProfileRequest(
                    first_name=first_name or "",
                    last_name=last_name or ""
                ))
            if about is not None:
                await self._client(functions.account.UpdateProfileRequest(about=about))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def update_username(self, username: str) -> bool:
        """Change username."""
        try:
            await self._client(functions.account.UpdateUsernameRequest(username=username))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def set_profile_photo(
        self,
        photo: Union[str, bytes],
        *,
        progress: Union[bool, Callable[[int, int], None], None] = True,
    ) -> bool:
        """Set your account's profile photo. `photo` can be a local
        file path, a URL, or raw bytes."""
        try:
            callback = _resolve_progress_callback(photo, progress)
            file = await self._client.upload_file(photo, progress_callback=callback)
            await self._client(functions.photos.UploadProfilePhotoRequest(file=file))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def delete_profile_photos(self, photo_ids: List[int] = None) -> bool:
        """Delete profile photos."""
        try:
            if photo_ids is None:
                photos = await self._client.get_profile_photos('me')
                photo_ids = [p.id for p in photos]
            await self._client(functions.photos.DeletePhotosRequest(id=photo_ids))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def block_user(
        self, chat_id: Union[int, str], *, only_stories: bool = False,
    ) -> bool:
        """
        Block a user (or a channel, to stop seeing its posts).

        Args:
            chat_id: The user/channel to block.
            only_stories: If True, only blocks them from your stories
                (they're still allowed to message you) instead of a
                full block.

        Returns:
            True on success.
        """
        try:
            await self._client(functions.contacts.BlockRequest(
                id=_norm_chat_id(chat_id),
                my_stories_from=only_stories or None,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def unblock_user(
        self, chat_id: Union[int, str], *, only_stories: bool = False,
    ) -> bool:
        """
        Unblock a previously-blocked user or channel.

        Args:
            chat_id: The user/channel to unblock.
            only_stories: If True, only undoes a stories-only block
                (see `block_user`'s only_stories).

        Returns:
            True on success.
        """
        try:
            await self._client(functions.contacts.UnblockRequest(
                id=_norm_chat_id(chat_id),
                my_stories_from=only_stories or None,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Group/Chat Settings Methods ====================
    #
    # These edit the GROUP's own title/photo/description -- not your
    # personal account profile (see update_profile/set_profile_photo
    # above for that). Works for both basic groups and channels/
    # supergroups; the right underlying request is picked automatically
    # based on the chat's type.
    #
    # All of these raise spluslib.errors.NotAdminError if the bot
    # account doesn't have permission to make the change, instead of
    # silently returning False.

    async def set_chat_title(self, chat_id: Union[int, str], title: str) -> bool:
        """
        Change a group/channel's title.

        Raises errors.NotAdminError if you don't have permission.
        """
        try:
            entity = await self._client.get_entity(_norm_chat_id(chat_id))
            if isinstance(entity, types.Channel):
                input_channel = await self._client.get_input_entity(entity)
                await self._client(functions.channels.EditTitleRequest(
                    channel=input_channel, title=title
                ))
            else:
                await self._client(functions.messages.EditChatTitleRequest(
                    chat_id=entity.id, title=title
                ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def set_chat_description(self, chat_id: Union[int, str], description: str) -> bool:
        """
        Change a group/channel's description/about text.

        Raises errors.NotAdminError if you don't have permission.
        """
        try:
            input_peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client(functions.messages.EditChatAboutRequest(
                peer=input_peer, about=description
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def set_chat_photo(
        self,
        chat_id: Union[int, str],
        photo: Union[str, bytes],
        *,
        progress: Union[bool, Callable[[int, int], None], None] = True,
    ) -> bool:
        """
        Set a group/channel's photo. `photo` can be a local file path,
        a URL, or raw bytes.

        Raises errors.NotAdminError if you don't have permission.
        """
        try:
            entity = await self._client.get_entity(_norm_chat_id(chat_id))
            callback = _resolve_progress_callback(photo, progress)
            uploaded = await self._client.upload_file(photo, progress_callback=callback)
            input_photo = types.InputChatUploadedPhoto(file=uploaded)

            if isinstance(entity, types.Channel):
                input_channel = await self._client.get_input_entity(entity)
                await self._client(functions.channels.EditPhotoRequest(
                    channel=input_channel, photo=input_photo
                ))
            else:
                await self._client(functions.messages.EditChatPhotoRequest(
                    chat_id=entity.id, photo=input_photo
                ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def delete_chat_photo(self, chat_id: Union[int, str]) -> bool:
        """
        Remove a group/channel's current photo (reverts to no photo).

        Raises errors.NotAdminError if you don't have permission.
        """
        try:
            entity = await self._client.get_entity(_norm_chat_id(chat_id))
            empty_photo = types.InputChatPhotoEmpty()

            if isinstance(entity, types.Channel):
                input_channel = await self._client.get_input_entity(entity)
                await self._client(functions.channels.EditPhotoRequest(
                    channel=input_channel, photo=empty_photo
                ))
            else:
                await self._client(functions.messages.EditChatPhotoRequest(
                    chat_id=entity.id, photo=empty_photo
                ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Chat/Dialog Methods ====================

    async def get_chats(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get list of dialogs/chats."""
        dialogs = await self._client.get_dialogs(limit=limit)
        return [self._dialog_to_dict(d) for d in dialogs]

    async def get_chat_info(self, chat_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """
        Get detailed info about a chat/group/channel, including fields
        that basic entity lookups don't have -- description, pinned
        message id, exact member/admin/online counts, invite link, and
        the chat photo, when available.
        """
        try:
            entity = await self._client.get_entity(_norm_chat_id(chat_id))
            info = self._entity_to_dict(entity)

            full = None
            if isinstance(entity, types.Channel):
                input_channel = await self._client.get_input_entity(entity)
                result = await self._client(functions.channels.GetFullChannelRequest(channel=input_channel))
                full = result.full_chat
            elif isinstance(entity, types.Chat):
                result = await self._client(functions.messages.GetFullChatRequest(chat_id=entity.id))
                full = result.full_chat

            if full is not None:
                info.update({
                    "description": getattr(full, 'about', '') or "",
                    "pinned_message_id": getattr(full, 'pinned_msg_id', None),
                    "has_photo": getattr(full, 'chat_photo', None) is not None,
                    "invite_link": getattr(getattr(full, 'exported_invite', None), 'link', info.get("invite_link")),
                })
                # Channel/supergroup-only extra counters
                if isinstance(entity, types.Channel):
                    info.update({
                        "participants_count": getattr(full, 'participants_count', info.get("participants_count")),
                        "admins_count": getattr(full, 'admins_count', None),
                        "banned_count": getattr(full, 'banned_count', None),
                        "kicked_count": getattr(full, 'kicked_count', None),
                        "online_count": getattr(full, 'online_count', None),
                        "slowmode_seconds": getattr(full, 'slowmode_seconds', None),
                    })

            return info
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_chat_members(
        self,
        chat_id: Union[int, str],
        limit: int = None,
        filter_admins: bool = False
    ) -> List[Dict[str, Any]]:
        """Get chat members with admin caching optimization."""
        from ._base.tl import types
        import time

        # Admin cache for performance
        if not hasattr(self, '_admin_cache'):
            self._admin_cache = {}
            self._admin_cache_ttl = 300  # 5 minutes

        entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
        chat_id_int = entity.chat_id if hasattr(entity, 'chat_id') else entity.channel_id

        if filter_admins:
            cache_key = str(chat_id_int)
            now = time.time()
            cached = self._admin_cache.get(cache_key)

            if cached and (now - cached['time']) < self._admin_cache_ttl:
                admin_ids = cached['ids']
            else:
                admin_ids = set()
                async for user in self._client.iter_participants(
                    entity,
                    filter=types.ChannelParticipantsAdmins()
                ):
                    admin_ids.add(user.id)
                self._admin_cache[cache_key] = {'ids': admin_ids, 'time': now}

            # Get all members and filter
            all_members = []
            async for user in self._client.iter_participants(entity, limit=limit):
                if user.id in admin_ids:
                    all_members.append(self._user_to_dict(user))
            return all_members

        # Get all members
        members = []
        async for user in self._client.iter_participants(entity, limit=limit):
            members.append(self._user_to_dict(user))
        return members

    async def is_admin(self, chat_id: Union[int, str], user_id: Union[int, str] = None) -> bool:
        """Check if a user is admin in a chat (with caching)."""
        if user_id is None:
            user_id = (await self.get_me())['id']

        members = await self.get_chat_members(chat_id, filter_admins=True)
        return any(m['id'] == user_id for m in members)

    async def get_banned_users(
        self,
        chat_id: Union[int, str],
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        """
        List users banned/kicked from a group or channel. (For banned
        conference-call participants, see get_banned_participants.)
        """
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            banned = []
            async for user in self._client.iter_participants(
                entity,
                limit=limit,
                filter=types.ChannelParticipantsKicked(q=''),
            ):
                banned.append(self._user_to_dict(user))
            return banned
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Contact Methods ====================

    async def add_contact(
        self,
        phone: str,
        first_name: str,
        last_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Add a contact to address book."""
        try:
            result = await self._client(functions.contacts.AddContactRequest(
                id=phone,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                add_phone_privacy_exception=True
            ))
            if result.users:
                return self._user_to_dict(result.users[0])
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_contacts(self) -> List[Dict[str, Any]]:
        """Get all contacts."""
        result = await self._client(functions.contacts.GetContactsRequest(hash=0))
        return [self._user_to_dict(u) for u in result.users]

    async def delete_contact(self, user_id: Union[int, str]) -> bool:
        """Delete a contact."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(user_id))
            await self._client(functions.contacts.DeleteContactsRequest(id=[entity]))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Chat Management ====================

    async def ban_member(
        self,
        chat_id: Union[int, str],
        user_id: Union[int, str],
        permanent: bool = True
    ) -> bool:
        """Ban/kick a member from chat."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))

            from datetime import datetime, timedelta, timezone
            until_date = None
            if not permanent:
                until_date = datetime.now(timezone.utc) + timedelta(days=366)

            await self._client.edit_permissions(
                entity, user,
                view_messages=permanent,
                until_date=until_date
            )
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def unban_member(self, chat_id: Union[int, str], user_id: Union[int, str]) -> bool:
        """Unban a member."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))
            await self._client.edit_permissions(entity, user)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def mute_member(
        self,
        chat_id: Union[int, str],
        user_id: Union[int, str],
        minutes: int = None
    ) -> bool:
        """Mute a member for specified minutes (None = forever)."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))

            from datetime import datetime, timedelta, timezone
            until_date = None
            if minutes:
                until_date = datetime.now(timezone.utc) + timedelta(minutes=minutes)

            await self._client.edit_permissions(
                entity, user,
                send_messages=False,
                until_date=until_date
            )
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def set_admin(
        self,
        chat_id: Union[int, str],
        user_id: Union[int, str],
        rank: str = "admin",
        **permissions
    ) -> bool:
        """Promote user to admin."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))

            default_perms = {
                'change_info': True,
                'post_messages': True,
                'edit_messages': True,
                'delete_messages': True,
                'ban_users': True,
                'invite_users': True,
                'pin_messages': True,
                'add_admins': False,
                'manage_call': True,
                'anonymous': False,
            }
            default_perms.update(permissions)

            await self._client.edit_admin(entity, user, title=rank, **default_perms)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def remove_admin(self, chat_id: Union[int, str], user_id: Union[int, str]) -> bool:
        """Demote admin to member."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))
            await self._client.edit_admin(entity, user, is_admin=False)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def create_channel(
        self,
        title: str,
        description: str = "",
        megagroup: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Create a channel or supergroup."""
        try:
            result = await self._client(functions.channels.CreateChannelRequest(
                title=title,
                about=description,
                megagroup=megagroup
            ))
            if result.chats:
                return self._entity_to_dict(result.chats[0])
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def create_group(
        self,
        title: str,
        users: List[Union[int, str]]
    ) -> Optional[Dict[str, Any]]:
        """Create a group with initial users."""
        try:
            input_users = []
            for u in users:
                input_users.append(await self._client.get_input_entity(u))

            result = await self._client(functions.messages.CreateChatRequest(
                users=input_users,
                title=title
            ))
            if result.chats:
                return self._entity_to_dict(result.chats[0])
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def leave_chat(self, chat_id: Union[int, str]) -> bool:
        """Leave a chat/channel."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client.delete_dialog(entity)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Message Methods ====================

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        *,
        reply_to: Union[int, str] = None,
        parse_mode: str = 'md',
        silent: bool = False,
        link_preview: bool = True,
        schedule: Any = None,
        formatting_entities: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a text message.

        `formatting_entities` lets you pass pre-built entities (e.g.
        from mention_user()) instead of markdown/HTML -- when given,
        `parse_mode` is ignored for this call, matching the underlying
        engine's behavior.
        """
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))

            msg = await self._client.send_message(
                entity,
                text,
                reply_to=reply_to,
                parse_mode=None if formatting_entities is not None else parse_mode,
                formatting_entities=formatting_entities,
                silent=silent,
                link_preview=link_preview,
                schedule=schedule
            )
            return self._message_to_dict(msg)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def mention_user(
        self,
        chat_id: Union[int, str],
        user_id: Union[int, str],
        *,
        text: str = None,
        extra_text: str = "",
        reply_to: Union[int, str] = None,
        silent: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message that mentions/tags a user by clickable name
        (like tapping "@" and picking them, works even if they have no
        username -- this is a MentionName entity, not @username text).

        Args:
            chat_id: Where to send the message.
            user_id: The user to mention (id, username, or "me").
            text: What the mention text itself should say. Defaults to
                their first name.
            extra_text: Extra text appended after the mention, e.g.
                mention_user(chat, uid, extra_text=", welcome!") sends
                "John, welcome!" with "John" clickable.
            reply_to: Message ID to reply to.
            silent: Send without notification sound.

        Returns:
            The sent message as a dict, or None on failure.

        Example:
            await bot.mention_user(chat_id, 123456789)
            # -> "John" (clickable), where John is their first name

            await bot.mention_user(chat_id, 123456789, text="the boss")
            # -> "the boss" (clickable, but still links to that user)
        """
        try:
            user_entity = await self._client.get_entity(_norm_chat_id(user_id))
            input_user = await self._client.get_input_entity(_norm_chat_id(user_id))
            mention_text = text or getattr(user_entity, 'first_name', None) or 'user'
            full_text = mention_text + extra_text

            entities = [types.MessageEntityMentionName(
                offset=0,
                length=len(mention_text),
                user_id=getattr(input_user, 'user_id', getattr(user_entity, 'id', None)),
            )]

            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            msg = await self._client.send_message(
                entity,
                full_text,
                reply_to=reply_to,
                parse_mode=None,
                formatting_entities=entities,
                silent=silent,
            )
            return self._message_to_dict(msg)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_messages(
        self,
        chat_id: Union[int, str],
        limit: int = 20,
        *,
        offset_id: int = 0,
        min_id: int = 0,
        max_id: int = 0,
        search: str = None,
        from_user: Union[int, str] = None
    ) -> List[Dict[str, Any]]:
        """Get messages from a chat."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))

            messages = []
            async for msg in self._client.iter_messages(
                entity,
                limit=limit,
                offset_id=offset_id,
                min_id=min_id,
                max_id=max_id,
                search=search,
                from_user=from_user
            ):
                messages.append(self._message_to_dict(msg))
            return messages
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_message_by_id(
        self,
        chat_id: Union[int, str],
        message_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a specific message by ID."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            msgs = await self._client.get_messages(entity, ids=[message_id])
            if msgs and msgs[0]:
                return self._message_to_dict(msgs[0])
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def delete_messages(
        self,
        chat_id: Union[int, str],
        message_ids: List[int],
        revoke: bool = True
    ) -> bool:
        """Delete messages."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client.delete_messages(entity, message_ids, revoke=revoke)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def edit_message(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        *,
        parse_mode: str = 'md',
        link_preview: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Edit a message."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))

            msg = await self._client.edit_message(
                entity,
                message_id,
                text,
                parse_mode=parse_mode,
                link_preview=link_preview
            )
            return self._message_to_dict(msg)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def forward_messages(
        self,
        chat_id: Union[int, str],
        message_ids: List[int],
        from_chat_id: Union[int, str]
    ) -> List[Dict[str, Any]]:
        """Forward messages."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            from_entity = await self._client.get_input_entity(_norm_chat_id(from_chat_id))

            if not isinstance(message_ids, list):
                message_ids = [message_ids]

            msgs = await self._client.forward_messages(
                entity, message_ids, from_entity
            )
            return [self._message_to_dict(m) for m in msgs]
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def pin_message(
        self,
        chat_id: Union[int, str],
        message_id: int,
        notify: bool = False
    ) -> bool:
        """Pin a message."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client.pin_message(entity, message_id, notify=notify)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def unpin_message(
        self,
        chat_id: Union[int, str],
        message_id: int = None
    ) -> bool:
        """Unpin a message or all messages."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client.unpin_message(entity, message_id)
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def react_message(
        self,
        chat_id: Union[int, str],
        message_id: int,
        emoji: str = "👍"
    ) -> bool:
        """React to a message."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client(functions.messages.SendReactionRequest(
                peer=entity,
                msg_id=message_id,
                reaction=[types.ReactionEmoji(emoticon=emoji)]
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_reactions(
        self,
        chat_id: Union[int, str],
        message_id: int
    ) -> Dict[str, Any]:
        """Get reactions on a message."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            result = await self._client(functions.messages.GetMessagesReactionsRequest(
                peer=entity,
                id=[message_id]
            ))
            return {
                "reactions": [
                    {
                        "emoji": r.reaction.emoticon if hasattr(r.reaction, 'emoticon') else str(r.reaction),
                        "count": r.count,
                        "chosen": r.chosen
                    }
                    for r in result.updates[0].reactions.results
                ] if result.updates else []
            }
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_chat_invite_link(
        self,
        chat_id: Union[int, str],
        *,
        title: str = None,
        expire_date=None,
        usage_limit: int = None,
        request_needed: bool = False,
    ) -> Optional[str]:
        """
        Get (create a fresh) invite link for a group or channel. You
        must have the "invite users" admin right in that chat.

        Args:
            chat_id: The group/channel.
            title: Optional label for this link (shown in admin's
                invite-link list, not to people who join with it).
            expire_date: Optional datetime/timestamp after which the
                link stops working.
            usage_limit: Optional max number of people who can join
                using this link.
            request_needed: If True, joins via this link go through
                admin approval instead of joining directly.

        Returns:
            The invite link URL (e.g. "https://splus.ir/joinchat/...")
            or None on failure.
        """
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            result = await self._client(functions.messages.ExportChatInviteRequest(
                peer=entity,
                title=title,
                expire_date=expire_date,
                usage_limit=usage_limit,
                request_needed=request_needed or None,
            ))
            return getattr(result, 'link', None)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    def _invite_to_dict(self, invite) -> Dict[str, Any]:
        """Convert a ChatInviteExported to dict."""
        return {
            "link": invite.link,
            "admin_id": invite.admin_id,
            "date": invite.date.timestamp() if invite.date else None,
            "revoked": bool(invite.revoked),
            "permanent": bool(invite.permanent),
            "request_needed": bool(invite.request_needed),
            "start_date": invite.start_date.timestamp() if invite.start_date else None,
            "expire_date": invite.expire_date.timestamp() if invite.expire_date else None,
            "usage_limit": invite.usage_limit,
            "usage": invite.usage,
            "requested": invite.requested,
            "title": invite.title,
        }

    async def get_chat_invite_links(
        self,
        chat_id: Union[int, str],
        *,
        revoked: bool = False,
        admin_id: Union[int, str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List existing invite links for a group/channel (as opposed to
        `get_chat_invite_link`, which always creates a brand new one).
        You must be an admin with the "invite users" right.

        Args:
            chat_id: The group/channel.
            revoked: If True, list revoked links instead of active ones.
            admin_id: Only list links created by this admin. Defaults
                to yourself.
            limit: Max number of links to return.

        Returns:
            A list of invite-link dicts (link, usage, expire_date,
            title, etc. -- see `_invite_to_dict`).
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            admin = await self._client.get_input_entity(_norm_chat_id(admin_id) if admin_id else 'me')
            admin_user = splus_utils.get_input_user(admin)

            result = await self._client(functions.messages.GetExportedChatInvitesRequest(
                peer=peer,
                admin_id=admin_user,
                limit=limit,
                revoked=revoked or None,
            ))
            return [
                self._invite_to_dict(inv) for inv in result.invites
                if isinstance(inv, types.ChatInviteExported)
            ]
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def edit_chat_invite_link(
        self,
        chat_id: Union[int, str],
        link: str,
        *,
        revoke: bool = False,
        title: str = None,
        expire_date=None,
        usage_limit: int = None,
        request_needed: bool = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Edit an existing invite link's settings, or revoke it.

        Args:
            chat_id: The group/channel.
            link: The exact invite link string to edit (from
                `get_chat_invite_links`).
            revoke: If True, revokes (deactivates) this link. Once
                revoked, a link can only be deleted, not re-activated.
            title, expire_date, usage_limit, request_needed: New
                values for these settings; leave as None to keep the
                current value unchanged.

        Returns:
            The updated invite-link dict, or None on failure.

        Example:
            # revoke a link
            await bot.edit_chat_invite_link(chat_id, link, revoke=True)

            # change its title
            await bot.edit_chat_invite_link(chat_id, link, title="New name")
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            result = await self._client(functions.messages.EditExportedChatInviteRequest(
                peer=peer,
                link=link,
                revoked=revoke or None,
                expire_date=expire_date,
                usage_limit=usage_limit,
                request_needed=request_needed,
                title=title,
            ))
            new_invite = getattr(result, 'new_invite', None) or getattr(result, 'invite', None)
            if isinstance(new_invite, types.ChatInviteExported):
                return self._invite_to_dict(new_invite)
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def delete_chat_invite_link(self, chat_id: Union[int, str], link: str) -> bool:
        """
        Permanently delete an invite link (it must be revoked first --
        see `edit_chat_invite_link(..., revoke=True)`).

        Args:
            chat_id: The group/channel.
            link: The exact invite link string to delete.

        Returns:
            True on success.
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client(functions.messages.DeleteExportedChatInviteRequest(
                peer=peer, link=link,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def check_chat_username(self, chat_id: Union[int, str], username: str) -> bool:
        """
        Check whether a username is available to set for a given
        group/channel you admin (i.e. not taken by someone else).

        Args:
            chat_id: The group/channel you're checking the username for.
            username: The username to check (without "@").

        Returns:
            True if it's available to use.
        """
        try:
            channel = await self._client.get_input_entity(_norm_chat_id(chat_id))
            result = await self._client(functions.channels.CheckUsernameRequest(
                channel=channel, username=username,
            ))
            return bool(result)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def set_chat_username(self, chat_id: Union[int, str], username: str) -> bool:
        """
        Set (or remove, with an empty string) the public username for
        a group/channel you admin.

        Args:
            chat_id: The group/channel.
            username: The new username (without "@"), or "" to make
                the chat private again.

        Returns:
            True on success.
        """
        try:
            channel = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client(functions.channels.UpdateUsernameRequest(
                channel=channel, username=username,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    def _join_request_to_dict(self, importer) -> Dict[str, Any]:
        """Convert a ChatInviteImporter to dict."""
        return {
            "user_id": importer.user_id,
            "date": importer.date.timestamp() if importer.date else None,
            "is_pending_request": bool(importer.requested),
            "via_chatlist": bool(importer.via_chatlist),
            "about": importer.about,
            "approved_by": importer.approved_by,
        }

    async def get_join_requests(
        self,
        chat_id: Union[int, str],
        *,
        link: str = None,
        query: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List pending join requests for a group/channel (people waiting
        for admin approval to join, e.g. via a "request to join" link).

        Args:
            chat_id: The group/channel.
            link: Only list requests made via this specific invite link.
            query: Filter by name/username search.
            limit: Max number of requests to return.

        Returns:
            A list of dicts: user_id, date, about (their join request
            message, if any), etc. -- see `_join_request_to_dict`.

        Example:
            requests = await bot.get_join_requests(chat_id)
            for req in requests:
                await bot.approve_join_request(chat_id, req["user_id"])
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            result = await self._client(functions.messages.GetChatInviteImportersRequest(
                peer=peer,
                offset_date=None,
                offset_user=types.InputUserEmpty(),
                limit=limit,
                requested=True,
                link=link,
                q=query,
            ))
            return [self._join_request_to_dict(imp) for imp in result.importers]
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def approve_join_request(self, chat_id: Union[int, str], user_id: Union[int, str]) -> bool:
        """
        Approve a pending join request.

        Args:
            chat_id: The group/channel.
            user_id: The requester's user id (from `get_join_requests`).

        Returns:
            True on success.
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))
            input_user = splus_utils.get_input_user(user)
            await self._client(functions.messages.HideChatJoinRequestRequest(
                peer=peer, user_id=input_user, approved=True,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def decline_join_request(self, chat_id: Union[int, str], user_id: Union[int, str]) -> bool:
        """
        Decline a pending join request.

        Args:
            chat_id: The group/channel.
            user_id: The requester's user id (from `get_join_requests`).

        Returns:
            True on success.
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            user = await self._client.get_input_entity(_norm_chat_id(user_id))
            input_user = splus_utils.get_input_user(user)
            await self._client(functions.messages.HideChatJoinRequestRequest(
                peer=peer, user_id=input_user, approved=False,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def decline_all_join_requests(self, chat_id: Union[int, str], *, link: str = None) -> bool:
        """
        Decline every pending join request for a chat at once
        (optionally scoped to just one invite link).

        Args:
            chat_id: The group/channel.
            link: Only decline requests made via this specific invite
                link; omit to decline all of them regardless of link.

        Returns:
            True on success.
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client(functions.messages.HideAllChatJoinRequestsRequest(
                peer=peer, approved=False, link=link,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """
        Look up an account by phone number and return its info: id,
        name, username, the private-chat id you'd message them at,
        bio, and a few status flags.

        The phone number must be in a resolvable international format,
        e.g. "+989123456789". Returns None if no account is registered
        with that number, or if the account's privacy settings don't
        allow it to be found this way.
        """
        try:
            phone = phone.strip()
            result = await self._client(functions.contacts.ResolvePhoneRequest(phone=phone))
            if not result.users:
                return None

            user = result.users[0]
            bio = ""
            try:
                full = await self._client(functions.users.GetFullUserRequest(id=user))
                bio = getattr(full.full_user, 'about', '') or ""
            except Exception:
                pass  # bio is a nice-to-have; don't fail the whole lookup over it

            return {
                "id": user.id,
                "chat_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username,
                "phone": user.phone,
                "bio": bio,
                "is_bot": user.bot,
                "is_verified": getattr(user, 'verified', False),
                "is_premium": getattr(user, 'premium', False),
                "is_contact": getattr(user, 'contact', False),
                "is_mutual_contact": getattr(user, 'mutual_contact', False),
            }
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Poll Methods ====================
    #
    # Sending a poll uses the same messages.SendMedia flow as send_file
    # (InputMediaPoll wraps a Poll the same way InputMediaUploadedDocument
    # wraps a file), so the same _get_response_message() plumbing applies
    # and the returned dict has a "poll" key you can read back with
    # get_poll_results / after a vote comes in via on_message.

    async def send_poll(
        self,
        chat_id: Union[int, str],
        question: str,
        options: List[str],
        *,
        is_anonymous: bool = True,
        allows_multiple_answers: bool = False,
        is_quiz: bool = False,
        correct_option: int = None,
        explanation: str = None,
        close_period: int = None,
        reply_to: Union[int, str] = None,
        silent: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a poll (or a quiz).

        Args:
            chat_id: Where to send the poll.
            question: The poll question.
            options: 2-10 answer strings.
            is_anonymous: If False, voters are public (shows in
                get_poll_results as public_voters). Default True to
                match how Soroush's own client creates polls.
            allows_multiple_answers: Let people pick more than one
                option. Ignored (forced False) if is_quiz=True, since
                a quiz always has exactly one correct answer.
            is_quiz: Make this a quiz instead of a regular poll --
                requires correct_option to be set.
            correct_option: 0-based index into `options` that's the
                correct answer. Required when is_quiz=True.
            explanation: Text shown after voting on a quiz (why the
                correct answer is correct). Only used if is_quiz=True.
            close_period: Auto-close the poll after this many seconds.
            reply_to: Message ID to reply to.
            silent: Send without notification sound.

        Returns:
            The sent message as a dict (see send_file's return shape),
            or None on failure.

        Example:
            await bot.send_poll(
                chat_id, "Best pizza topping?",
                ["Pepperoni", "Mushroom", "Pineapple (fight me)"],
            )

            # Quiz:
            await bot.send_poll(
                chat_id, "2 + 2 = ?", ["3", "4", "5"],
                is_quiz=True, correct_option=1,
                explanation="Basic arithmetic!",
            )
        """
        if not 2 <= len(options) <= 10:
            raise ValueError("A poll needs between 2 and 10 options")
        if is_quiz and correct_option is None:
            raise ValueError("is_quiz=True requires correct_option to be set")

        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))

            answers = [
                types.PollAnswer(text=text, option=bytes([i]))
                for i, text in enumerate(options)
            ]
            poll = types.Poll(
                id=helpers.generate_random_long(),
                question=question,
                answers=answers,
                public_voters=not is_anonymous,
                multiple_choice=allows_multiple_answers and not is_quiz,
                quiz=is_quiz or None,
                close_period=close_period,
            )
            media = types.InputMediaPoll(
                poll=poll,
                correct_answers=[bytes([correct_option])] if is_quiz else None,
                solution=explanation if is_quiz else None,
                solution_entities=[] if is_quiz and explanation else None,
            )

            request = functions.messages.SendMediaRequest(
                peer=entity,
                media=media,
                message="",
                silent=silent,
                reply_to=None if reply_to is None else types.InputReplyToMessage(reply_to),
            )
            msg = self._client._get_response_message(
                request, await self._client(request), entity
            )
            return self._message_to_dict(msg)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def vote_poll(
        self,
        chat_id: Union[int, str],
        message_id: int,
        option_indices: Union[int, List[int]],
    ) -> Dict[str, Any]:
        """
        Vote on a poll. `option_indices` is the 0-based index (or a
        list of indices, for polls with allows_multiple_answers=True)
        into the options as originally passed to send_poll.
        """
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            if isinstance(option_indices, int):
                option_indices = [option_indices]

            msg = await self._client.get_messages(entity, ids=message_id)
            if not msg or not getattr(msg, 'poll', None):
                raise errors.translate(ValueError("That message isn't a poll"))

            result = await self._client(functions.messages.SendVoteRequest(
                peer=entity,
                msg_id=message_id,
                options=[bytes([i]) for i in option_indices],
            ))
            return self._message_to_dict(
                self._client._get_response_message(None, result, entity)
            )
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def close_poll(
        self,
        chat_id: Union[int, str],
        message_id: int,
    ) -> Dict[str, Any]:
        """Close (stop accepting votes on) a poll you sent."""
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            msg = await self._client.get_messages(entity, ids=message_id)
            if not msg or not getattr(msg, 'poll', None):
                raise errors.translate(ValueError("That message isn't a poll"))

            closed_poll = types.Poll(
                id=msg.poll.poll.id,
                question=msg.poll.poll.question,
                answers=msg.poll.poll.answers,
                closed=True,
                public_voters=msg.poll.poll.public_voters,
                multiple_choice=msg.poll.poll.multiple_choice,
                quiz=msg.poll.poll.quiz,
            )
            request = functions.messages.EditMessageRequest(
                peer=entity,
                id=message_id,
                media=types.InputMediaPoll(poll=closed_poll),
            )
            result = await self._client(request)
            return self._message_to_dict(
                self._client._get_response_message(request, result, entity)
            )
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_poll_results(
        self,
        chat_id: Union[int, str],
        message_id: int,
    ) -> Dict[str, Any]:
        """
        Get the current results of a poll: vote counts per option,
        total voters, and whether it's closed.
        """
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
            msg = await self._client.get_messages(entity, ids=message_id)
            if not msg or not getattr(msg, 'poll', None):
                raise errors.translate(ValueError("That message isn't a poll"))

            poll_media = msg.poll
            summary = poll_media.poll
            results = poll_media.results

            options = []
            vote_results = {r.option: r for r in (results.results or [])}
            for answer in summary.answers:
                r = vote_results.get(answer.option)
                options.append({
                    "text": answer.text,
                    "voters_count": r.voters if r else 0,
                    "is_chosen": bool(r.chosen) if r else False,
                    "is_correct": bool(r.correct) if r else False,
                })

            return {
                "question": summary.question,
                "options": options,
                "total_voters": results.total_voters,
                "is_closed": bool(summary.closed),
                "is_quiz": bool(summary.quiz),
                "is_anonymous": not bool(summary.public_voters),
                "allows_multiple_answers": bool(summary.multiple_choice),
            }
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def search_messages(
        self,
        chat_id: Union[int, str],
        query: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search messages in a chat."""
        return await self.get_messages(chat_id, limit=limit, search=query)

    # ==================== File/Media Methods ====================

    async def send_file(
        self,
        chat_id: Union[int, str],
        file: Union[str, bytes],
        *,
        caption: str = "",
        reply_to: Union[int, str] = None,
        parse_mode: str = 'md',
        force_document: bool = False,
        supports_streaming: bool = False,
        voice_note: bool = False,
        video_note: bool = False,
        silent: bool = False,
        schedule: Any = None,
        thumb: Union[str, bytes] = None,
        spoiler: bool = False,
        progress: Union[bool, Callable[[int, int], None], None] = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Send any file (auto-detects type). `file` can be a local file
        path (e.g. "/home/me/photo.jpg"), a URL, or raw bytes -- all
        three work exactly as-is, no need to read the file into bytes
        yourself first.

        By default this prints a live upload progress bar to the
        console (percentage + a bar), since uploads of large files can
        otherwise look "stuck" with no feedback:

            await bot.send_file(chat_id, "/path/to/movie.mp4")
            # Uploading movie.mp4: [########------------]  42% (4.2/10.0 MB)

        Control this with `progress`:
            progress=True (default) -- built-in console progress bar
            progress=False          -- no progress output at all
            progress=some_function  -- your own callback, called as
                                        some_function(bytes_sent, total_bytes)
                                        (may be a regular or async function)

        `spoiler=True` sends a photo/video blurred behind a "tap to
        reveal" overlay, same as the spoiler toggle in the official
        apps when attaching media:

            await bot.send_photo(chat_id, "spoiler.jpg", spoiler=True)

        Only affects photos/videos sent as quick media (the default);
        has no effect on documents (force_document=True) or other file
        types like audio.

        Raises spluslib.errors.NotAdminError / NoPermissionError /
        InvalidMediaError / FileTooLargeError / etc on failure instead
        of silently returning None, so problems are never invisible.
        """
        try:
            entity = await self._client.get_input_entity(_norm_chat_id(chat_id))

            callback = _resolve_progress_callback(file, progress)

            msg = await self._client.send_file(
                entity,
                file,
                caption=caption,
                reply_to=reply_to,
                parse_mode=parse_mode,
                force_document=force_document,
                supports_streaming=supports_streaming,
                voice_note=voice_note,
                video_note=video_note,
                silent=silent,
                schedule=schedule,
                thumb=thumb,
                spoiler=spoiler or None,
                progress_callback=callback,
            )
            if callback is not None:
                _finish_progress_line(file, progress)
            return self._message_to_dict(msg)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def send_photo(
        self,
        chat_id: Union[int, str],
        photo: Union[str, bytes],
        *,
        caption: str = "",
        spoiler: bool = False,
        progress: Union[bool, Callable[[int, int], None], None] = True,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Send a photo. `photo` can be a local file path, a URL, or bytes.

        `spoiler=True` sends it blurred behind a "tap to reveal"
        overlay, same as the official apps' spoiler toggle.
        """
        return await self.send_file(chat_id, photo, caption=caption, spoiler=spoiler, progress=progress, **kwargs)

    async def send_video(
        self,
        chat_id: Union[int, str],
        video: Union[str, bytes],
        *,
        caption: str = "",
        supports_streaming: bool = True,
        progress: Union[bool, Callable[[int, int], None], None] = True,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Send a video. `video` can be a local file path, a URL, or bytes."""
        return await self.send_file(
            chat_id, video, caption=caption,
            supports_streaming=supports_streaming, progress=progress, **kwargs
        )

    async def send_document(
        self,
        chat_id: Union[int, str],
        document: Union[str, bytes],
        *,
        caption: str = "",
        force_document: bool = True,
        progress: Union[bool, Callable[[int, int], None], None] = True,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Send a document/file. `document` can be a local file path, a URL, or bytes."""
        return await self.send_file(
            chat_id, document, caption=caption,
            force_document=force_document, progress=progress, **kwargs
        )

    async def send_voice(
        self,
        chat_id: Union[int, str],
        voice: Union[str, bytes],
        *,
        caption: str = "",
        progress: Union[bool, Callable[[int, int], None], None] = True,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Send a voice message (playable inline, like a mic recording).
        `voice` can be a local file path, a URL, or bytes."""
        return await self.send_file(
            chat_id, voice, caption=caption, voice_note=True, progress=progress, **kwargs
        )

    async def send_audio(
        self,
        chat_id: Union[int, str],
        audio: Union[str, bytes],
        *,
        caption: str = "",
        progress: Union[bool, Callable[[int, int], None], None] = True,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Send an audio file (music player style, not a voice note).
        `audio` can be a local file path, a URL, or bytes."""
        return await self.send_file(chat_id, audio, caption=caption, progress=progress, **kwargs)

    async def download_media(
        self,
        message: Union[Dict, Any],
        file_path: str = None
    ) -> Optional[str]:
        """Download media from a message."""
        try:
            if isinstance(message, dict):
                # Get the actual message object from the client
                msg_obj = await self._client.get_messages(
                    await self._client.get_input_entity(_norm_chat_id(message['chat_id'])),
                    ids=[message['id']]
                )
                if msg_obj and msg_obj[0]:
                    message = msg_obj[0]
                else:
                    return None

            return await self._client.download_media(message, file=file_path)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def join_group_by_invite(
        self,
        invite_link: str
    ) -> Optional[Dict[str, Any]]:
        """
        Join a group or channel using an invite link.

        Args:
            invite_link: The invite link (e.g., "https://plus.soush.ir/joinchat/aaabbb..." or just the hash).

        Returns:
            Dict with chat info if successful, None otherwise.
        """
        try:
            # Extract hash from link
            hash = invite_link
            if 'http' in invite_link:
                # Assuming format: https://plus.soush.ir/joinchat/<hash>
                hash = invite_link.split('/')[-1]

            # Check the invite first (optional, but good for error handling)
            try:
                result = await self._client(functions.messages.CheckChatInviteRequest(hash=hash))
                # result can be ChatInvite or ChatInviteAlready
                if isinstance(result, types.ChatInviteAlready):
                    # Already a member, return chat info
                    chat = result.chat
                    return self._chat_to_dict(chat)
            except Exception:
                # If check fails, still try to join
                pass

            # Join the chat
            result = await self._client(functions.messages.ImportChatInviteRequest(hash=hash))
            if result.chats:
                return self._chat_to_dict(result.chats[0])
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Group Call Methods (Conference Calls) ====================

    async def create_group_call(
        self,
        title: str = "Group Call",
        chat_id: Union[int, str] = None,
        rtmp_stream: bool = False,
        schedule_date: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new group call (conference call).

        Args:
            title: Title for the group call.
            chat_id: Optional chat where the call will be created. If None,
                    creates a standalone group call with a meet link.
            rtmp_stream: Whether this is an RTMP stream.
            schedule_date: Schedule the call for later.

        Returns:
            Dict with call info if successful, None otherwise.
            Includes 'invite_link', 'meet_link', and 'invite_hash' (slug) if available.
            For standalone calls (no chat_id), returns a meet link like
            "https://splus.ir/meet/mkx-ofx-yfh" that can be shared with others.
        """
        try:
            # Soroush Plus conference version - must match what web client sends
            # Web client sends version "1.0.0" in createConferenceCall
            version = "1.0.0"

            # Create conference call
            result = await self._client(functions.conference.CreateConferenceCallRequest(
                version=version,
                name=title
            ))

            # Result is ConferenceCreated with slug
            if result and hasattr(result, 'slug'):
                slug = result.slug
                meet_link = f"https://splus.ir/meet/{slug}"

                # If chat_id is provided, send the link to the chat
                if chat_id is not None:
                    try:
                        entity = await self._client.get_input_entity(_norm_chat_id(chat_id))
                        # Send a message with the meet link to the chat
                        # The actual message sending can be done via send_message
                        pass
                    except Exception:
                        pass

                # Return call info with the meet link
                return {
                    "id": None,  # Will be filled after resolve
                    "access_hash": None,
                    "slug": slug,
                    "title": title,
                    "invite_link": meet_link,
                    "meet_link": meet_link,
                    "invite_hash": slug,
                    "chat_id": chat_id,
                    "created": True,
                    "version": version
                }
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def resolve_group_call(
        self,
        slug: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a group call by its slug (meet link hash).

        Args:
            slug: The slug from the meet link (e.g., "mkx-ofx-yfh").

        Returns:
            Dict with full call info including id, access_hash, participants, etc.
        """
        try:
            result = await self._client(functions.conference.ResolveConferenceCallRequest(
                slug=slug
            ))
            if result and hasattr(result, 'conference'):
                conf = result.conference
                # Handle wrapper type
                if hasattr(conf, 'conference'):
                    conf = conf.conference
                return self._conference_call_to_dict(conf, slug)
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def join_group_call(
        self,
        slug: str = None,
        meet_link: str = None,
        muted: bool = True,
        video_stopped: bool = True,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Join an existing group call (conference call).

        Args:
            slug: The slug from the meet link (e.g., "mkx-ofx-yfh").
            meet_link: Full meet link (e.g., "https://splus.ir/meet/mkx-ofx-yfh").
            muted: Join with microphone muted.
            video_stopped: Join with video stopped.
            max_retries: Maximum number of retries on FloodWaitError.

        Returns:
            Dict with call info if successful, None otherwise.
        """
        from ._base import errors as splus_errors

        # Extract slug from meet_link if provided
        if meet_link and not slug:
            if 'https://splus.ir/meet/' in meet_link:
                slug = meet_link.split('/meet/')[-1]
            else:
                slug = meet_link  # Assume it's just the slug

        if not slug:
            raise ValueError("Either slug or meet_link must be provided")

        # First resolve the conference call to get id and access_hash
        resolved = await self.resolve_group_call(slug)
        if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
            return None

        # Create InputConferenceCall
        conference = types.InputConferenceCall(
            id=resolved['id'],
            access_hash=resolved['access_hash']
        )

        # Join the conference call - use the correct version "1.0.0"
        version = "1.0.0"

        for attempt in range(max_retries):
            try:
                result = await self._client(functions.conference.JoinConferenceCallRequest(
                    version=version,
                    conference=conference
                ))

                # Result is Updates which may contain UpdateConferenceCallConnection
                # with LiveKit url and token for media streaming, AND
                # UpdateConferenceCall with the conference details, as two
                # SEPARATE updates in result.updates -- in either order.
                #
                # IMPORTANT: we must scan the whole list before deciding what
                # to return. An earlier version of this code returned as soon
                # as it saw UpdateConferenceCall, which meant that whenever
                # the server sent UpdateConferenceCall BEFORE
                # UpdateConferenceCallConnection (which it does, based on
                # real captured traffic), we'd return without ever looking
                # at the second update -- silently dropping the url/token
                # and making join_group_call look like it "didn't join".
                livekit_info = None
                conf_call_dict = None
                if result and result.updates:
                    print(f"DEBUG: Got {len(result.updates)} updates from JoinConferenceCallRequest")
                    for update in result.updates:
                        print(f"DEBUG: Update type: {type(update).__name__}")
                        # NOTE: generated TLObjects don't expose a '_' attribute (that key
                        # only exists in to_dict()'s output), so checking `update._` never
                        # matches and silently fails. Use isinstance against the real type.
                        if isinstance(update, types.UpdateConferenceCallConnection):
                            livekit_info = {
                                "url": update.url,
                                "token": update.token
                            }
                            print(f"DEBUG: Found LiveKit connection info: url={livekit_info['url'][:50] if livekit_info['url'] else None}...")
                        elif isinstance(update, types.UpdateConferenceCall):
                            # The conference might be the wrapper type (has .conference attr)
                            # or the real type (has .id directly)
                            conf_obj = update.conference
                            if hasattr(conf_obj, 'conference'):
                                # It's the wrapper type, get the real conference
                                conf_obj = conf_obj.conference
                            conf_call_dict = self._conference_call_to_dict(conf_obj, slug)

                    # Now that we've looked at every update, decide what to return.
                    if conf_call_dict:
                        if livekit_info:
                            conf_call_dict.update(livekit_info)
                        return conf_call_dict

                # If we only got the connection info without conference update
                if livekit_info:
                    resolved = await self.resolve_group_call(slug)
                    if resolved:
                        resolved.update(livekit_info)
                        return resolved

                return resolved  # Return resolved info at minimum

            except splus_errors.FloodWaitError as e:
                wait_seconds = e.seconds
                print(f"FloodWaitError: waiting {wait_seconds} seconds (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(wait_seconds)
                else:
                    raise errors.FloodWaitError(wait_seconds, original=e) from e
            except errors.SplusError:
                raise
            except Exception as e:
                raise errors.translate(e) from e

        return None

    async def leave_group_call(
        self,
        slug: str = None,
        meet_link: str = None
    ) -> bool:
        """
        Leave a group call (conference call).

        Args:
            slug: The slug from the meet link.
            meet_link: Full meet link (e.g., "https://splus.ir/meet/mkx-ofx-yfh").

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Extract slug from meet_link if provided
            if meet_link and not slug:
                if 'https://splus.ir/meet/' in meet_link:
                    slug = meet_link.split('/meet/')[-1]

            if not slug:
                return False

            # Resolve to get id and access_hash
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return False

            # Create InputConferenceCall
            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            await self._client(functions.conference.LeaveConferenceCallRequest(
                conference=conference
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def end_group_call(
        self,
        slug: str = None,
        meet_link: str = None
    ) -> bool:
        """
        End (discard) a group call (conference call).

        Args:
            slug: The slug from the meet link.
            meet_link: Full meet link (e.g., "https://splus.ir/meet/mkx-ofx-yfh").

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Extract slug from meet_link if provided
            if meet_link and not slug:
                if 'https://splus.ir/meet/' in meet_link:
                    slug = meet_link.split('/meet/')[-1]

            if not slug:
                return False

            # Resolve to get id and access_hash
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return False

            # Create InputConferenceCall
            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            await self._client(functions.conference.DiscardConferenceCallRequest(
                conference=conference
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_group_call_info(
        self,
        slug: str = None,
        meet_link: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get current group call info.

        Args:
            slug: The slug from the meet link.
            meet_link: Full meet link (e.g., "https://splus.ir/meet/mkx-ofx-yfh").

        Returns:
            Dict with call info if successful, None otherwise.
        """
        try:
            if meet_link and not slug:
                if 'https://splus.ir/meet/' in meet_link:
                    slug = meet_link.split('/meet/')[-1]

            if not slug:
                return None

            return await self.resolve_group_call(slug)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def mute_participant(
        self,
        slug: str,
        participant_id: str,
        track_id: str = None,
        muted: bool = True
    ) -> bool:
        """
        Mute/unmute a participant in group call.

        Args:
            slug: The slug from the meet link.
            participant_id: The participant ID to mute/unmute.
            track_id: Optional track ID (audio/video).
            muted: True to mute, False to unmute.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Resolve to get id and access_hash
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return False

            # Create InputConferenceCall
            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            # Create InputConferenceParticipant
            participant = types.InputConferenceParticipant(participant_id)

            # Create InputConferenceMediaTrack (default to audio if not specified)
            if track_id is None:
                track = types.InputConferenceMediaTrack("audio")
            else:
                track = types.InputConferenceMediaTrack(track_id)

            await self._client(functions.conference.MuteConferenceParticipantRequest(
                conference=conference,
                participant=participant,
                track=track
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def remove_participant(
        self,
        slug: str,
        participant_id: str
    ) -> bool:
        """
        Remove a participant from group call.

        Args:
            slug: The slug from the meet link.
            participant_id: The participant ID to remove.

        Returns:
            True if successful, False otherwise.
        """
        try:
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return False

            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            participant = types.InputConferenceParticipant(participant_id)

            await self._client(functions.conference.RemoveConferenceParticipantRequest(
                conference=conference,
                participant=participant
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def ban_participant(
        self,
        slug: str,
        user_id: Union[int, str],
        user_access_hash: int
    ) -> bool:
        """
        Ban a participant from group call.

        Args:
            slug: The slug from the meet link.
            user_id: The user ID to ban.
            user_access_hash: The user's access hash.

        Returns:
            True if successful, False otherwise.
        """
        try:
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return False

            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            peer = types.InputPeerUser(user_id=user_id, access_hash=user_access_hash)

            await self._client(functions.conference.BanConferenceParticipantRequest(
                conference=conference,
                peer=peer
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def unban_participant(
        self,
        slug: str,
        user_id: Union[int, str],
        user_access_hash: int
    ) -> bool:
        """
        Unban a participant from group call.

        Args:
            slug: The slug from the meet link.
            user_id: The user ID to unban.
            user_access_hash: The user's access hash.

        Returns:
            True if successful, False otherwise.
        """
        try:
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return False

            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            peer = types.InputPeerUser(user_id=user_id, access_hash=user_access_hash)

            await self._client(functions.conference.UnbanConferenceParticipantRequest(
                conference=conference,
                peer=peer
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_banned_participants(
        self,
        slug: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get list of banned participants.

        Args:
            slug: The slug from the meet link.

        Returns:
            List of banned participants if successful, None otherwise.
        """
        try:
            resolved = await self.resolve_group_call(slug)
            if not resolved or not resolved.get('id') or not resolved.get('access_hash'):
                return None

            conference = types.InputConferenceCall(
                id=resolved['id'],
                access_hash=resolved['access_hash']
            )

            result = await self._client(functions.conference.GetBannedConferenceParticipantsRequest(
                conference=conference
            ))

            if result and hasattr(result, 'participants'):
                return [self._participant_to_dict(p) for p in result.participants]
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_active_group_calls(
        self,
        limit: int = 20,
        offset: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get list of active conference calls.

        Args:
            limit: Maximum number of calls to return.
            offset: Pagination offset.

        Returns:
            Dict with active calls list if successful, None otherwise.
        """
        try:
            result = await self._client(functions.conference.GetActiveConferenceCallsRequest(
                limit=limit,
                offset=offset
            ))

            if result and hasattr(result, 'conference'):
                conferences = []
                for c in result.conference:
                    # Handle wrapper type
                    if hasattr(c, 'conference'):
                        c = c.conference
                    conferences.append(self._conference_call_to_dict(c))
                return {
                    "conferences": conferences,
                    "next_offset": getattr(result, 'next_offset', None)
                }
            return None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    def _conference_call_to_dict(self, conf, slug: str = None) -> Dict[str, Any]:
        """Convert ConferenceCall to dict."""
        meet_link = f"https://splus.ir/meet/{conf.slug}" if hasattr(conf, 'slug') and conf.slug else None

        return {
            "id": conf.id,
            "access_hash": conf.access_hash,
            "seq": getattr(conf, 'seq', None),
            "start_time": getattr(conf, 'start_time', None),
            "version": getattr(conf, 'version', None),
            "slug": getattr(conf, 'slug', slug),
            "owner": conf.owner.to_dict() if hasattr(conf, 'owner') and conf.owner else None,
            "name": getattr(conf, 'name', None),
            "invite_link": meet_link,
            "meet_link": meet_link,
            "invite_hash": getattr(conf, 'slug', slug),
        }

    def _participant_to_dict(self, participant) -> Dict[str, Any]:
        """Convert ConferenceParticipant to dict."""
        return {
            "peer": participant.peer.to_dict() if hasattr(participant, 'peer') and participant.peer else None,
            "id": getattr(participant, 'id', None),
        }

    # ==================== Story Methods ====================

    def _story_to_dict(self, story, peer_id: Union[int, str] = None) -> Dict[str, Any]:
        """Convert a StoryItem (or StoryItemSkipped/StoryItemDeleted) to dict."""
        if story is None:
            return None

        if isinstance(story, types.StoryItemDeleted):
            return {"id": story.id, "peer_id": peer_id, "is_deleted": True}

        if isinstance(story, types.StoryItemSkipped):
            return {
                "id": story.id,
                "peer_id": peer_id,
                "is_skipped": True,
                "date": story.date.timestamp() if story.date else None,
                "expire_date": story.expire_date.timestamp() if story.expire_date else None,
            }

        media = story.media
        return {
            "id": story.id,
            "peer_id": peer_id,
            "date": story.date.timestamp() if story.date else None,
            "expire_date": story.expire_date.timestamp() if story.expire_date else None,
            "caption": story.caption,
            "pinned": story.pinned,
            "is_public": story.public,
            "close_friends": story.close_friends,
            "noforwards": story.noforwards,
            "edited": story.edited,
            "out": story.out,
            "views_count": getattr(story.views, 'views_count', None) if story.views else None,
            "reactions_count": getattr(story.views, 'reactions_count', None) if story.views else None,
            "media": media.to_dict() if hasattr(media, 'to_dict') else None,
        }

    def _parse_story_reference(
        self, story_or_link: Union[str, int], story_id: int = None,
    ):
        """
        Normalize the different ways a story can be referenced into
        (peer, story_id).

        Accepts either:
          - (chat_id, story_id) -- the usual case, two separate args
          - a story link as the first arg, e.g.
            "https://splus.ir/username/s/123" or "username/s/123" --
            in which case `story_id` should be left as None

        Raises ValueError if a link is given but doesn't look like a
        valid story link (must end in "/s/<numeric id>").
        """
        if story_id is not None:
            return _norm_chat_id(story_or_link), story_id

        link = str(story_or_link).strip()
        # Strip protocol if present, e.g. "https://splus.ir/user/s/1" -> "splus.ir/user/s/1"
        link = re.sub(r'^https?://', '', link)
        # Strip a leading domain-like segment (has a dot, no slash before
        # it) so both "splus.ir/username/s/123" and a bare
        # "username/s/123" (no domain at all) end up the same: a plain
        # username has no dot, so it's left untouched by this step.
        link = re.sub(r'^[\w-]+\.[\w.-]+/', '', link)
        link = link.strip('/')

        match = re.match(r'^(?:i/story/(\d+)$|(.+)/s/(\d+)$)', link)
        if not match:
            raise ValueError(
                f"Doesn't look like a story link: {story_or_link!r}. "
                "Expected something like 'https://.../username/s/123' "
                "or pass (chat_id, story_id) as two separate arguments."
            )

        if match.group(1):
            # "i/story/123" form has no username in the link itself --
            # can't resolve who posted it from the link alone.
            raise ValueError(
                f"Story link {story_or_link!r} doesn't include a "
                "username, so the owner can't be resolved from the "
                "link alone. Pass (chat_id, story_id) instead."
            )

        username, sid = match.group(2), match.group(3)
        return username, int(sid)

    async def get_story_link(
        self, chat_id: Union[int, str], story_id: int = None,
    ) -> Optional[str]:
        """
        Get a shareable link (e.g. "https://splus.ir/username/s/123")
        for a story.

        Args:
            chat_id: The story owner (id, username, or "me").
            story_id: The story's id. If omitted, this fetches the
                user's active stories via `get_user_stories()` and
                uses the most recent one -- handy when you just want
                "a link to whatever they currently have up" without
                looking up the id yourself first.

        Returns:
            The link string, or None if there's no such story, if the
            user has no active stories (when story_id is omitted), or
            if the server rejects story links entirely for this peer
            (Splus returns a NOT_SUPPORTED error for some/all accounts
            here even when everything else about the story is fine --
            that's a server-side limitation, not something the request
            itself can work around, so it's treated as "no link
            available" rather than raising).

        Example:
            # link to a specific known story
            link = await bot.get_story_link(user_id, 123)

            # link to their current story, whatever it is
            link = await bot.get_story_link(user_id)
        """
        try:
            if story_id is None:
                stories = await self.get_user_stories(chat_id)
                active = [s for s in stories if not s.get("is_deleted")]
                if not active:
                    return None
                story_id = active[-1]["id"]

            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            try:
                result = await self._client(functions.stories.ExportStoryLinkRequest(
                    peer=peer, id=story_id,
                ))
            except splus_errors.RPCError as e:
                if e.message == 'NOT_SUPPORTED':
                    return None
                raise
            return getattr(result, 'link', None)
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def download_story(
        self,
        chat_id: Union[int, str],
        story_id: int,
        file_path: str = None,
        *,
        progress: Union[bool, Callable[[int, int], None], None] = True,
    ) -> Optional[str]:
        """
        Download a story's photo/video to disk (or into memory).

        Args:
            chat_id: The story owner (id, username, or "me").
            story_id: The story's id (from `get_user_stories()`'s
                "id" field, or `has_story()`'s "latest_story_id").
            file_path: Where to save it. If omitted, saves next to
                where the script runs using Splus's default naming.
                Pass `bytes` (the type itself, not a string) to get
                the raw bytes back in memory instead of writing a file.
            progress: Same as `send_file`'s -- True for a console
                progress bar (default), False for none, or your own
                callback(received_bytes, total_bytes).

        Returns:
            The saved file path (or bytes, if file_path=bytes), or
            None if the story has no downloadable media (e.g. a
            text-only story) or no longer exists.

        Example:
            path = await bot.download_story(user_id, story_id)
            print("saved to", path)

            # straight to memory
            data = await bot.download_story(user_id, story_id, bytes)
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            result = await self._client(functions.stories.GetStoriesByIDRequest(
                peer=peer, id=[story_id],
            ))
            if not result or not result.stories:
                return None

            story = result.stories[0]
            media = getattr(story, 'media', None)
            if media is None:
                # e.g. StoryItemDeleted/StoryItemSkipped, or a
                # text-only story with no attached photo/video
                return None

            callback = _resolve_progress_callback(file_path, progress)
            downloaded = await self._client.download_media(
                media, file=file_path, progress_callback=callback,
            )
            if callback is not None:
                _finish_progress_line(file_path, progress)
            return downloaded
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def get_user_stories(self, chat_id: Union[int, str]) -> List[Dict[str, Any]]:
        """
        Get a user's/chat's currently active stories.

        Args:
            chat_id: The user/chat to check (id, username, or "me").

        Returns:
            A list of story dicts (see `_story_to_dict`), empty if they
            have no active stories.

        Example:
            stories = await bot.get_user_stories(user_id)
            if stories:
                print(f"They have {len(stories)} active stories")
        """
        try:
            chat_id = _norm_chat_id(chat_id)
            peer = await self._client.get_input_entity(chat_id)
            result = await self._client(functions.stories.GetPeerStoriesRequest(peer=peer))
            if not result or not result.stories:
                return []

            return [
                self._story_to_dict(s, peer_id=chat_id)
                for s in result.stories.stories
            ]
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def has_story(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """
        Check whether a user/chat currently has an active story, and if
        so, return its info plus a shareable link.

        Args:
            chat_id: The user/chat to check (id, username, or "me").

        Returns:
            {
                "has_story": bool,
                "stories": [...],       # all their active stories (may be several)
                "latest_story_id": int | None,
                "link": str | None,     # link to the most recent story
            }

        Example:
            info = await bot.has_story(user_id)
            if info["has_story"]:
                print("They posted:", info["link"])
        """
        stories = await self.get_user_stories(chat_id)
        active = [s for s in stories if not s.get("is_deleted")]

        if not active:
            return {
                "has_story": False,
                "stories": [],
                "latest_story_id": None,
                "link": None,
            }

        latest = active[-1]
        link = None
        try:
            link = await self.get_story_link(chat_id, latest["id"])
        except errors.SplusError:
            pass

        return {
            "has_story": True,
            "stories": active,
            "latest_story_id": latest["id"],
            "link": link,
        }

    async def send_story_view(self, chat_id: Union[int, str], story_id: int) -> bool:
        """
        Mark a story as seen/viewed (equivalent to opening it in the app).

        Args:
            chat_id: The story owner (id, username, or "me").
            story_id: The story's id.

        Returns:
            True on success.
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            await self._client(functions.stories.IncrementStoryViewsRequest(
                peer=peer, id=[story_id],
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def send_story_reaction(
        self,
        chat_id: Union[int, str],
        story_id: int,
        emoji: Optional[str] = None,
        *,
        add_to_recent: bool = False,
    ) -> bool:
        """
        React to a story with an emoji (like double-tapping a story
        with a heart, or picking a reaction from the tray).

        Args:
            chat_id: The story owner (id, username, or "me").
            story_id: The story's id.
            emoji: The reaction emoji, e.g. "\U0001F525". Pass None to
                remove your current reaction on this story.
            add_to_recent: Whether to add this to your recently-used
                reactions tray.

        Returns:
            True on success.

        Example:
            await bot.send_story_reaction(user_id, story_id, "\u2764")
        """
        try:
            peer = await self._client.get_input_entity(_norm_chat_id(chat_id))
            reaction = types.ReactionEmoji(emoticon=emoji) if emoji else types.ReactionEmpty()
            await self._client(functions.stories.SendReactionRequest(
                peer=peer,
                story_id=story_id,
                reaction=reaction,
                add_to_recent=add_to_recent or None,
            ))
            return True
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    async def reply_to_story(
        self,
        chat_id_or_link: Union[int, str],
        story_id: int = None,
        text: str = "",
        *,
        parse_mode: str = 'md',
        silent: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Reply to a story with a text message (shows up in the owner's
        DMs as "replied to your story", same as swiping up on a story
        and typing).

        Can be called two ways:
            # by owner + story id
            await bot.reply_to_story(user_id, story_id, "nice!")

            # by story link
            await bot.reply_to_story("https://splus.ir/username/s/123", text="nice!")

        Note: the story link form only works for links that include a
        username (e.g. ".../username/s/123"); it can't resolve an
        owner from an "i/story/123"-style link with no username.

        Args:
            chat_id_or_link: The story owner (id/username/"me"), or a
                full story link/path as a single string.
            story_id: The story's id (omit when passing a link).
            text: The reply text.
            parse_mode: Markdown parsing mode for `text`.
            silent: Send without notification sound.

        Returns:
            The sent message as a dict, or None on failure.
        """
        try:
            owner, sid = self._parse_story_reference(chat_id_or_link, story_id)
            entity = await self._client.get_input_entity(owner)
            input_user = splus_utils.get_input_user(entity)

            if not text:
                raise ValueError("text is required to reply to a story")

            parsed_text, msg_entities = await self._client._parse_message_text(text, parse_mode)
            random_id = helpers.generate_random_long()

            request = functions.messages.SendMessageRequest(
                peer=entity,
                message=parsed_text,
                entities=msg_entities,
                random_id=random_id,
                reply_to=types.InputReplyToStory(user_id=input_user, story_id=sid),
                silent=silent or None,
            )
            result = await self._client(request)
            msg = self._client._get_response_message(request, result, entity)
            return self._message_to_dict(msg) if msg else None
        except errors.SplusError:
            raise
        except Exception as e:
            raise errors.translate(e) from e

    # ==================== Legacy Audio Streaming (DEPRECATED) ====================
    #
    # These three methods are placeholders left over from before
    # spluslib.call_audio.CallAudioSession existed, and always return
    # False without doing anything. Kept only so old code that imports
    # them doesn't crash with AttributeError.
    #
    # For actually joining a call and playing/switching/stopping audio,
    # use spluslib.call_audio.CallAudioSession instead:
    #
    #     from spluslib.call_audio import CallAudioSession
    #     call = await client.join_group_call(slug="...")
    #     session = CallAudioSession()
    #     await session.connect(call["url"], call["token"])
    #     await session.play("/path/to/song.mp3")

    async def start_audio_stream(
        self,
        chat_id: Union[int, str],
        audio_source: Union[str, bytes],
        repeat: bool = False
    ) -> bool:
        """
        DEPRECATED placeholder -- always returns False and does nothing.
        Use spluslib.call_audio.CallAudioSession.connect() + .play()
        instead; see the module docstring above.
        """
        return False

    async def play_audio_file(
        self,
        chat_id: Union[int, str],
        file_path: str
    ) -> bool:
        """
        DEPRECATED placeholder -- always returns False and does nothing.
        Use spluslib.call_audio.CallAudioSession.play() instead; see
        the module docstring above.
        """
        return False

    async def play_audio_queue(
        self,
        chat_id: Union[int, str],
        file_paths: List[str]
    ) -> bool:
        """
        DEPRECATED placeholder -- always returns False and does nothing.
        Use spluslib.call_audio.CallAudioSession.play() in a loop over
        your file list instead; see the module docstring above.
        """
        return False

    def _user_to_dict(self, user) -> Dict[str, Any]:
        """Convert User object to dict."""
        return {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "phone": getattr(user, 'phone', None),
            "is_bot": user.bot,
            "is_verified": getattr(user, 'verified', False),
            "is_premium": getattr(user, 'premium', False),
            "is_scam": getattr(user, 'scam', False),
            "is_fake": getattr(user, 'fake', False),
            "restriction_reason": getattr(user, 'restriction_reason', []),
        }

    def _chat_to_dict(self, chat) -> Dict[str, Any]:
        """Convert Chat/Channel to dict."""
        return {
            "id": chat.id,
            "title": getattr(chat, 'title', None) or getattr(chat, 'first_name', ''),
            "username": getattr(chat, 'username', None),
            "type": "channel" if hasattr(chat, 'broadcast') else "group" if hasattr(chat, 'megagroup') else "chat",
            "participants_count": getattr(chat, 'participants_count', None),
            "is_broadcast": getattr(chat, 'broadcast', False),
            "is_megagroup": getattr(chat, 'megagroup', False),
            "is_forum": getattr(chat, 'forum', False),
            "description": getattr(chat, 'about', ''),
            "invite_link": getattr(chat, 'invite_link', None),
        }

    def _entity_to_dict(self, entity) -> Dict[str, Any]:
        """Convert any entity to dict."""
        if isinstance(entity, types.User):
            return self._user_to_dict(entity)
        elif isinstance(entity, (types.Chat, types.Channel)):
            return self._chat_to_dict(entity)
        return {}

    def _dialog_to_dict(self, dialog) -> Dict[str, Any]:
        """Convert Dialog to dict."""
        entity = dialog.entity
        result = self._entity_to_dict(entity)
        result.update({
            "unread_count": dialog.unread_count,
            "unread_mentions": dialog.unread_mentions_count,
            "is_pinned": dialog.pinned,
            "top_message_id": dialog.top_message,
            "draft": dialog.draft.text if dialog.draft else None,
        })
        return result

    def _message_to_dict(self, message) -> Dict[str, Any]:
        """Convert Message to dict."""
        from_user = message.sender
        chat = message.chat

        return {
            "id": message.id,
            "text": message.text or message.message,
            "date": message.date.timestamp() if message.date else None,
            "from_id": from_user.id if from_user else None,
            "from_user": self._user_to_dict(from_user) if from_user else None,
            "chat_id": chat.id if chat else None,
            "chat": self._chat_to_dict(chat) if chat else None,
            "out": message.out,
            "mentioned": message.mentioned,
            "media_unread": message.media_unread,
            "silent": message.silent,
            "post": message.post,
            "from_scheduled": message.from_scheduled,
            "legacy": message.legacy,
            "edit_hide": message.edit_hide,
            "pinned": message.pinned,
            "noforwards": message.noforwards,
            "reply_to_msg_id": message.reply_to_msg_id,
            "via_bot_id": getattr(message, 'via_bot_id', None),
            "reactions": [
                {
                    "emoji": r.reaction.emoticon if hasattr(r.reaction, 'emoticon') else str(r.reaction),
                    "count": r.count,
                    "chosen": r.chosen
                }
                for r in (getattr(message, 'reactions', None).results if getattr(message, 'reactions', None) else [])
            ],
            "views": getattr(message, 'views', None),
            "forwards": getattr(message, 'forwards', None),
        }

    # Delegate other methods to underlying client
    def __getattr__(self, name):
        return getattr(self._client, name)