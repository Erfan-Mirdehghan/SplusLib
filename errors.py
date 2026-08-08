"""
spluslib.errors -- friendly, simple exceptions for SplusLib.

The underlying engine (spluslib/_base, a Soroush Plus fork of Telethon)
already has hundreds of very specific, low-level RPC error classes
(ChatAdminRequiredError, UserBannedInChannelError, FloodWaitError, ...).
Those are accurate but not fun to catch by hand in normal bot code.

This module gives you a small, predictable set of exceptions that map
onto real-world situations, so you can write:

    try:
        await bot.set_admin(chat_id, user_id)
    except errors.NotAdminError:
        await bot.send_message(chat_id, "I'm not an admin here.")

instead of having to know the exact underlying RPC error class name.

Every SplusError also carries the original low-level exception (if any)
on `.original`, so if you ever need the raw details they're still there.
"""

from __future__ import annotations

from typing import Optional

from ._base.errors import rpcerrorlist as _rpc
from ._base.errors.common import MultiError as _MultiError


class SplusError(Exception):
    """Base class for every exception spluslib raises on purpose."""

    def __init__(self, message: str = "", *, original: Optional[Exception] = None):
        super().__init__(message or self.__class__.__doc__ or "")
        self.original = original


# --------------------------------------------------------------------- #
# Permission / membership errors
# --------------------------------------------------------------------- #

class NotAdminError(SplusError):
    """You (the bot account) are not an admin in this chat, or don't
    have the specific admin right needed for this action."""


class NoPermissionError(SplusError):
    """The action is not allowed here (chat settings, restrictions,
    or Soroush Plus itself is blocking it) -- distinct from simply
    not being an admin."""


class UserNotFoundError(SplusError):
    """Could not find that user (wrong id/username, or the user
    doesn't exist)."""


class UserNotInChatError(SplusError):
    """That user is not a member of this chat."""


class UserAlreadyInChatError(SplusError):
    """That user is already a member of this chat."""


class UserBlockedYouError(SplusError):
    """That user has blocked you, so this action isn't possible."""


class UserPrivacyError(SplusError):
    """Blocked by the target user's privacy settings."""


class UserDeactivatedError(SplusError):
    """That account has been deleted or deactivated."""


# --------------------------------------------------------------------- #
# Chat / entity errors
# --------------------------------------------------------------------- #

class ChatNotFoundError(SplusError):
    """Could not find that chat/group/channel (wrong id, or the bot
    account isn't in it)."""


class InvalidChatError(SplusError):
    """This id/link doesn't refer to a valid chat."""


# --------------------------------------------------------------------- #
# Message / content errors
# --------------------------------------------------------------------- #

class MessageTooLongError(SplusError):
    """The message text is longer than Soroush Plus allows."""


class MessageNotFoundError(SplusError):
    """Could not find that message (wrong id, or it was deleted)."""


class MessageNotModifiedError(SplusError):
    """edit_message() was called with content identical to the
    existing message, so there was nothing to change."""


class EmptyMessageError(SplusError):
    """Message text/caption can't be empty for this action."""


class InvalidMediaError(SplusError):
    """The file/photo/video you tried to send was rejected as
    invalid, unreadable, or an unsupported type."""


class FileTooLargeError(SplusError):
    """The file is larger than Soroush Plus allows for this kind of
    upload."""


# --------------------------------------------------------------------- #
# Username errors
# --------------------------------------------------------------------- #

class InvalidUsernameError(SplusError):
    """That username isn't in a valid format."""


class UsernameTakenError(SplusError):
    """That username is already taken by someone else."""


class UsernameNotFoundError(SplusError):
    """No account/chat has that username."""


# --------------------------------------------------------------------- #
# Rate limiting / flood
# --------------------------------------------------------------------- #

class FloodWaitError(SplusError):
    """You're being rate-limited by Soroush Plus. `.seconds` tells you
    how long to wait before retrying this exact action."""

    def __init__(self, seconds: int, *, original: Optional[Exception] = None):
        self.seconds = seconds
        super().__init__(
            f"Rate-limited: wait {seconds} seconds before retrying.",
            original=original,
        )


class TooManyRequestsError(SplusError):
    """Sending messages/requests too fast in general (not tied to one
    specific action like FloodWaitError)."""


# --------------------------------------------------------------------- #
# Auth / login errors
# --------------------------------------------------------------------- #

class InvalidPhoneError(SplusError):
    """That phone number isn't valid or isn't registered."""


class InvalidCodeError(SplusError):
    """The login code you entered is wrong."""


class ExpiredCodeError(SplusError):
    """The login code expired before it was used -- request a new one."""


class InvalidPasswordError(SplusError):
    """The 2FA password you entered is wrong."""


class PasswordNeededError(SplusError):
    """This account has 2FA enabled -- a password is required to
    finish logging in."""


# --------------------------------------------------------------------- #
# Conference call errors
# --------------------------------------------------------------------- #

class CallNotFoundError(SplusError):
    """Could not find/resolve that conference call (wrong slug/link,
    or the call has ended)."""


class NotInCallError(SplusError):
    """This action needs an active call connection -- call
    CallAudioSession.connect() first."""


class AlreadyInCallError(SplusError):
    """Already connected to a call -- call disconnect() before
    connecting to a different one."""


# --------------------------------------------------------------------- #
# Fallback for anything we don't have a specific mapping for yet
# --------------------------------------------------------------------- #

class UnknownError(SplusError):
    """Something went wrong and spluslib doesn't have a specific
    exception for it yet. Check `.original` for the real underlying
    error."""


