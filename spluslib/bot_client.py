"""
BotClient -- high-level wrapper for Soroush Plus's official HTTP Bot API
(api.splus.ir/bot<token>/METHOD), completely separate from SplusClient.

SplusClient (spluslib.client.SplusClient) logs into a real user account
over MTProto (the vendored engine in spluslib/_base) and can do anything a
person can do in the app. BotClient instead authenticates as a *bot*, the
same way Telegram bots do, over plain HTTPS/JSON -- there is no MTProto,
no session file, no phone number. You get a bot token from
`splus.ir/fatherbot` (Soroush Plus's equivalent of @BotFather) and that
token is the only credential BotClient needs.

The Soroush Plus Bot API is intentionally a byte-for-byte clone of the
Telegram Bot API: same method names, same JSON field names, same object
shapes, same parse_mode syntax -- only the base URL differs
(api.splus.ir instead of api.telegram.org). BotClient mirrors that: every
method on the real API is reachable in two ways:

    1. Generic passthrough -- works for literally every method the API
       has, including ones not explicitly wrapped below, with the exact
       official parameter names:

           await bot.call("sendDice", chat_id=chat_id, emoji="🎯")
           await bot.call("getMe")

       `BotClient.__getattr__` also forwards unknown attribute access
       to `call()`, so `await bot.sendDice(chat_id=..., emoji="🎯")` and
       `await bot.getMe()` work directly too -- exactly the official
       method names, camelCase and all, so existing Telegram Bot API
       example code needs only the token/base URL changed to run here.

    2. Hand-written snake_case convenience wrappers for the most common
       methods (send_message, send_photo, get_updates, ...), which
       accept local file paths/URLs/raw bytes directly (no manual byte
       reading), support progress bars for uploads the same way
       SplusClient does, and return plain dicts.

Use whichever style fits -- they hit the same HTTP endpoint underneath.
"""

import asyncio
import inspect
import json as _json
import mimetypes
import os
import sys as _sys
import time
from typing import Any, Callable, Dict, List, Optional, Union

try:
    import aiohttp
    from aiohttp import web as aiohttp_web  # NOT auto-available on the `aiohttp` module itself
except ImportError:  # pragma: no cover
    aiohttp = None
    aiohttp_web = None

from . import errors
from ._progress import (
    human_size as _human_size,
    file_label as _file_label,
    make_console_progress_printer as _make_console_progress_printer,
    resolve_progress_callback as _resolve_progress_callback,
)

DEFAULT_BASE_URL = "https://api.splus.ir"
DEFAULT_FILE_BASE_URL = "https://api.splus.ir/file"


def _require_aiohttp():
    if aiohttp is None:
        raise ImportError(
            "BotClient requires the 'aiohttp' package. Install it with: "
            "pip install aiohttp"
        )


async def _maybe_await(value):
    """Call-site helper: await value if it's awaitable (an async
    handler/filter), otherwise just return it (a sync one). Lets every
    handler/filter/on_error callback be either sync or async."""
    if inspect.isawaitable(value):
        return await value
    return value


class BotMessage(dict):
    """
    A `Message` dict (as documented for the Bot API) with a few
    convenience additions on top -- it's a real `dict` subclass, so
    everything that works on a plain dict still works identically
    (`msg["text"]`, `"photo" in msg`, `json.dumps(msg)`, `.get(...)`,
    iterating it, etc), but you also get:

        msg.chat_id          # shortcut for msg["chat"]["id"]
        msg.text              # shortcut for msg.get("text")
        msg.message_id         # shortcut for msg["message_id"]
        await msg.reply("...")            # sendMessage to this chat
        await msg.reply_photo(photo=...)  # sendPhoto to this chat, etc

    `reply_*` methods mirror the BotClient.send_* method they wrap
    (same kwargs, minus chat_id which is filled in for you), and
    additionally default `reply_to_message_id` to this message's id
    unless you pass reply_to_message_id=None explicitly.
    """

    def __init__(self, data: dict, bot: "BotClient"):
        super().__init__(data)
        self._bot = bot

    @property
    def chat_id(self) -> Optional[int]:
        chat = self.get("chat")
        return chat.get("id") if chat else None

    @property
    def message_id(self) -> Optional[int]:
        return self.get("message_id")

    @property
    def text(self) -> Optional[str]:
        return self.get("text")

    @property
    def sender_id(self) -> Optional[int]:
        sender = self.get("from")
        return sender.get("id") if sender else None

    def _reply_kwargs(self, kwargs: dict) -> dict:
        kwargs.setdefault("reply_to_message_id", self.message_id)
        return kwargs

    async def reply(self, text: str, **kwargs) -> Dict[str, Any]:
        return await self._bot.send_message(self.chat_id, text, **self._reply_kwargs(kwargs))

    async def reply_photo(self, photo: Union[str, bytes], **kwargs) -> Dict[str, Any]:
        return await self._bot.send_photo(self.chat_id, photo, **self._reply_kwargs(kwargs))

    async def reply_audio(self, audio: Union[str, bytes], **kwargs) -> Dict[str, Any]:
        return await self._bot.send_audio(self.chat_id, audio, **self._reply_kwargs(kwargs))

    async def reply_document(self, document: Union[str, bytes], **kwargs) -> Dict[str, Any]:
        return await self._bot.send_document(self.chat_id, document, **self._reply_kwargs(kwargs))

    async def reply_video(self, video: Union[str, bytes], **kwargs) -> Dict[str, Any]:
        return await self._bot.send_video(self.chat_id, video, **self._reply_kwargs(kwargs))

    async def reply_voice(self, voice: Union[str, bytes], **kwargs) -> Dict[str, Any]:
        return await self._bot.send_voice(self.chat_id, voice, **self._reply_kwargs(kwargs))

    async def reply_animation(self, animation: Union[str, bytes], **kwargs) -> Dict[str, Any]:
        return await self._bot.send_animation(self.chat_id, animation, **self._reply_kwargs(kwargs))

    async def reply_dice(self, **kwargs) -> Dict[str, Any]:
        return await self._bot.send_dice(self.chat_id, **self._reply_kwargs(kwargs))

    async def delete(self) -> bool:
        return await self._bot.delete_message(self.chat_id, self.message_id)

    async def get_file_and_download(
        self, destination: Optional[str] = None,
    ) -> Optional[Union[str, bytes]]:
        """
        Convenience for the common "download whatever file is
        attached to this message" case -- looks at photo/audio/
        document/video/voice/video_note/animation/sticker (in that
        priority order) and downloads whichever is present. Returns
        None if this message has no file attached at all.
        """
        file_id = None
        for key in ("document", "video", "audio", "voice", "video_note", "animation", "sticker"):
            if key in self and self[key]:
                file_id = self[key]["file_id"]
                break
        if file_id is None and self.get("photo"):
            file_id = self["photo"][-1]["file_id"]  # largest size
        if file_id is None:
            return None
        return await self._bot.download_file(file_id, destination)


