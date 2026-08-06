# Spluslib - High-level Soroush Plus Userbot Library

A clean, simplified Python library for building userbots on **Soroush Plus** messenger. This library is designed for **user accounts (userbots)**, not bots with tokens.

## Features

- **Simple API**: High-level methods like `send_message()`, `get_chats()`, `ban_member()` instead of low-level Telethon calls
- **Easy Authentication**: `start(phone)` handles connection and login automatically
- **Event Handlers**: Decorator-based event handling with filters
- **Type Hints**: Full type annotations for better IDE support
- **Built-in Fixes**: Patches for known Soroush Plus API limitations
- **Group Call Support**: Create, join, and manage group calls

## Installation

```bash
pip install spluslib
```

Or install from source:
```bash
cd "C:\Users\Erfan\Desktop\Splus Lib"
pip install -e .
```

## Requirements

- Python 3.8+
- `aiohttp`, `pyaes`, `rsa`, `python-socks` (installed automatically)
- `tgcalls` (for audio streaming functionality, optional)

## Quick Start

```python
import asyncio
from spluslib import SplusClient, events

async def main():
    # Create client with session name
    client = SplusClient("my_session")

    # Connect and login (prompts for code if needed)
    await client.start("+989123456789")

    # Get your info
    me = await client.get_me()
    print(f"Logged in as: {me['first_name']} (@{me['username']})")

    # Send a message
    await client.send_message("me", "Hello from Splus!")

    # Event handler for new messages
    @client.on(events.NewMessage)
    async def handler(event):
        if event.raw_text == "ping":
            await event.reply("pong!")

    # Run until disconnected
    await client.run_until_disconnected()

asyncio.run(main())
```

## API Reference

### Client Lifecycle

| Method | Description |
|--------|-------------|
| `start(phone)` | Connect and authorize |
| `stop()` | Disconnect gracefully |
| `run_until_disconnected()` | Run event loop |
| `__aenter__` / `__aexit__` | Async context manager |

### Account Methods

| Method | Description |
|--------|-------------|
| `get_me()` | Get current user info |
| `update_profile(first_name, last_name, about)` | Update profile |
| `update_username(username)` | Change username |
| `set_profile_photo(photo)` | Set profile photo |
| `delete_profile_photos(photo_ids)` | Delete profile photos |

### Chat/Dialog Methods

| Method | Description |
|--------|-------------|
| `get_chats(limit)` | Get list of dialogs |
| `get_chat_info(chat_id)` | Get chat details |
| `get_chat_members(chat_id, filter_admins)` | Get members (with admin caching) |
| `is_admin(chat_id, user_id)` | Check if user is admin |

### Contact Methods

| Method | Description |
|--------|-------------|
| `add_contact(phone, first_name, last_name)` | Add contact |
| `get_contacts()` | Get all contacts |
| `delete_contact(user_id)` | Delete contact |

### Chat Management

| Method | Description |
|--------|-------------|
| `ban_member(chat_id, user_id, permanent)` | Ban/kick member |
| `unban_member(chat_id, user_id)` | Unban member |
| `mute_member(chat_id, user_id, minutes)` | Mute member |
| `set_admin(chat_id, user_id, rank, **perms)` | Promote to admin |
| `remove_admin(chat_id, user_id)` | Demote admin |
| `create_channel(title, description, megagroup)` | Create channel/group |
| `create_group(title, users)` | Create group with users |
| `leave_chat(chat_id)` | Leave chat |
| `join_group_by_invite(invite_link)` | Join a group/channel using an invite link |

### Message Methods

| Method | Description |
|--------|-------------|
| `send_message(chat_id, text, **kwargs)` | Send text message |
| `get_messages(chat_id, limit, **kwargs)` | Get messages |
| `get_message_by_id(chat_id, msg_id)` | Get single message |
| `delete_messages(chat_id, msg_ids, revoke)` | Delete messages |
| `edit_message(chat_id, msg_id, text, **kwargs)` | Edit message |
| `forward_messages(chat_id, msg_ids, from_chat)` | Forward messages |
| `pin_message(chat_id, msg_id, notify)` | Pin message |
| `unpin_message(chat_id, msg_id)` | Unpin message |
| `react_message(chat_id, msg_id, emoji)` | Add reaction |
| `get_reactions(chat_id, msg_id)` | Get reactions |
| `search_messages(chat_id, query, limit)` | Search messages |

### File/Media Methods

| Method | Description |
|--------|-------------|
| `send_file(chat_id, file, **kwargs)` | Send any file |
| `send_photo(chat_id, photo, **kwargs)` | Send photo |
| `send_video(chat_id, video, **kwargs)` | Send video |
| `send_document(chat_id, document, **kwargs)` | Send document |
| `send_voice(chat_id, voice, **kwargs)` | Send voice message |
| `send_audio(chat_id, audio, **kwargs)` | Send audio |
| `download_media(message, file_path)` | Download media |

### Group Call Methods (Conference Calls)

Soroush Plus uses a **Conference Call** system with meet links (e.g., `https://splus.ir/meet/mkx-ofx-yfh`). Calls can be standalone (no chat required) or associated with a chat.

