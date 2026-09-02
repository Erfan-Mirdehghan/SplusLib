"""
Type stub for Message.

`Message` resolves attributes like `.text`, `.reply`, `.sender` dynamically
at runtime (it wraps and patches a raw `types.Message` TL object), so tools
like Pylance/VS Code can't see them just from reading message.py and offer
no autocomplete on `event.message.reply(...)` or `event.reply(...)`.

This stub declares the same shape statically, purely for editor tooling --
it has zero effect on runtime behaviour. Keep it in sync with message.py
when adding/removing public members there.
"""
from typing import Any, Optional, List, Union

from ...client.soroushclient import SoroushClient
from .forward import Forward


class Message:
    id: int
    peer_id: Any
    from_id: Any
    date: int
    message: Optional[str]
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
    ttl_period: Optional[int]

    @property
    def client(self) -> SoroushClient: ...

    @property
    def is_me(self) -> bool: ...

    @property
    def text(self) -> Optional[str]: ...
    @text.setter
    def text(self, value: str) -> None: ...

    @property
    def raw_text(self) -> Optional[str]: ...
    @raw_text.setter
    def raw_text(self, value: str) -> None: ...

    @property
    def is_reply(self) -> bool: ...

    @property
    def is_private(self) -> bool: ...

    @property
    def is_group(self) -> bool: ...

    @property
    def is_channel(self) -> bool: ...

    @property
    def forward(self) -> Optional[Forward]: ...

    @property
    def reply_to_chat(self) -> Any: ...

    @property
    def reply_to_sender(self) -> Any: ...

    @property
    def buttons(self) -> Optional[list]: ...

    async def get_buttons(self) -> Optional[list]: ...

    @property
    def button_count(self) -> int: ...

    @property
    def file(self) -> Any: ...

    @property
    def photo(self) -> Any: ...

    @property
    def document(self) -> Any: ...

    @property
    def web_preview(self) -> Any: ...

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
    def game(self) -> Any: ...

    @property
    def geo(self) -> Any: ...

    @property
    def invoice(self) -> Any: ...

    @property
    def poll(self) -> Any: ...

    @property
    def venue(self) -> Any: ...

    @property
    def dice(self) -> Any: ...

    @property
    def action_entities(self) -> Optional[list]: ...

    @property
    def via_bot(self) -> Any: ...

    @property
    def via_input_bot(self) -> Any: ...

    @property
    def reply_to_msg_id(self) -> Optional[int]: ...

    @property
    def to_id(self) -> Any: ...

    def get_entities_text(self, cls: Any = ...) -> list: ...

    async def get_reply_message(self) -> Optional["Message"]: ...

    async def respond(self, *args: Any, **kwargs: Any) -> "Message": ...

    async def reply(self, *args: Any, **kwargs: Any) -> "Message": ...

    async def forward_to(self, *args: Any, **kwargs: Any) -> Union["Message", List["Message"]]: ...

    async def edit(self, *args: Any, **kwargs: Any) -> Union["Message", bool]: ...

    async def delete(self, *args: Any, **kwargs: Any) -> Any: ...

    async def download_media(self, *args: Any, **kwargs: Any) -> Optional[Union[str, bytes]]: ...

    async def click(self, i: Optional[int] = ..., j: Optional[int] = ..., *args: Any, **kwargs: Any) -> Any: ...

    async def mark_read(self) -> None: ...

    async def pin(self, *, notify: bool = ..., pm_oneside: bool = ...) -> "Message": ...

    async def unpin(self) -> None: ...

    # Delegated from SenderGetter / ChatGetter mixins -- declared here too
    # since attribute access on Message goes through __getattr__.
    sender_id: Optional[int]
    chat_id: Optional[int]

    async def get_sender(self) -> Any: ...
    async def get_input_sender(self) -> Any: ...
    async def get_chat(self) -> Any: ...
    async def get_input_chat(self) -> Any: ...