class BotCallbackQuery(dict):
    """
    A `CallbackQuery` dict with convenience additions -- a real `dict`
    subclass, same deal as BotMessage. On top of `msg["data"]`,
    `msg["from"]`, etc, you get:

        query.data              # shortcut for query.get("data")
        query.chat_id            # shortcut for the originating message's chat id, if present
        await query.answer(text="Got it!")  # answerCallbackQuery for this press
    """

    def __init__(self, data: dict, bot: "BotClient"):
        super().__init__(data)
        self._bot = bot

    @property
    def data(self) -> Optional[str]:
        return self.get("data")

    @property
    def message(self) -> Optional["BotMessage"]:
        msg = self.get("message")
        return BotMessage(msg, self._bot) if msg else None

    @property
    def chat_id(self) -> Optional[int]:
        msg = self.get("message")
        return msg["chat"]["id"] if msg and "chat" in msg else None

    @property
    def sender_id(self) -> Optional[int]:
        sender = self.get("from")
        return sender.get("id") if sender else None

    async def answer(self, *, text: str = None, show_alert: bool = None,
                      url: str = None, cache_time: int = None) -> bool:
        return await self._bot.answer_callback_query(
            self["id"], text=text, show_alert=show_alert, url=url, cache_time=cache_time,
        )


class _FileInput:
    """
    Internal marker wrapping a value the caller passed for a file-type
    parameter (photo=, document=, audio=, ...), so _call() knows to
    switch to multipart/form-data and how to read the bytes.

    Accepts, same as SplusClient's send_file/send_photo/etc:
      - a local file path (str not starting with http(s)://)
      - a URL (str starting with http:// or https://) -- passed straight
        through as a string value instead of being uploaded, since the
        Bot API accepts URLs directly for most file parameters (matching
        Telegram's behavior exactly)
      - raw bytes
      - an existing file_id string from a previous upload -- also just
        passed straight through as a string value
    """

    __slots__ = ("value", "field_name")

    def __init__(self, value: Union[str, bytes], field_name: str):
        self.value = value
        self.field_name = field_name

    @property
    def is_upload(self) -> bool:
        """True if this needs to actually be uploaded as multipart
        (a local path or raw bytes) rather than passed as a plain
        string value (a URL or an existing file_id)."""
        if isinstance(self.value, (bytes, bytearray)):
            return True
        if isinstance(self.value, str) and self.value.startswith(("http://", "https://")):
            return False
        if isinstance(self.value, str) and os.path.isfile(self.value):
            return True
        # Not a URL and not an existing local file -- most likely an
        # existing file_id string the caller got back from a previous
        # upload/message; pass through as-is.
        return False


