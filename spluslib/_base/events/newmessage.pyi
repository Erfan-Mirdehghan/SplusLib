"""
Type stub for NewMessage.Event (and MessageEdited.Event, which subclasses
it with no changes).

At runtime, `Event` proxies unknown attribute access to `self.message`
(a `Message` instance) via `__getattr__`/`__setattr__` -- see newmessage.py.
That means `event.reply(...)`, `event.text`, `event.sender_id`, etc. all
work fine when you run the code, but editors have no static declaration to
read, so `event.` doesn't offer them in autocomplete and `event.reply`
shows as an unresolved attribute.

This stub re-exposes the same public surface as Message directly on Event,
purely for editor tooling. It has no effect on runtime behaviour -- keep it
in sync with message.pyi / message.py when the underlying API changes.
"""
from typing import Any, Optional, List, Union, Pattern, Match

from ..client.soroushclient import SoroushClient
from ..tl.custom.message import Message
from ..tl.custom.forward import Forward


class NewMessage:
    # NOTE: intentionally has NO base classes here (not EventCommon,
    # not Message), even though at runtime Event *is* an EventCommon
    # subclass that proxies to a wrapped Message. EventCommon's real
    # (non-stub) class has metaclass ABCMeta (via abc.ABC), while a
    # stub class declared with no explicit base gets the plain `type`
    # metaclass. Declaring `class Event(EventCommon, Message)` here
    # mixes those two metaclasses, which Pylance cannot resolve --
    # it silently drops member resolution for the whole class instead
    # of erroring, which is what caused `.reply` etc. to go unresolved.
    # Keeping Event flat (no bases) sidesteps the conflict entirely;
    # every member Event actually exposes (its own + everything
    # forwarded from EventCommon/Message) is declared explicitly below.
    class Event:
        pattern_match: Optional[Match]
        message: Message

        # Everything below mirrors tl.custom.message.Message's stub --
        # present because Event.__getattr__ forwards here at runtime.
        id: int
        date: int
        text: Optional[str]
        raw_text: Optional[str]
        out: bool
        mentioned: bool
        media_unread: bool
        silent: bool
        post: bool
        entities: Optional[list]
        media: Any
        reply_markup: Any
        views: Optional[int]
        forwards: Optional[int]
        edit_date: Optional[int]
        grouped_id: Optional[int]
        reply_to: Any
        via_bot_id: Optional[int]
        sender_id: Optional[int]
        chat_id: Optional[int]
        original_update: Any

        @property
        def client(self) -> SoroushClient: ...

        # -- from EventCommon -> ChatGetter --
        @property
        def chat(self) -> Any: ...

        @property
        def input_chat(self) -> Any: ...

        @property
        def is_private(self) -> bool: ...

        @property
        def is_group(self) -> bool: ...

        @property
        def is_channel(self) -> bool: ...

        async def get_input_chat(self) -> Any: ...

        def to_dict(self) -> dict: ...

        def stringify(self) -> str: ...

        @property
        def is_reply(self) -> bool: ...

        @property
        def is_me(self) -> bool: ...

        @property
        def forward(self) -> Optional[Forward]: ...

        @property
        def buttons(self) -> Optional[list]: ...

        @property
        def file(self) -> Any: ...

        @property
        def photo(self) -> Any: ...

        @property
        def document(self) -> Any: ...

        @property
        def audio(self) -> Any: ...

        @property
        def voice(self) -> Any: ...

        @property
        def video(self) -> Any: ...

        @property
        def video_note(self) -> Any: ...

        @property
        def gif(self) -> Any: ...

        @property
        def sticker(self) -> Any: ...

        @property
        def contact(self) -> Any: ...

        @property
        def poll(self) -> Any: ...

        @property
        def dice(self) -> Any: ...

        @property
        def geo(self) -> Any: ...

        @property
        def venue(self) -> Any: ...

        async def get_reply_message(self) -> Optional[Message]: ...

        async def respond(self, *args: Any, **kwargs: Any) -> Message: ...

        async def reply(self, *args: Any, **kwargs: Any) -> Message: ...

        async def forward_to(self, *args: Any, **kwargs: Any) -> Union[Message, List[Message]]: ...

        async def edit(self, *args: Any, **kwargs: Any) -> Union[Message, bool]: ...

        async def delete(self, *args: Any, **kwargs: Any) -> Any: ...

        async def download_media(self, *args: Any, **kwargs: Any) -> Optional[Union[str, bytes]]: ...

        async def click(self, i: Optional[int] = ..., j: Optional[int] = ..., *args: Any, **kwargs: Any) -> Any: ...

        async def mark_read(self) -> None: ...

        async def pin(self, *, notify: bool = ..., pm_oneside: bool = ...) -> Message: ...

        async def unpin(self) -> None: ...

        async def get_sender(self) -> Any: ...
        async def get_chat(self) -> Any: ...