# --------------------------------------------------------------------- #
# The actual mapping from low-level RPC error classes to the friendly
# ones above. This intentionally covers the errors a userbot actually
# runs into day to day; anything not listed here falls back to
# UnknownError (with the real exception preserved on `.original`), it
# is not silently swallowed.
# --------------------------------------------------------------------- #

_ERROR_MAP = {
    # Permission / admin
    _rpc.ChatAdminRequiredError: NotAdminError,
    _rpc.ChatAdminInviteRequiredError: NotAdminError,
    _rpc.ChatWriteForbiddenError: NoPermissionError,
    _rpc.ChatForbiddenError: NoPermissionError,
    _rpc.ChatGuestSendForbiddenError: NoPermissionError,
    _rpc.ChatSendMediaForbiddenError: NoPermissionError,
    _rpc.ChatSendStickersForbiddenError: NoPermissionError,
    _rpc.ChatSendGifsForbiddenError: NoPermissionError,
    _rpc.ChatSendGameForbiddenError: NoPermissionError,
    _rpc.ChatSendPollForbiddenError: NoPermissionError,
    _rpc.ChatRestrictedError: NoPermissionError,
    _rpc.ChatForwardsRestrictedError: NoPermissionError,
    _rpc.BroadcastForbiddenError: NoPermissionError,

    # Users / membership
    _rpc.UserNotParticipantError: UserNotInChatError,
    _rpc.UserAlreadyParticipantError: UserAlreadyInChatError,
    _rpc.UserBlockedError: UserBlockedYouError,
    _rpc.UserPrivacyRestrictedError: UserPrivacyError,
    _rpc.UserDeactivatedError: UserDeactivatedError,
    _rpc.UserDeactivatedBanError: UserDeactivatedError,
    _rpc.UserKickedError: UserNotInChatError,
    _rpc.UserBannedInChannelError: NoPermissionError,
    _rpc.InputUserDeactivatedError: UserDeactivatedError,

    # Chats
    _rpc.ChannelInvalidError: ChatNotFoundError,
    _rpc.ChannelIdInvalidError: ChatNotFoundError,
    _rpc.ChatIdInvalidError: ChatNotFoundError,
    _rpc.ChatInvalidError: InvalidChatError,
    _rpc.PeerIdInvalidError: ChatNotFoundError,

    # Messages / media
    _rpc.MessageTooLongError: MessageTooLongError,
    _rpc.MessageIdInvalidError: MessageNotFoundError,
    _rpc.MessageNotModifiedError: MessageNotModifiedError,
    _rpc.MessageEmptyError: EmptyMessageError,
    _rpc.MediaEmptyError: InvalidMediaError,
    _rpc.MediaInvalidError: InvalidMediaError,

    # Usernames
    _rpc.UsernameInvalidError: InvalidUsernameError,
    _rpc.UsernameOccupiedError: UsernameTakenError,
    _rpc.UsernameNotOccupiedError: UsernameNotFoundError,

    # Flood
    _rpc.FloodWaitError: FloodWaitError,
    _rpc.PeerFloodError: TooManyRequestsError,

    # Auth
    _rpc.PhoneNumberInvalidError: InvalidPhoneError,
    _rpc.PhoneCodeInvalidError: InvalidCodeError,
    _rpc.PhoneCodeExpiredError: ExpiredCodeError,
    _rpc.PhoneCodeEmptyError: InvalidCodeError,
    _rpc.PasswordHashInvalidError: InvalidPasswordError,
    _rpc.SessionPasswordNeededError: PasswordNeededError,
}


def translate(exc: Exception) -> SplusError:
    """
    Translate a raw exception (usually from the underlying engine)
    into a friendly SplusError subclass. If exc is already a
    SplusError, it's returned as-is. Unknown exception types become
    UnknownError, with the real exception kept on `.original` so
    nothing is ever silently lost.
    """
    if isinstance(exc, SplusError):
        return exc

    mapped = _ERROR_MAP.get(type(exc))
    if mapped is not None:
        if mapped is FloodWaitError:
            seconds = getattr(exc, "seconds", 0)
            return FloodWaitError(seconds, original=exc)
        return mapped(str(exc) or mapped.__doc__ or "", original=exc)

    # Walk the MRO in case it's a subclass of something we do map
    # (the rpcerrorlist classes are a flat hierarchy in practice, but
    # this keeps us robust if that ever changes).
    for exc_type, mapped_type in _ERROR_MAP.items():
        if isinstance(exc, exc_type):
            if mapped_type is FloodWaitError:
                seconds = getattr(exc, "seconds", 0)
                return FloodWaitError(seconds, original=exc)
            return mapped_type(str(exc) or mapped_type.__doc__ or "", original=exc)

    return UnknownError(str(exc) or "An unexpected error occurred.", original=exc)


__all__ = [
    "SplusError",
    "NotAdminError",
    "NoPermissionError",
    "UserNotFoundError",
    "UserNotInChatError",
    "UserAlreadyInChatError",
    "UserBlockedYouError",
    "UserPrivacyError",
    "UserDeactivatedError",
    "ChatNotFoundError",
    "InvalidChatError",
    "MessageTooLongError",
    "MessageNotFoundError",
    "MessageNotModifiedError",
    "EmptyMessageError",
    "InvalidMediaError",
    "FileTooLargeError",
    "InvalidUsernameError",
    "UsernameTakenError",
    "UsernameNotFoundError",
    "FloodWaitError",
    "TooManyRequestsError",
    "InvalidPhoneError",
    "InvalidCodeError",
    "ExpiredCodeError",
    "InvalidPasswordError",
    "PasswordNeededError",
    "CallNotFoundError",
    "NotInCallError",
    "AlreadyInCallError",
    "UnknownError",
    "translate",
]