class BotClient:
    """
    Client for Soroush Plus's official HTTP Bot API.

    Usage:
        bot = BotClient("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

        @bot.on_message()
        async def handler(message):
            await bot.send_message(message["chat"]["id"], "Hello!")

        async def main():
            await bot.run_polling()

        asyncio.run(main())

    Or without polling, just calling methods directly:

        async def main():
            me = await bot.get_me()
            print(me)
            await bot.send_message(chat_id, "Hi")
            await bot.close()   # release the aiohttp session when done

    Get a token from `splus.ir/fatherbot` (Soroush Plus's equivalent of
    @BotFather). Nothing here touches MTProto or the vendored `_base`
    engine at all -- this is a plain HTTPS/JSON client, same as
    `python-telegram-bot`/`aiogram`/etc would be for a Telegram bot.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        file_base_url: str = DEFAULT_FILE_BASE_URL,
        request_timeout: float = 60.0,
        connector: Optional["aiohttp.BaseConnector"] = None,
        debug: bool = False,
    ):
        _require_aiohttp()
        if not token or ":" not in token:
            raise ValueError(
                "That doesn't look like a valid bot token. Get one from "
                "splus.ir/fatherbot -- it looks like "
                "'123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'."
            )
        self.token = token
        self._base_url = base_url.rstrip("/")
        self._file_base_url = file_base_url.rstrip("/")
        self._request_timeout = request_timeout
        self._connector = connector
        self._session: Optional["aiohttp.ClientSession"] = None
        # debug=True prints every outgoing request (method, form field
        # names, file field names/sizes) and the full raw response body
        # to stderr -- turn this on when an error message alone (like a
        # bare "NOT_SUPPORTED") isn't enough to tell what's wrong.
        self._debug = debug

        self._message_handlers: List[tuple] = []
        self._edited_message_handlers: List[tuple] = []
        self._callback_query_handlers: List[tuple] = []
        self._inline_query_handlers: List[tuple] = []
        self._update_handlers: List[Callable] = []  # fires on every update, any type

        self._polling = False
        self._webhook_running = False
        self._webhook_runner: Optional["aiohttp_web.AppRunner"] = None
        self._me: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # Low-level transport
    # ------------------------------------------------------------------ #

    def _api_url(self, method: str) -> str:
        return f"{self._base_url}/bot{self.token}/{method}"

    async def _get_session(self) -> "aiohttp.ClientSession":
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=None)  # per-call timeout set below
            self._session = aiohttp.ClientSession(connector=self._connector, timeout=timeout)
        return self._session

    async def close(self):
        """Release the underlying HTTP session. Call this when you're
        done with the bot (not required if your process just exits)."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.close()

    async def call(self, method: str, **params) -> Any:
        """
        Call any Bot API method by its exact official name, with its
        exact official parameter names, e.g.:

            await bot.call("sendMessage", chat_id=chat_id, text="hi")
            await bot.call("sendDice", chat_id=chat_id, emoji="🎯")

        File-type parameters (photo=, document=, audio=, video=,
        animation=, voice=, video_note=, sticker=, certificate=) accept
        a local path, raw bytes, or a URL/file_id string, exactly like
        the snake_case convenience methods -- this is what they call
        internally. Local files are streamed from disk (not read fully
        into memory first). Returns whatever's in the response's
        "result" field (already JSON-decoded: a dict, a list, a
        bool, ...).

        Raises `errors.BotAPIError` if the API responds with
        `ok: false`, or `errors.FloodWaitError` specifically for 429
        rate-limit responses (`.seconds` is the API's `retry_after`).
        """
        session = await self._get_session()
        url = self._api_url(method)

        file_fields = {
            k: v for k, v in params.items()
            if isinstance(v, _FileInput) and v.is_upload
        }

        # Drop Nones and serialize non-string values the way the HTTP
        # Bot API expects (JSON-encoded strings for dict/list params
        # like reply_markup, entities, etc; everything else as str()).
        # File inputs that are NOT uploads (a URL or file_id string)
        # are converted to their plain string value here too.
        form_params = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, _FileInput):
                if value.is_upload:
                    continue  # handled via file_fields below
                value = value.value
            if isinstance(value, (dict, list)):
                value = _json.dumps(value, ensure_ascii=False)
            elif isinstance(value, bool):
                value = "true" if value else "false"
            else:
                value = str(value)
            form_params[key] = value

        timeout = aiohttp.ClientTimeout(total=self._request_timeout)
        opened_files = []  # closed in `finally` below

        try:
            if file_fields:
                # Equivalent of requests.post(url, data=form_params, files=files) --
                # aiohttp.FormData builds the multipart/form-data body
                # (with boundary) for us.
                data = aiohttp.FormData()
                for k, v in form_params.items():
                    data.add_field(k, v)

                debug_files = []
                for field_name, file_input in file_fields.items():
                    value = file_input.value
                    if isinstance(value, (bytes, bytearray)):
                        content = bytes(value)
                        filename = field_name
                        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                        data.add_field(field_name, content, filename=filename, content_type=content_type)
                        debug_files.append((field_name, filename, content_type, len(content), "bytes"))
                    elif isinstance(value, str) and os.path.isfile(value):
                        filename = os.path.basename(value)
                        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                        # Stream the file object directly instead of
                        # `open(...).read()`-ing it all into memory
                        # first -- matters for large audio/video files.
                        file_object = open(value, "rb")
                        opened_files.append(file_object)
                        data.add_field(field_name, file_object, filename=filename, content_type=content_type)
                        debug_files.append((field_name, filename, content_type, os.path.getsize(value), "file"))
                    else:
                        raise ValueError(f"Invalid file input for {field_name!r}: {value!r}")

                if self._debug:
                    print(
                        f"[BotClient debug] POST {url}\n"
                        f"  Content-Type: multipart/form-data\n"
                        f"  form fields: {form_params}\n"
                        f"  file fields: {debug_files}",
                        file=_sys.stderr,
                    )

                async with session.post(url, data=data, timeout=timeout) as resp:
                    raw_body = await resp.text()
                    if self._debug:
                        print(f"[BotClient debug] HTTP {resp.status} <- {raw_body[:2000]}", file=_sys.stderr)
                    try:
                        payload = _json.loads(raw_body)
                    except _json.JSONDecodeError as e:
                        raise errors.BotAPIError(
                            f"Invalid JSON response from {method}: {raw_body[:500]}", original=e,
                        ) from e
            else:
                if self._debug:
                    print(f"[BotClient debug] POST {url}\n  form fields: {form_params}", file=_sys.stderr)
                async with session.post(url, data=form_params, timeout=timeout) as resp:
                    raw_body = await resp.text()
                    if self._debug:
                        print(f"[BotClient debug] HTTP {resp.status} <- {raw_body[:2000]}", file=_sys.stderr)
                    try:
                        payload = _json.loads(raw_body)
                    except _json.JSONDecodeError as e:
                        raise errors.BotAPIError(
                            f"Invalid JSON response from {method}: {raw_body[:500]}", original=e,
                        ) from e
        except aiohttp.ClientError as e:
            raise errors.BotAPIError(f"Network error calling {method}: {e}", original=e) from e
        except asyncio.TimeoutError as e:
            raise errors.BotAPIError(f"Timed out calling {method}", original=e) from e
        finally:
            for f in opened_files:
                f.close()

        if not payload.get("ok"):
            description = payload.get("description", "Unknown error")
            error_code = payload.get("error_code")
            parameters = payload.get("parameters") or {}
            if error_code == 429 and "retry_after" in parameters:
                raise errors.FloodWaitError(parameters["retry_after"])

            sent_summary = {
                k: (f"<file: {v.value if isinstance(v.value, str) else len(v.value)} bytes>"
                    if isinstance(v, _FileInput) else v)
                for k, v in params.items() if v is not None
            }
            raise errors.BotAPIError(
                f"{description} (method={method!r}, params={sent_summary!r})",
                error_code=error_code, parameters=parameters,
            )

        return payload.get("result")

    def __getattr__(self, name: str):
        # Forward unknown attribute access straight to the Bot API,
        # so `bot.sendDice(...)`, `bot.getMe()`, `bot.answerCallbackQuery(...)`
        # etc all work using the exact official method names, without
        # needing an explicit wrapper for every single one.
        if name.startswith("_"):
            raise AttributeError(name)

        async def _method(**params):
            return await self.call(name, **params)

        return _method

    def _file_param(self, value: Optional[Union[str, bytes]], field_name: str) -> Optional[_FileInput]:
        if value is None:
            return None
        return _FileInput(value, field_name)

    # ------------------------------------------------------------------ #
    # Keyboard-building helpers, also reachable as bot.inline_keyboard(...)
    # ------------------------------------------------------------------ #
    #
    # IMPORTANT: these are real methods (not inherited via __getattr__),
    # specifically so that bot.inline_keyboard(...)/bot.reply_keyboard(...)
    # etc actually build a keyboard dict locally. Without this, calling
    # them as bot.inline_keyboard(...) would silently fall through
    # BotClient.__getattr__ and try to POST a nonexistent "inline_keyboard"
    # method to the live HTTP API instead of raising a clear error -- the
    # module-level functions (spluslib.bot_client.inline_keyboard, or
    # `from spluslib import inline_keyboard`) do the exact same thing and
    # remain the other supported way to call these.

    @staticmethod
    def inline_keyboard(buttons: List[List[Dict[str, str]]]) -> Dict[str, Any]:
        """See the module-level inline_keyboard() for full docs."""
        return inline_keyboard(buttons)

    @staticmethod
    def reply_keyboard(
        buttons: List[List[Union[str, Dict[str, Any]]]],
        *, resize_keyboard: bool = True, one_time_keyboard: bool = False, selective: bool = False,
    ) -> Dict[str, Any]:
        """See the module-level reply_keyboard() for full docs."""
        return reply_keyboard(
            buttons, resize_keyboard=resize_keyboard,
            one_time_keyboard=one_time_keyboard, selective=selective,
        )

    @staticmethod
    def remove_keyboard(*, selective: bool = False) -> Dict[str, Any]:
        """See the module-level remove_keyboard() for full docs."""
        return remove_keyboard(selective=selective)

    @staticmethod
    def force_reply(*, selective: bool = False, input_field_placeholder: str = None) -> Dict[str, Any]:
        """See the module-level force_reply() for full docs."""
        return force_reply(selective=selective, input_field_placeholder=input_field_placeholder)

    # ------------------------------------------------------------------ #
    # Events: decorators + polling loop
    # ------------------------------------------------------------------ #

    def on_message(self, func: Optional[Callable] = None):
        """
        Register a handler for new incoming messages (the `message`
        field of an Update). The handler receives the raw message
        dict, exactly as documented for the `Message` object.

            @bot.on_message()
            async def handler(message):
                await bot.send_message(message["chat"]["id"], "got it")

        Optionally filter with a predicate:

            @bot.on_message(lambda m: "text" in m)
            async def text_only(message):
                ...
        """
        def decorator(handler):
            self._message_handlers.append((func, handler))
            return handler
        return decorator

    def on_edited_message(self, func: Optional[Callable] = None):
        """Register a handler for edited messages (the `edited_message`
        field of an Update). Same shape/filtering as on_message()."""
        def decorator(handler):
            self._edited_message_handlers.append((func, handler))
            return handler
        return decorator

    def on_callback_query(self, func: Optional[Callable] = None):
        """
        Register a handler for inline button presses (the
        `callback_query` field of an Update).

            @bot.on_callback_query()
            async def handler(query):
                await bot.answer_callback_query(query["id"], text="Got it!")
        """
        def decorator(handler):
            self._callback_query_handlers.append((func, handler))
            return handler
        return decorator

    def on_inline_query(self, func: Optional[Callable] = None):
        """Register a handler for inline queries (the `inline_query`
        field of an Update, i.e. `@bot query` typed elsewhere)."""
        def decorator(handler):
            self._inline_query_handlers.append((func, handler))
            return handler
        return decorator

    def on_update(self, handler: Callable):
        """
        Register a handler that fires for every single update
        regardless of type, receiving the raw Update dict. Useful for
        logging or handling update types with no dedicated decorator
        above. Not a decorator factory -- use it directly:

            bot.on_update(my_handler)
        """
        self._update_handlers.append(handler)
        return handler

    async def _dispatch(self, update: Dict[str, Any]):
        for handler in self._update_handlers:
            await _maybe_await(handler(update))

        if "message" in update:
            await self._run_handlers(self._message_handlers, BotMessage(update["message"], self))
        if "edited_message" in update:
            await self._run_handlers(self._edited_message_handlers, BotMessage(update["edited_message"], self))
        if "callback_query" in update:
            await self._run_handlers(self._callback_query_handlers, BotCallbackQuery(update["callback_query"], self))
        if "inline_query" in update:
            await self._run_handlers(self._inline_query_handlers, update["inline_query"])

    async def _run_handlers(self, handlers, payload):
        for func, handler in handlers:
            if func is not None:
                try:
                    keep = func(payload)
                except Exception:
                    continue
                if not keep:
                    continue
            await _maybe_await(handler(payload))

    async def run_polling(
        self,
        *,
        poll_timeout: int = 30,
        limit: int = 100,
        allowed_updates: Optional[List[str]] = None,
        drop_pending_updates: bool = False,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ):
        """
        Start long-polling for updates and dispatch them to your
        registered handlers forever (until stop_polling() is called or
        the task is cancelled). This calls getUpdates() in a loop --
        don't also set a webhook at the same time (the API won't
        deliver updates via getUpdates while a webhook is active; call
        delete_webhook() first if you'd previously set one).

            bot = BotClient(token)

            @bot.on_message()
            async def echo(message):
                if "text" in message:
                    await bot.send_message(message["chat"]["id"], message["text"])

            await bot.run_polling()
        """
        self._polling = True
        offset = None

        if drop_pending_updates:
            # Fetch and immediately discard whatever's pending, by
            # requesting with a huge offset next call.
            pending = await self.get_updates(limit=100, timeout=0)
            if pending:
                offset = pending[-1]["update_id"] + 1

        while self._polling:
            try:
                updates = await self.get_updates(
                    offset=offset, limit=limit, timeout=poll_timeout,
                    allowed_updates=allowed_updates,
                )
            except Exception as e:
                if on_error is not None:
                    await _maybe_await(on_error(e))
                else:
                    # IMPORTANT: never swallow this silently. Without an
                    # on_error handler, print it so a broken poll loop
                    # (bad token, network issue, etc) is visible instead
                    # of looking like the bot just isn't doing anything.
                    import traceback
                    print(f"[BotClient] get_updates() failed: {e!r}", file=_sys.stderr)
                    traceback.print_exc()
                    await asyncio.sleep(1)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                try:
                    await self._dispatch(update)
                except Exception as e:
                    if on_error is not None:
                        await _maybe_await(on_error(e))
                    else:
                        # Same reasoning as above -- a handler raising
                        # (e.g. calling a method that doesn't exist on
                        # the plain dict passed to it) must not vanish
                        # without a trace.
                        import traceback
                        print(f"[BotClient] handler for update {update.get('update_id')} "
                              f"raised: {e!r}", file=_sys.stderr)
                        traceback.print_exc()

    def stop_polling(self):
        """Stop a running run_polling() loop after its current
        getUpdates() call returns."""
        self._polling = False

    async def run_webhook(
        self,
        url: str,
        *,
        host: str = "0.0.0.0",
        port: int = 8443,
        path: Optional[str] = None,
        certificate: Union[str, bytes] = None,
        ip_address: str = None,
        max_connections: int = 40,
        allowed_updates: Optional[List[str]] = None,
        drop_pending_updates: bool = False,
        secret_token: str = None,
    ):
        """
        Run an HTTP server that listens for updates pushed by Soroush
        Plus, instead of long-polling for them -- the opposite
        transport direction from run_polling(). This calls
        setWebhook() for you (printing the confirmation and the API's
        response, see below) and then serves forever until cancelled
        or stop_webhook() is called; don't also run_polling() at the
        same time as a webhook is set, they're mutually exclusive on
        Soroush's side.

        Args:
            url: Your public HTTPS URL, e.g. "https://test.ir/bot" --
                this is the full address Soroush Plus will POST
                updates to. Must be reachable from the internet (not
                localhost/a private IP) and use one of the supported
                webhook ports: 443, 80, 88, or 8443.
            host: Local address to bind the server to. "0.0.0.0"
                (default) listens on all interfaces -- correct for
                most setups (a reverse proxy or direct public
                exposure). Use "127.0.0.1" only if something else
                (nginx, etc) is proxying to this port for you.
            port: Local port to bind to. This is the port your process
                actually listens on -- it does not have to match the
                port implied by `url` if you're behind a reverse proxy
                that forwards to it (e.g. nginx on :443 forwarding to
                this process on :8443).
            path: URL path to accept updates on. Defaults to whatever
                path is present in `url` (e.g. "/bot" for
                "https://test.ir/bot"), or "/" if `url` has no path.
            certificate, ip_address, max_connections, allowed_updates,
            drop_pending_updates: passed straight through to
                set_webhook() -- see its docstring.
            secret_token: If given, Soroush Plus will include it in an
                `X-Splus-Bot-Api-Secret-Token` header on every request,
                and this server will reject any request that doesn't
                have that exact header, so random requests to your
                endpoint can't spoof updates. Recommended for anything
                public-facing.

        Example:
            await bot.run_webhook("https://test.ir/bot", port=8443)
            # prints:
            #   [BotClient] Webhook server listening on 0.0.0.0:8443/bot
            #   [BotClient] setWebhook -> {'url': 'https://test.ir/bot', ...}
            #   [BotClient] Webhook set successfully.
        """
        _require_aiohttp()

        from urllib.parse import urlparse
        parsed = urlparse(url)
        webhook_path = path if path is not None else (parsed.path or "/")

        app = aiohttp_web.Application()

        async def _handle_update(request: "aiohttp_web.Request"):
            if secret_token is not None:
                header = request.headers.get("X-Splus-Bot-Api-Secret-Token")
                if header != secret_token:
                    return aiohttp_web.Response(status=401, text="Invalid secret token")
            try:
                update = await request.json()
            except Exception:
                return aiohttp_web.Response(status=400, text="Invalid JSON")

            try:
                await self._dispatch(update)
            except Exception as e:
                import traceback
                print(f"[BotClient] handler for update {update.get('update_id')} "
                      f"raised: {e!r}", file=_sys.stderr)
                traceback.print_exc()

            return aiohttp_web.Response(status=200)

        app.router.add_post(webhook_path, _handle_update)

        runner = aiohttp_web.AppRunner(app)
        await runner.setup()
        site = aiohttp_web.TCPSite(runner, host, port)
        await site.start()
        self._webhook_runner = runner

        print(f"[BotClient] Webhook server listening on {host}:{port}{webhook_path}", file=_sys.stderr)

        result = await self.set_webhook(
            url,
            certificate=certificate,
            ip_address=ip_address,
            max_connections=max_connections,
            allowed_updates=allowed_updates,
            drop_pending_updates=drop_pending_updates,
        )
        info = await self.get_webhook_info()
        if result:
            print(f"[BotClient] Webhook set successfully -> {info}", file=_sys.stderr)
        else:
            print(f"[BotClient] setWebhook returned falsy -- check the URL/port "
                  f"and try again. Current webhook info: {info}", file=_sys.stderr)

        self._webhook_running = True
        try:
            while self._webhook_running:
                await asyncio.sleep(1)
        finally:
            await runner.cleanup()

    async def stop_webhook(self, *, delete: bool = True):
        """
        Stop a running run_webhook() server. By default also calls
        delete_webhook() so Soroush Plus stops trying to push updates
        to a server that's no longer listening -- pass delete=False to
        leave the webhook registration in place (e.g. if you're about
        to restart the server on the same URL momentarily).
        """
        self._webhook_running = False
        if delete:
            await self.delete_webhook()

    # ------------------------------------------------------------------ #
    # Lifecycle / meta
    # ------------------------------------------------------------------ #

    async def get_me(self) -> Dict[str, Any]:
        """Test the token and get basic info about the bot (a `User`
        dict). Also cached on `.me` after the first successful call."""
        self._me = await self.call("getMe")
        return self._me

    @property
    def me(self) -> Optional[Dict[str, Any]]:
        """The bot's own User dict, if get_me() has been called at
        least once (None before that)."""
        return self._me

    async def log_out(self) -> bool:
        """Log out from the cloud API server, e.g. before switching to
        a local Bot API server. You won't be able to log back in for
        10 minutes."""
        return bool(await self.call("logOut"))

    async def close_bot(self) -> bool:
        """Close the bot instance before moving it from one local
        server to another. Named close_bot (not close) so it doesn't
        collide with close(), which releases the HTTP session."""
        return bool(await self.call("close"))

    # ------------------------------------------------------------------ #
    # Updates & webhook
    # ------------------------------------------------------------------ #

    async def get_updates(
        self,
        *,
        offset: int = None,
        limit: int = 100,
        timeout: int = 0,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Long-poll for new updates directly (you generally want
        run_polling() instead, which wraps this in a loop and
        dispatches to your @bot.on_message()/etc handlers -- call this
        directly only if you want to manage the loop/offset yourself).

        Does not work while a webhook is set -- call delete_webhook()
        first if you'd previously set one.
        """
        result = await self.call(
            "getUpdates", offset=offset, limit=limit, timeout=timeout,
            allowed_updates=allowed_updates,
        )
        return result or []

    async def set_webhook(
        self,
        url: str,
        *,
        certificate: Union[str, bytes] = None,
        ip_address: str = None,
        max_connections: int = 40,
        allowed_updates: Optional[List[str]] = None,
        drop_pending_updates: bool = False,
    ) -> bool:
        """
        Set a webhook URL to receive updates via an outgoing HTTPS
        POST instead of polling. Supported ports: 443, 80, 88, 8443.
        Use an unguessable path (e.g. incorporating your bot token) so
        random requests can't spoof updates.
        """
        return bool(await self.call(
            "setWebhook",
            url=url,
            certificate=self._file_param(certificate, "certificate"),
            ip_address=ip_address,
            max_connections=max_connections,
            allowed_updates=allowed_updates,
            drop_pending_updates=drop_pending_updates or None,
        ))

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool:
        """Remove the webhook and go back to using get_updates()/run_polling()."""
        return bool(await self.call("deleteWebhook", drop_pending_updates=drop_pending_updates or None))

    async def get_webhook_info(self) -> Dict[str, Any]:
        """Get the current webhook status (a `WebhookInfo` dict)."""
        return await self.call("getWebhookInfo")

    # ------------------------------------------------------------------ #
    # Messaging
    # ------------------------------------------------------------------ #

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        *,
        parse_mode: Optional[str] = None,
        entities: Optional[List[dict]] = None,
        disable_web_page_preview: bool = None,
        reply_to_message_id: int = None,
        allow_sending_without_reply: bool = None,
        reply_markup: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message. Returns the sent `Message` dict.

        `parse_mode`: "MarkdownV2", "HTML", or "Markdown" (legacy) --
        omit to send plain text with no formatting parsing at all.
        `reply_markup`: a dict shaped like an `InlineKeyboardMarkup`,
        `ReplyKeyboardMarkup`, `ReplyKeyboardRemove`, or `ForceReply` --
        see the keyboard helper functions in this module
        (inline_keyboard(), reply_keyboard()) for an easier way to
        build these than writing the dict by hand.
        """
        return await self.call(
            "sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode,
            entities=entities, disable_web_page_preview=disable_web_page_preview,
            reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=allow_sending_without_reply,
            reply_markup=reply_markup,
        )

    async def forward_message(
        self,
        chat_id: Union[int, str],
        from_chat_id: Union[int, str],
        message_id: int,
        *,
        disable_notification: bool = None,
    ) -> Dict[str, Any]:
        """Forward a message as-is (keeps the "Forwarded from" header)."""
        return await self.call(
            "forwardMessage", chat_id=chat_id, from_chat_id=from_chat_id,
            message_id=message_id, disable_notification=disable_notification,
        )

    async def copy_message(
        self,
        chat_id: Union[int, str],
        from_chat_id: Union[int, str],
        message_id: int,
        *,
        caption: str = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Copy a message's content without the "Forwarded from" link
        back to the original. Returns a `MessageId` dict (`{"message_id": ...}`)."""
        return await self.call(
            "copyMessage", chat_id=chat_id, from_chat_id=from_chat_id,
            message_id=message_id, caption=caption, parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    async def edit_message_text(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        *,
        parse_mode: Optional[str] = None,
        entities: Optional[List[dict]] = None,
        disable_web_page_preview: bool = None,
        reply_markup: Optional[dict] = None,
    ) -> Union[Dict[str, Any], bool]:
        """Edit the text of a message you sent. Returns the edited
        `Message`, or `True` if it was an inline message."""
        return await self.call(
            "editMessageText", chat_id=chat_id, message_id=message_id, text=text,
            parse_mode=parse_mode, entities=entities,
            disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup,
        )

    async def edit_message_caption(
        self,
        chat_id: Union[int, str],
        message_id: int,
        caption: str,
        *,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None,
    ) -> Union[Dict[str, Any], bool]:
        """Edit the caption of a media message."""
        return await self.call(
            "editMessageCaption", chat_id=chat_id, message_id=message_id,
            caption=caption, parse_mode=parse_mode, reply_markup=reply_markup,
        )

    async def edit_message_reply_markup(
        self,
        chat_id: Union[int, str],
        message_id: int,
        *,
        reply_markup: Optional[dict] = None,
    ) -> Union[Dict[str, Any], bool]:
        """Edit (or remove, with reply_markup=None) just the inline
        keyboard of a message."""
        return await self.call(
            "editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
            reply_markup=reply_markup,
        )

    async def delete_message(self, chat_id: Union[int, str], message_id: int) -> bool:
        """Delete a message (only works within the API's allowed
        deletion window/scope)."""
        return bool(await self.call("deleteMessage", chat_id=chat_id, message_id=message_id))

    async def pin_chat_message(
        self, chat_id: Union[int, str], message_id: int, *, disable_notification: bool = None,
    ) -> bool:
        return bool(await self.call(
            "pinChatMessage", chat_id=chat_id, message_id=message_id,
            disable_notification=disable_notification,
        ))

    async def unpin_chat_message(self, chat_id: Union[int, str], message_id: int = None) -> bool:
        return bool(await self.call("unpinChatMessage", chat_id=chat_id, message_id=message_id))

    async def send_chat_action(self, chat_id: Union[int, str], action: str) -> bool:
        """
        Show a status like "typing..." or "uploading photo...". Valid
        `action` values: "typing", "upload_photo", "record_video",
        "upload_video", "record_voice", "upload_voice",
        "upload_document", "choose_sticker", "find_location",
        "record_video_note", "upload_video_note". Lasts up to 5
        seconds, or until you send the actual message.
        """
        return bool(await self.call("sendChatAction", chat_id=chat_id, action=action))

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str = None,
        show_alert: bool = None,
        url: str = None,
        cache_time: int = None,
    ) -> bool:
        """
        Answer an inline button press. Call this for every
        callback_query you handle, even with no `text` -- otherwise
        the user's client shows a loading spinner on the button until
        it times out.
        """
        return bool(await self.call(
            "answerCallbackQuery", callback_query_id=callback_query_id,
            text=text, show_alert=show_alert, url=url, cache_time=cache_time,
        ))

    async def get_chat(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Get up-to-date info about a chat (a `Chat` dict)."""
        return await self.call("getChat", chat_id=chat_id)

    # ------------------------------------------------------------------ #
    # Files, photos, video, voice, audio, stickers
    # ------------------------------------------------------------------ #
    #
    # Every one of these accepts `photo=`/`document=`/etc as: a local
    # file path (str), a URL (str), or raw bytes -- no manual byte
    # reading needed, matching SplusClient's send_file/send_photo/etc.
    # `progress=True` (the default) shows a console progress bar for
    # actual uploads (local path/bytes); it's a no-op when you pass a
    # URL or an existing file_id, since there's nothing to upload.

    async def _send_media(
        self, method: str, chat_id, field_name: str, file: Union[str, bytes],
        *, progress: Union[bool, Callable, None] = True, **extra,
    ) -> Dict[str, Any]:
        file_input = self._file_param(file, field_name)
        progress_cb = None
        if file_input is not None and file_input.is_upload:
            progress_cb = _resolve_progress_callback(file, progress)
        # NOTE: the Bot API has no native upload-progress reporting
        # (it's a single multipart POST, not chunked like the MTProto
        # upload path) -- so unlike SplusClient's progress=, this can
        # only report 0% then 100%, not real incremental progress.
        # Still shown by default for consistency/visual feedback.
        if progress_cb:
            total = len(file) if isinstance(file, (bytes, bytearray)) else (
                os.path.getsize(file) if isinstance(file, str) and os.path.isfile(file) else 0
            )
            progress_cb(0, total)
        result = await self.call(method, chat_id=chat_id, **{field_name: file_input}, **extra)
        if progress_cb:
            total = len(file) if isinstance(file, (bytes, bytearray)) else (
                os.path.getsize(file) if isinstance(file, str) and os.path.isfile(file) else 0
            )
            progress_cb(total, total)
        return result

    async def send_photo(
        self, chat_id: Union[int, str], photo: Union[str, bytes], *,
        caption: str = None, parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a photo (up to 10MB). `photo` can be a local path, URL, or raw bytes."""
        return await self._send_media(
            "sendPhoto", chat_id, "photo", photo, caption=caption,
            parse_mode=parse_mode, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id, progress=progress,
        )

    async def send_audio(
        self, chat_id: Union[int, str], audio: Union[str, bytes], *,
        caption: str = None, parse_mode: Optional[str] = None,
        duration: int = None, performer: str = None, title: str = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a music-player-style audio file (MP3, M4A)."""
        return await self._send_media(
            "sendAudio", chat_id, "audio", audio, caption=caption,
            parse_mode=parse_mode, duration=duration, performer=performer,
            title=title, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id, progress=progress,
        )

    async def send_document(
        self, chat_id: Union[int, str], document: Union[str, bytes], *,
        caption: str = None, parse_mode: Optional[str] = None,
        disable_content_type_detection: bool = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a general file (up to 50MB)."""
        return await self._send_media(
            "sendDocument", chat_id, "document", document, caption=caption,
            parse_mode=parse_mode,
            disable_content_type_detection=disable_content_type_detection,
            reply_markup=reply_markup, reply_to_message_id=reply_to_message_id,
            progress=progress,
        )

    async def send_video(
        self, chat_id: Union[int, str], video: Union[str, bytes], *,
        caption: str = None, parse_mode: Optional[str] = None,
        duration: int = None, width: int = None, height: int = None,
        supports_streaming: bool = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a video (up to 50MB)."""
        return await self._send_media(
            "sendVideo", chat_id, "video", video, caption=caption,
            parse_mode=parse_mode, duration=duration, width=width, height=height,
            supports_streaming=supports_streaming, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id, progress=progress,
        )

    async def send_animation(
        self, chat_id: Union[int, str], animation: Union[str, bytes], *,
        caption: str = None, parse_mode: Optional[str] = None,
        duration: int = None, width: int = None, height: int = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a GIF or soundless MP4/H.264 animation."""
        return await self._send_media(
            "sendAnimation", chat_id, "animation", animation, caption=caption,
            parse_mode=parse_mode, duration=duration, width=width, height=height,
            reply_markup=reply_markup, reply_to_message_id=reply_to_message_id,
            progress=progress,
        )

    async def send_voice(
        self, chat_id: Union[int, str], voice: Union[str, bytes], *,
        caption: str = None, parse_mode: Optional[str] = None,
        duration: int = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a playable voice message (OGG/OPUS, MP3, or M4A)."""
        return await self._send_media(
            "sendVoice", chat_id, "voice", voice, caption=caption,
            parse_mode=parse_mode, duration=duration, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id, progress=progress,
        )

    async def send_video_note(
        self, chat_id: Union[int, str], video_note: Union[str, bytes], *,
        duration: int = None, length: int = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a round "video message" (up to 1 minute)."""
        return await self._send_media(
            "sendVideoNote", chat_id, "video_note", video_note, duration=duration,
            length=length, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id, progress=progress,
        )

    async def send_sticker(
        self, chat_id: Union[int, str], sticker: Union[str, bytes], *,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
        progress: Union[bool, Callable, None] = True,
    ) -> Dict[str, Any]:
        """Send a sticker (WEBP, TGS, or WEBM)."""
        return await self._send_media(
            "sendSticker", chat_id, "sticker", sticker, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id, progress=progress,
        )

    async def send_media_group(
        self, chat_id: Union[int, str], media: List[dict],
    ) -> List[Dict[str, Any]]:
        """
        Send an album of 2-10 photos/videos/documents/audio as a
        group. `media` is a list of `InputMedia*`-shaped dicts, e.g.:

            await bot.send_media_group(chat_id, [
                {"type": "photo", "media": "https://example.com/1.jpg", "caption": "first"},
                {"type": "photo", "media": "https://example.com/2.jpg"},
            ])

        To attach local files instead of URLs, reference an
        `attach://<name>` in `media` and pass matching keyword
        arguments named `<name>` -- this is Telegram's exact
        convention. For simple all-URL albums, dicts alone are enough.
        """
        return await self.call("sendMediaGroup", chat_id=chat_id, media=media)

    # ------------------------------------------------------------------ #
    # Location, contact, dice
    # ------------------------------------------------------------------ #

    async def send_location(
        self, chat_id: Union[int, str], latitude: float, longitude: float, *,
        horizontal_accuracy: float = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
    ) -> Dict[str, Any]:
        return await self.call(
            "sendLocation", chat_id=chat_id, latitude=latitude, longitude=longitude,
            horizontal_accuracy=horizontal_accuracy, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_contact(
        self, chat_id: Union[int, str], phone_number: str, first_name: str, *,
        last_name: str = None, vcard: str = None,
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
    ) -> Dict[str, Any]:
        return await self.call(
            "sendContact", chat_id=chat_id, phone_number=phone_number,
            first_name=first_name, last_name=last_name, vcard=vcard,
            reply_markup=reply_markup, reply_to_message_id=reply_to_message_id,
        )

    async def send_dice(
        self, chat_id: Union[int, str], *, emoji: str = "🎲",
        reply_markup: Optional[dict] = None, reply_to_message_id: int = None,
    ) -> Dict[str, Any]:
        """Send an animated random dice/emoji. `emoji` can be one of
        the special animated ones Telegram-family clients support
        (🎲, 🎯, 🏀, ⚽, 🎳, 🎰) -- the resulting `dice.value` is the
        random outcome."""
        return await self.call(
            "sendDice", chat_id=chat_id, emoji=emoji, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_poll(
        self,
        chat_id: Union[int, str],
        question: str,
        options: List[str],
        *,
        is_anonymous: bool = None,
        type: str = None,
        allows_multiple_answers: bool = None,
        correct_option_id: int = None,
        explanation: str = None,
        explanation_parse_mode: Optional[str] = None,
        open_period: int = None,
        close_date: int = None,
        is_closed: bool = None,
        reply_markup: Optional[dict] = None,
        reply_to_message_id: int = None,
    ) -> Dict[str, Any]:
        """
        Send a poll (or quiz -- pass type="quiz" and correct_option_id).

            await bot.send_poll(chat_id, "Best pizza topping?",
                                 ["Pepperoni", "Mushroom", "Pineapple"])

            await bot.send_poll(chat_id, "2 + 2 = ?", ["3", "4", "5"],
                                 type="quiz", correct_option_id=1,
                                 explanation="Basic arithmetic!")

        NOTE: unlike SplusClient.send_poll() (the MTProto userbot
        client, a different part of this library), this method talks
        to the official Bot API, so its parameters are the official
        camelCase-derived ones (open_period/close_date instead of
        close_period, correct_option_id instead of correct_option,
        etc) -- matches the Bot API docs exactly, not SplusClient's
        naming.
        """
        return await self.call(
            "sendPoll", chat_id=chat_id, question=question, options=options,
            is_anonymous=is_anonymous, type=type,
            allows_multiple_answers=allows_multiple_answers,
            correct_option_id=correct_option_id, explanation=explanation,
            explanation_parse_mode=explanation_parse_mode, open_period=open_period,
            close_date=close_date, is_closed=is_closed, reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )

    async def stop_poll(
        self, chat_id: Union[int, str], message_id: int, *, reply_markup: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Stop (close) a poll you sent. Returns the final `Poll` dict
        with final vote counts."""
        return await self.call("stopPoll", chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)

    # ------------------------------------------------------------------ #
    # Chat / member management
    # ------------------------------------------------------------------ #

    async def ban_chat_member(
        self, chat_id: Union[int, str], user_id: int, *,
        until_date: int = None, revoke_messages: bool = None,
    ) -> bool:
        """Ban a user from a group/channel (they can't rejoin until
        unbanned, or until until_date if given)."""
        return bool(await self.call(
            "banChatMember", chat_id=chat_id, user_id=user_id,
            until_date=until_date, revoke_messages=revoke_messages,
        ))

    async def unban_chat_member(
        self, chat_id: Union[int, str], user_id: int, *, only_if_banned: bool = None,
    ) -> bool:
        """Unban a previously-banned user. They won't auto-rejoin --
        they'll need a fresh invite link."""
        return bool(await self.call(
            "unbanChatMember", chat_id=chat_id, user_id=user_id, only_if_banned=only_if_banned,
        ))

    async def restrict_chat_member(
        self, chat_id: Union[int, str], user_id: int, permissions: dict, *,
        until_date: int = None, use_independent_chat_permissions: bool = None,
    ) -> bool:
        """
        Restrict what a user can do in a group (mute, block media,
        etc) without banning them. `permissions` is a `ChatPermissions`
        dict, e.g. `{"can_send_messages": False}` to fully mute.
        """
        return bool(await self.call(
            "restrictChatMember", chat_id=chat_id, user_id=user_id,
            permissions=permissions, until_date=until_date,
            use_independent_chat_permissions=use_independent_chat_permissions,
        ))

    async def promote_chat_member(
        self, chat_id: Union[int, str], user_id: int, **admin_rights,
    ) -> bool:
        """
        Grant/revoke admin rights for a user. Pass any of the official
        boolean fields as kwargs, e.g.:

            await bot.promote_chat_member(chat_id, user_id,
                                           can_delete_messages=True,
                                           can_invite_users=True)
        """
        return bool(await self.call("promoteChatMember", chat_id=chat_id, user_id=user_id, **admin_rights))

    async def set_chat_administrator_custom_title(
        self, chat_id: Union[int, str], user_id: int, custom_title: str,
    ) -> bool:
        """Set a custom admin title (shown instead of "Admin") for an
        admin you promoted."""
        return bool(await self.call(
            "setChatAdministratorCustomTitle", chat_id=chat_id, user_id=user_id, custom_title=custom_title,
        ))

    async def set_chat_permissions(self, chat_id: Union[int, str], permissions: dict) -> bool:
        """Set the default permissions for all non-admin members of a group."""
        return bool(await self.call("setChatPermissions", chat_id=chat_id, permissions=permissions))

    async def set_chat_title(self, chat_id: Union[int, str], title: str) -> bool:
        return bool(await self.call("setChatTitle", chat_id=chat_id, title=title))

    async def set_chat_description(self, chat_id: Union[int, str], description: str = None) -> bool:
        return bool(await self.call("setChatDescription", chat_id=chat_id, description=description))

    async def set_chat_photo(self, chat_id: Union[int, str], photo: Union[str, bytes]) -> bool:
        """Set a group/channel's photo. `photo` must be an upload (a
        local path or raw bytes) -- URLs/file_ids aren't accepted for
        this one, per the Bot API."""
        return bool(await self.call("setChatPhoto", chat_id=chat_id, photo=self._file_param(photo, "photo")))

    async def delete_chat_photo(self, chat_id: Union[int, str]) -> bool:
        return bool(await self.call("deleteChatPhoto", chat_id=chat_id))

    async def leave_chat(self, chat_id: Union[int, str]) -> bool:
        """Make the bot leave a group/channel."""
        return bool(await self.call("leaveChat", chat_id=chat_id))

    async def get_chat_administrators(self, chat_id: Union[int, str]) -> List[Dict[str, Any]]:
        """Get the list of admins in a group/channel (a list of
        `ChatMember` dicts)."""
        result = await self.call("getChatAdministrators", chat_id=chat_id)
        return result or []

    async def get_chat_member_count(self, chat_id: Union[int, str]) -> int:
        return await self.call("getChatMemberCount", chat_id=chat_id)

    async def get_chat_member(self, chat_id: Union[int, str], user_id: int) -> Dict[str, Any]:
        """Get info about a specific chat member (a `ChatMember` dict,
        including their status: creator/administrator/member/restricted/left/kicked)."""
        return await self.call("getChatMember", chat_id=chat_id, user_id=user_id)

    # ------------------------------------------------------------------ #
    # Invite links & join requests
    # ------------------------------------------------------------------ #

    async def create_chat_invite_link(
        self, chat_id: Union[int, str], *, name: str = None,
        expire_date: int = None, member_limit: int = None, creates_join_request: bool = None,
    ) -> Dict[str, Any]:
        """Create an additional invite link for a chat (a `ChatInviteLink` dict)."""
        return await self.call(
            "createChatInviteLink", chat_id=chat_id, name=name, expire_date=expire_date,
            member_limit=member_limit, creates_join_request=creates_join_request,
        )

    async def edit_chat_invite_link(
        self, chat_id: Union[int, str], invite_link: str, *, name: str = None,
        expire_date: int = None, member_limit: int = None, creates_join_request: bool = None,
    ) -> Dict[str, Any]:
        return await self.call(
            "editChatInviteLink", chat_id=chat_id, invite_link=invite_link, name=name,
            expire_date=expire_date, member_limit=member_limit,
            creates_join_request=creates_join_request,
        )

    async def revoke_chat_invite_link(self, chat_id: Union[int, str], invite_link: str) -> Dict[str, Any]:
        return await self.call("revokeChatInviteLink", chat_id=chat_id, invite_link=invite_link)

    async def approve_chat_join_request(self, chat_id: Union[int, str], user_id: int) -> bool:
        return bool(await self.call("approveChatJoinRequest", chat_id=chat_id, user_id=user_id))

    async def decline_chat_join_request(self, chat_id: Union[int, str], user_id: int) -> bool:
        return bool(await self.call("declineChatJoinRequest", chat_id=chat_id, user_id=user_id))

    # ------------------------------------------------------------------ #
    # File download
    # ------------------------------------------------------------------ #

    async def get_file(self, file_id: str) -> Dict[str, Any]:
        """Get info about a file (a `File` dict with `file_path`),
        needed to build a download URL or call download_file(). The
        resulting link is valid for at least 1 hour."""
        return await self.call("getFile", file_id=file_id)

    def get_file_url(self, file_path: str) -> str:
        """Build the direct download URL for a file_path returned by get_file()."""
        return f"{self._file_base_url}/bot{self.token}/{file_path}"

    async def download_file(
        self, file_id: str, destination: Optional[str] = None,
    ) -> Union[str, bytes]:
        """
        Download a file by its file_id. If `destination` is given,
        saves it there and returns the path; otherwise returns the
        raw bytes.

            info = await bot.send_photo(chat_id, "photo.jpg")
            file_id = info["photo"][-1]["file_id"]
            data = await bot.download_file(file_id)
            # or:
            path = await bot.download_file(file_id, "saved.jpg")
        """
        file_info = await self.get_file(file_id)
        url = self.get_file_url(file_info["file_path"])
        session = await self._get_session()
        async with session.get(url) as resp:
            if resp.status != 200:
                raise errors.BotAPIError(
                    f"Failed to download file (HTTP {resp.status})", error_code=resp.status,
                )
            data = await resp.read()

        if destination is None:
            return data
        with open(destination, "wb") as f:
            f.write(data)
        return destination

    async def get_user_profile_photos(
        self, user_id: int, *, offset: int = None, limit: int = None,
    ) -> Dict[str, Any]:
        """Get a user's profile photos (a `UserProfilePhotos` dict)."""
        return await self.call("getUserProfilePhotos", user_id=user_id, offset=offset, limit=limit)

    # ------------------------------------------------------------------ #
    # Bot commands
    # ------------------------------------------------------------------ #

    async def set_my_commands(
        self, commands: List[Dict[str, str]], *,
        scope: Optional[dict] = None, language_code: str = None,
    ) -> bool:
        """
        Set the bot's command list (shown in the chat's "/" menu).
        `commands` is a list of `{"command": "...", "description": "..."}`
        dicts. Optionally scope to a specific chat type/chat with
        `scope` (a `BotCommandScope*`-shaped dict, e.g.
        `{"type": "default"}`, `{"type": "all_private_chats"}`, or
        `{"type": "chat", "chat_id": ...}`).
        """
        return bool(await self.call(
            "setMyCommands", commands=commands, scope=scope, language_code=language_code,
        ))

    async def delete_my_commands(
        self, *, scope: Optional[dict] = None, language_code: str = None,
    ) -> bool:
        return bool(await self.call("deleteMyCommands", scope=scope, language_code=language_code))

    async def get_my_commands(
        self, *, scope: Optional[dict] = None, language_code: str = None,
    ) -> List[Dict[str, str]]:
        result = await self.call("getMyCommands", scope=scope, language_code=language_code)
        return result or []

    # inline_keyboard/reply_keyboard/remove_keyboard/force_reply are
    # also available as bot.inline_keyboard(...) etc, not just as
    # top-level spluslib.bot_client functions -- see the bottom of this
    # file, right after they're defined, for where they get attached
    # to this class as staticmethods. (They can't be defined inline
    # here since BotClient.__getattr__ forwards ANY undefined
    # attribute straight to the live HTTP API by design -- attaching
    # real staticmethods after the class is the fix, not a workaround:
    # __getattr__ is only ever consulted for names Python's normal
    # attribute lookup doesn't find, so a real class attribute always
    # wins and __getattr__ is never reached for these names.)


# ---------------------------------------------------------------------- #
# Keyboard-building helpers
# ---------------------------------------------------------------------- #
#
# These just build the plain dicts the Bot API expects for
# reply_markup=; using them is entirely optional -- you can always pass
# a hand-built dict in the exact same shape instead. They exist so you
# don't have to remember the exact nested key names.

def inline_keyboard(buttons: List[List[Dict[str, str]]]) -> Dict[str, Any]:
    """
    Build an `InlineKeyboardMarkup` dict from rows of button dicts.
    Each button dict needs "text" plus exactly one of "callback_data"
    or "url" (or any other official InlineKeyboardButton field).

        markup = inline_keyboard([
            [{"text": "Yes", "callback_data": "yes"}, {"text": "No", "callback_data": "no"}],
            [{"text": "Visit site", "url": "https://example.com"}],
        ])
        await bot.send_message(chat_id, "Pick one:", reply_markup=markup)
    """
    return {"inline_keyboard": buttons}


def reply_keyboard(
    buttons: List[List[Union[str, Dict[str, Any]]]],
    *,
    resize_keyboard: bool = True,
    one_time_keyboard: bool = False,
    selective: bool = False,
) -> Dict[str, Any]:
    """
    Build a `ReplyKeyboardMarkup` dict (the custom keyboard that
    replaces the user's regular keyboard, as opposed to inline
    buttons attached to one message). Each item in a row can be a
    plain string (becomes `{"text": ...}`) or a dict for special
    buttons (`{"text": ..., "request_contact": True}`, etc).

        markup = reply_keyboard([["Option A", "Option B"], ["Cancel"]])
        await bot.send_message(chat_id, "Choose:", reply_markup=markup)
    """
    rows = [
        [b if isinstance(b, dict) else {"text": b} for b in row]
        for row in buttons
    ]
    return {
        "keyboard": rows,
        "resize_keyboard": resize_keyboard,
        "one_time_keyboard": one_time_keyboard,
        "selective": selective,
    }


def remove_keyboard(*, selective: bool = False) -> Dict[str, Any]:
    """Build a `ReplyKeyboardRemove` dict, to hide a previously-shown
    custom reply keyboard."""
    return {"remove_keyboard": True, "selective": selective}


def force_reply(*, selective: bool = False, input_field_placeholder: str = None) -> Dict[str, Any]:
    """Build a `ForceReply` dict, to prompt the user's client to show
    a reply interface as if they'd tapped "Reply" on this message."""
    result = {"force_reply": True, "selective": selective}
    if input_field_placeholder is not None:
        result["input_field_placeholder"] = input_field_placeholder
    return result


# Also expose these on BotClient itself, so `bot.inline_keyboard(...)`
# works directly -- not just `from spluslib.bot_client import
# inline_keyboard`. This must happen here, after the functions above
# are defined, since BotClient is defined earlier in this file. See
# the comment on BotClient.get_my_commands for why this (a real class
# attribute) is what makes it safe from the __getattr__ passthrough,
# rather than a separate wrapper method defined inside the class body.
BotClient.inline_keyboard = staticmethod(inline_keyboard)
BotClient.reply_keyboard = staticmethod(reply_keyboard)
BotClient.remove_keyboard = staticmethod(remove_keyboard)
BotClient.force_reply = staticmethod(force_reply)

