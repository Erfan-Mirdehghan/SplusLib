"""
Events module - provides clean event types for SplusClient
"""

from ._base import events as splus_events

# Re-export spluspy events with simplified names
NewMessage = splus_events.NewMessage
MessageEdited = splus_events.MessageEdited
MessageDeleted = splus_events.MessageDeleted
MessageRead = splus_events.MessageRead
ChatAction = splus_events.ChatAction
UserUpdate = splus_events.UserUpdate
CallbackQuery = splus_events.CallbackQuery
InlineQuery = splus_events.InlineQuery
Album = splus_events.Album
Raw = splus_events.Raw
StopPropagation = splus_events.StopPropagation

# Aliases for convenience
Message = NewMessage
Edited = MessageEdited
Deleted = MessageDeleted
Action = ChatAction
Update = UserUpdate
Callback = CallbackQuery
Inline = InlineQuery

# Custom event classes for common use cases
class Command:
    """Event filter for commands like /start, /help, etc."""
    def __init__(self, commands: list, prefixes: str = "/"):
        self.commands = commands if isinstance(commands, list) else [commands]
        self.prefixes = prefixes

    def __call__(self, event):
        text = event.raw_text or ""
        for prefix in self.prefixes:
            for cmd in self.commands:
                if text.startswith(f"{prefix}{cmd}"):
                    return True
        return False


class Text:
    """Event filter for text matching."""
    def __init__(self, pattern: str = None, contains: str = None, regex: str = None):
        self.pattern = pattern
        self.contains = contains
        self.regex = regex
        import re
        if regex:
            self._compiled = re.compile(regex)

    def __call__(self, event):
        text = event.raw_text or ""
        if self.pattern and text == self.pattern:
            return True
        if self.contains and self.contains in text:
            return True
        if self.regex and self._compiled.search(text):
            return True
        return False


class Private:
    """Filter for private messages."""
    def __call__(self, event):
        return event.is_private


class Group:
    """Filter for group messages."""
    def __call__(self, event):
        return event.is_group


class Channel:
    """Filter for channel messages."""
    def __call__(self, event):
        return event.is_channel


class Incoming:
    """Filter for incoming messages."""
    def __call__(self, event):
        return event.incoming


class Outgoing:
    """Filter for outgoing messages."""
    def __call__(self, event):
        return event.outgoing


# Combine multiple filters with AND
class And:
    """Combine multiple filters with AND logic."""
    def __init__(self, *filters):
        self.filters = filters

    def __call__(self, event):
        return all(f(event) for f in self.filters)


# Combine multiple filters with OR
class Or:
    """Combine multiple filters with OR logic."""
    def __init__(self, *filters):
        self.filters = filters

    def __call__(self, event):
        return any(f(event) for f in self.filters)


__all__ = [
    "NewMessage",
    "MessageEdited",
    "MessageDeleted",
    "MessageRead",
    "ChatAction",
    "UserUpdate",
    "CallbackQuery",
    "InlineQuery",
    "Album",
    "Raw",
    "StopPropagation",
    "Message",
    "Edited",
    "Deleted",
    "Action",
    "Update",
    "Callback",
    "Inline",
    "Command",
    "Text",
    "Private",
    "Group",
    "Channel",
    "Incoming",
    "Outgoing",
    "And",
    "Or",
]