| Method | Description |
|--------|-------------|
| `create_group_call(title, chat_id=None)` | Create a new conference call. Returns meet link. Optional `chat_id` to send link to a chat. |
| `join_group_call(slug=None, meet_link=None, muted=True, video_stopped=True)` | Join an existing conference call via slug or full meet link. |
| `leave_group_call(slug=None, meet_link=None)` | Leave a conference call. |
| `end_group_call(slug=None, meet_link=None)` | End/discard a conference call. |
| `get_group_call_info(slug=None, meet_link=None)` | Get current call info. |
| `resolve_group_call(slug)` | Resolve a call by slug to get full details (id, access_hash, participants). |
| `mute_participant(slug, participant_id, track_id=None, muted=True)` | Mute/unmute a participant. |
| `remove_participant(slug, participant_id)` | Remove a participant from call. |
| `ban_participant(slug, user_id, user_access_hash)` | Ban a participant. |
| `unban_participant(slug, user_id, user_access_hash)` | Unban a participant. |
| `get_banned_participants(slug)` | Get list of banned participants. |
| `get_active_group_calls(limit=20, offset=None)` | Get list of active conference calls. |

#### Group Call Example

```python
from spluslib import SplusClient, events

async def main():
    client = SplusClient("my_session")
    await client.start("+989123456789")

    # Create a standalone conference call (no chat needed)
    call = await client.create_group_call(title="Meeting Call")
    print(f"Created call: {call}")
    print(f"Meet Link: {call['meet_link']}")  # e.g., https://splus.ir/meet/mkx-ofx-yfh
    print(f"Slug: {call['slug']}")

    # Join the call using slug or full meet link
    await client.join_group_call(slug=call['slug'], muted=True, video_stopped=True)

    # Or join with full meet link
    # await client.join_group_call(meet_link="https://splus.ir/meet/mkx-ofx-yfh")

    # Get call info
    info = await client.get_group_call_info(slug=call['slug'])
    print(f"Call info: {info}")

    # Mute a participant (need participant_id from call info)
    # await client.mute_participant(call['slug'], "participant_id", muted=True)

    # Leave the call
    await client.leave_group_call(slug=call['slug'])

    # Or end the call entirely (discard)
    # await client.end_group_call(slug=call['slug'])

    await client.run_until_disconnected()
```

> **Note**: Audio streaming (playing audio files, radio-like streaming) requires the `tgcalls` library to be installed separately. The conference call methods above provide the signaling layer for creating and managing calls, but actual audio transmission needs `tgcalls` or similar library.

## Music Bot Example

A complete music bot example is available in `example_music_bot.py` that demonstrates:

- **Call Management**: Create/join/leave/end group calls
- **Music Playback**: Search songs via API, download, and play
- **Queue System**: Add songs to queue, skip, show now playing
- **Commands**: `/call`, `/join`, `/play`, `/queue`, `/skip`, `/stop`, `/np`, `/leave`, `/help`

### Installation for Real Audio Streaming

```bash
pip install spluslib tgcalls aiohttp
```

### Commands

| Command | Description |
|---------|-------------|
| `/call` | Create group call in current chat |
| `/join <slug\|link>` | Join existing group call |
| `/play <song>` | Search and play song |
| `/queue <song>` | Add song to queue |
| `/skip` | Skip current song |
| `/stop` | Stop playback |
| `/np` | Show now playing |
| `/listqueue` | Show queue |
| `/leave` | Leave current call |
| `/leave end` | End call completely |
| `/help` | Show all commands |

### Real Audio Streaming with tgcalls

The library provides the **signaling layer** (create/join calls, get LiveKit url/token). For actual audio streaming:

```python
from tgcalls import TgCalls

# After joining a call, you get LiveKit url/token
call_result = await client.join_group_call(slug="mkx-ofx-yfh")

if call_result.get('url') and call_result.get('token'):
    tgcalls = TgCalls(client._client)
    await tgcalls.start()
    
    # Join and stream audio
    await tgcalls.join_group_call(
        chat_id=chat_id,
        audio_file="song.mp3"
    )
```

See `example_music_bot.py` for a complete implementation with fallback simulation.

### Event Filters

```python
from spluslib import events

# Command filter
@client.on(events.NewMessage, func=events.Command(["start", "help"]))
async def cmd_handler(event):
    await event.reply("Welcome!")

# Text filter
@client.on(events.NewMessage, func=events.Text(contains="hello"))
async def hello_handler(event):
    await event.reply("Hi there!")

# Combine filters
@client.on(events.NewMessage, func=events.And(events.Private, events.Incoming))
async def private_incoming(event):
    ...

# Available filters:
# - events.Command(commands, prefixes="/")
# - events.Text(pattern, contains, regex)
# - events.Private / events.Group / events.Channel
# - events.Incoming / events.Outgoing
# - events.And(*filters) / events.Or(*filters)
```

## Message Object

Event messages and returned messages are dicts with:
```python
{
    "id": 123,
    "text": "message text",
    "date": 1699999999.0,  # Unix timestamp
    "from_id": 123456,
    "from_user": {...},     # User dict
    "chat_id": -100123456,
    "chat": {...},          # Chat dict
    "out": False,
    "mentioned": False,
    "reply_to_msg_id": 122,
    "reactions": [...],
    "views": 100,
    "forwards": 5,
}
```

## Known Soroush Plus Limitations (Handled)

1. **No inline/keyboard buttons** - Soroush Plus doesn't support buttons, so they're not included
2. **Admin caching** - `get_permissions(chat, user)` doesn't work for single users; library uses cached `iter_participants` with `ChannelParticipantsAdmins` filter
3. **WebSocket only** - Connection is via WebSocket to `im-server.splus.ir:443` (handled by base library)
4. **No `GetParticipantRequest`** - Use batch participant fetching instead

## Project Structure

```
spluslib/
├── __init__.py       # Main exports
├── client.py         # SplusClient - high-level wrapper with group call methods
├── events.py         # Event types and filters
├── pyproject.toml    # Package configuration
└── setup.py          # Package configuration
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Author

**Erfan Mirdehghan**