pypi https://pypi.org/project/spluslib/

# SplusLib

**Version 2.0.2**

A complete, high-level Python userbot library for **Soroush Plus**, built on a
Soroush-Plus-specific fork of the MTProto engine that powers Telethon.
Messaging, files/media, stories, group and account management, and real
LiveKit-based voice/conference calls — all through a simple, consistent API.

> 📄 مستندات فارسی: پایین همین فایل، بعد از بخش انگلیسی. / Persian
> documentation is further down in this same file, after the English section.

---

## Table of Contents (English)

- [What's new in 2.0.0](#whats-new-in-200)
- [What's in this repo](#whats-in-this-repo)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Core concepts](#core-concepts)
- [Events](#events)
- [Event & message object API](#event--message-object-api)
- [Complete `SplusClient` method reference](#complete-splusclient-method-reference)
- [Messaging](#messaging)
- [Files, photos, video, voice, audio](#files-photos-video-voice-audio)
- [Stories](#stories)
- [Account management](#account-management)
- [Group / chat management](#group--chat-management)
- [Invite links & join requests](#invite-links--join-requests)
- [Contacts](#contacts)
- [Conference calls (join + play audio)](#conference-calls-join--play-audio)
- [Error handling](#error-handling)
- [Full method reference](#full-method-reference)
- [Known limitations](#known-limitations)
- [For AI assistants reading this repo](#for-ai-assistants-reading-this-repo)

---
# Installation 
```bash
pip install spluslib
```

## What's in 2.0.x

- **Stories.** Check if a user has an active story, list a peer's active
  stories, view/react/reply to a story, download a story's photo/video, and
  get a shareable story link — see [Stories](#stories).
- **Spoiler media.** `send_photo`/`send_video`/`send_file` accept
  `spoiler=True` to send blurred "tap to reveal" media.
- **Block/unblock.** `block_user()` / `unblock_user()`, including a
  stories-only block option.
- **Invite link management.** List a chat's existing invite links, edit
  their settings or revoke them, delete them — beyond just creating new
  ones. See [Invite links & join requests](#invite-links--join-requests).
- **Join requests.** List pending join requests for a chat, approve or
  decline them individually, or decline all at once.
- **Chat usernames.** Check availability and set a public username for a
  group/channel you admin.
- **Identifiable device name.** `SplusClient(session_name)` now shows up in
  Settings → Devices as `"<session_name> (SplusLib)"` by default instead of
  a generic OS-based name, so each bot session is recognizable at a glance.
  Override with `device_model=...` if you want something else.

---

## What's in this repo

```
spluslib/
├── __init__.py       # package entry point, exports SplusClient, events, errors, CallAudioSession
├── client.py          # SplusClient -- the main high-level API (~3300 lines, ~105 public methods)
├── events.py           # friendly re-exports of the event classes (NewMessage, MessageEdited, ...)
├── errors.py            # friendly exception hierarchy (NotAdminError, FloodWaitError, ...)
├── call_audio.py          # CallAudioSession -- real LiveKit voice-call connection + audio playback
└── _base/                  # the vendored MTProto engine (a Soroush Plus fork of Telethon)
    ├── client/                 # low-level client mixins (messages, uploads, users, chats, ...)
    ├── crypto/                  # MTProto encryption
    ├── network/                  # connection/transport layer
    ├── sessions/                   # session storage (SQLite by default)
    ├── tl/                          # generated TL schema: types, functions, custom wrappers
    ├── events/                       # low-level event builders
    └── errors/                        # the full raw RPC error list (hundreds of specific classes)
```

**Everything ships in one folder.** There is no separate package to install
for the engine — `_base` (internally aliased to `spluspy` in `sys.modules` for
backward-compatible internal imports) is a private, vendored subpackage.
You only ever import from `spluslib`.

---

## Installation

```bash
# 1. Copy the spluslib/ folder into your project (or clone this repo)

# 2. Install the two external dependencies:
pip install livekit --break-system-packages
# ffmpeg must also be installed and on PATH (used only to decode audio
# files for call playback -- not needed if you never use CallAudioSession)
```

That's it. No `requirements.txt` beyond `livekit` — the MTProto engine
(`_base`) has no external dependencies beyond the Python standard library
(plus `pyaes`, `rsa`, `pysocks` which Telethon-family libraries typically
need; install them if your environment doesn't already have them:
`pip install pyaes rsa pysocks --break-system-packages`).

---

## Quick start

```python
import asyncio
from spluslib import SplusClient, events, errors

client = SplusClient("my_session")

@client.on_message(pattern=r"^/start$")
async def start_cmd(event):
    await event.reply("Hello! I'm alive.")

async def main():
    await client.start("+989123456789")   # phone number with country code
    await client.run_until_disconnected()

asyncio.run(main())
```

Run it, enter the login code when prompted (interactively, or via
`code_callback=` for non-interactive use), and the bot is live.

By default this session shows up in Settings → Devices as
`"my_session (SplusLib)"` — pass `device_model="..."` to `SplusClient(...)`
if you want a different label.

---

## Core concepts

- **One client, one account.** `SplusClient(session_name)` creates (or
  reuses) a local session file. Each `SplusClient` instance represents one
  logged-in Soroush Plus account.
- **Everything is `async`.** Every network-touching method is a coroutine —
  call them with `await` inside an `async def`, and run your entry point
  with `asyncio.run(...)`.
- **Dicts in, dicts out.** High-level methods return plain Python
  dictionaries (e.g. `{"id": ..., "text": ..., "chat_id": ...}`) rather than
  raw TL objects, so you don't need to know the underlying MTProto schema to
  use them.
- **Exceptions instead of `None`/`False` on failure.** Every method raises a
  `spluslib.errors.SplusError` subclass (see [Error handling](#error-handling))
  when something goes wrong — a permission problem, a not-found chat, a rate
  limit, etc. Methods don't silently return `None`/`False` and hide the
  reason.
- **Escape hatch.** Anything not wrapped by `SplusClient` is still reachable:
  `client._client` is the underlying `_base.SoroushClient` (Telethon-style)
  instance, and `SplusClient.__getattr__` transparently forwards unknown
  attribute lookups to it. So `await client.some_native_method(...)` works
  even if `some_native_method` isn't explicitly defined on `SplusClient`.

---

## Events

Instead of the verbose Telethon-style

```python
@client.on(events.NewMessage)
async def handler(event):
    ...
```

SplusLib gives you one short method per event type:

| Method | Fires on |
|---|---|
| `on_message(**filters)` | New incoming/outgoing messages |
| `on_edited(**filters)` | Edited messages |
| `on_deleted(**filters)` | Deleted messages (`event.deleted_ids`) |
| `on_read(**filters)` | Read receipts |
| `on_chat_action(**filters)` | Joins/leaves, title/photo changes, pins, group creation (`event.user_joined`, etc) |
| `on_user_update(**filters)` | Online/offline status, typing, profile photo changes |
| `on_callback(**filters)` | Inline button presses (`await event.answer(...)`) |
| `on_inline(**filters)` | Inline queries (`@bot query`) |
| `on_album(**filters)` | Grouped media (albums) |
| `on_raw(**filters)` | Raw, unprocessed updates (advanced use only) |

All the usual filter kwargs work exactly like Telethon's event filters,
since they're passed straight through: `pattern=`, `chats=`, `incoming=`,
`outgoing=`, `from_users=`, `blacklist_chats=`, `func=`, etc.

```python
@client.on_message(pattern=r"^/echo (.+)$")
async def echo(event):
    await event.reply(event.pattern_match.group(1))

@client.on_message(incoming=True, chats=[-100123456789])
async def only_this_group(event):
    ...
```

The original `@client.on(events.X, ...)` style still works too, for the
rarer cases the shortcuts don't cover, or if you just prefer it:

```python
from spluslib import events

@client.on(events.UserUpdate)
async def on_status_change(event):
    ...
```

You can also register/remove handlers programmatically instead of using
decorators: `client.add_event_handler(callback, event_type)` and
`client.remove_event_handler(callback, event_type)`.

---


## Event & message object API

`NewMessage.Event` is intentionally message-like. The event forwards unknown
attributes and methods to its underlying `Message` object, so code such as
`event.reply(...)`, `event.text`, `event.chat_id`, and `event.sender_id` works
directly. The event also exposes `event.message` when you want the underlying
message object explicitly.

### Common message properties

| Property | Description |
|---|---|
| `text` | Formatted message text using the client's parse mode |
| `raw_text` | Raw message text without formatting entities |
| `is_reply` | `True` when the message replies to another message or story |
| `reply_to_msg_id` | ID of the replied-to message, when available |
| `reply_to_chat` | Chat/entity containing the replied-to message, when available |
| `reply_to_sender` | Sender of the replied-to message, when available |
| `forward` | Forward metadata for forwarded messages |
| `buttons` | Inline/reply keyboard buttons, when present |
| `button_count` | Total number of buttons |
| `file` | Unified file wrapper for photo/document media |
| `photo` | Photo media, when present |
| `document` | Document media, when present |
| `audio` | Audio document, excluding voice notes |
| `voice` | Voice-message document |
| `video` | Video document |
| `video_note` | Round/video-note media |
| `gif` | Animated/GIF-like document |
| `sticker` | Sticker media |
| `contact` | Shared contact media |
| `game` | Game media |
| `geo` | Location/venue coordinates |
| `invoice` | Invoice/payment media |
| `poll` | Poll media |
| `venue` | Venue media |
| `dice` | Dice/media payload |
| `action_entities` | Entities involved in a service/action message |
| `via_bot` / `via_input_bot` | Bot attribution information |
| `to_id` | Destination peer information |

### Message methods

All network methods are async and should be awaited:

```python
@client.on_message()
async def handler(msg):
    # Reply to the incoming message
    await msg.reply("Hello!")

    # Send another message in the same chat, without replying
    await msg.respond("This is a separate message")

    # Edit the current message
    await msg.edit("Edited text")

    # Delete the current message
    await msg.delete()

    # Forward it somewhere
    await msg.forward_to("@another_chat")

    # Download attached media
    path = await msg.download_media("/tmp")

    # Mark as read
    await msg.mark_read()

    # Pin / unpin
    await msg.pin()
    await msg.unpin()
```

### Buttons and polls

`Message.click()` can activate an inline/reply button or vote in a poll.

```python
# By row/column
await msg.click(0, 0)

# By visible button text
await msg.click(text="Confirm")

# By callback data
await msg.click(data=b"payload")

# Vote in a poll by answer index
await msg.click(0)
```

You can also inspect the keyboard:

```python
buttons = await msg.get_buttons()

for row in buttons or []:
    for button in row:
        print(button.text)
```

### Reply context

```python
if msg.is_reply:
    replied = await msg.get_reply_message()
    print(replied.raw_text if replied else "Original message unavailable")
```

### Sender and chat helpers

```python
sender = await msg.get_sender()
chat = await msg.get_chat()

print(sender)
print(chat)
```

### Event-specific helpers

`CallbackQuery.Event` provides:

```python
await event.answer("Done!")
await event.respond("Response message")
await event.reply("Reply to the callback message")
await event.edit("Edited callback message")
await event.delete()
message = await event.get_message()
```

`ChatAction.Event` provides helpers such as:

```python
await event.get_user()
await event.get_added_by()
await event.get_kicked_by()
await event.get_users()
await event.get_input_user()
await event.get_input_users()
pinned = await event.get_pinned_message()
pinned_messages = await event.get_pinned_messages()
```

`Album.Event` supports message-like operations including:

```python
await event.respond("Album response")
await event.reply("Reply")
await event.forward_to("@another_chat")
await event.edit("Edited")
await event.delete()
await event.mark_read()
await event.pin()
```

### Event aliases and custom filters

`from spluslib import events` exposes the standard event classes plus
convenience aliases:

```python
events.Message      # alias for NewMessage
events.Edited       # alias for MessageEdited
events.Deleted      # alias for MessageDeleted
events.Action       # alias for ChatAction
events.Update       # alias for UserUpdate
events.Callback     # alias for CallbackQuery
events.Inline       # alias for InlineQuery
```

It also includes ready-to-use filters:

```python
@client.on_message(events.Command("start"))
async def start(msg):
    await msg.reply("Hello!")

@client.on_message(events.Text(contains="hello"))
async def hello(msg):
    await msg.reply("Hi!")

@client.on_message(events.Private())
async def private_only(msg):
    ...

@client.on_message(events.Group())
async def group_only(msg):
    ...

@client.on_message(events.And(events.Group(), events.Incoming()))
async def incoming_group(msg):
    ...
```

Available custom filters are `Command`, `Text`, `Private`, `Group`, `Channel`,
`Incoming`, `Outgoing`, `And`, and `Or`.

---

## Complete `SplusClient` method reference

The shipped `SplusClient` currently exposes the following public high-level API:

### Lifecycle & events

```text
start()
stop()
run_until_disconnected()
on()
add_event_handler()
remove_event_handler()
on_message()
on_edited()
on_update()
on_deleted()
on_read()
on_reaction()
on_chat_action()
on_user_update()
on_callback()
on_inline()
on_album()
on_raw()
```

### Account & contacts

```text
get_me()
update_profile()
update_username()
set_profile_photo()
delete_profile_photos()
block_user()
unblock_user()
add_contact()
get_contacts()
delete_contact()
get_user_by_phone()
report_user()
```

### Chats & groups

```text
set_chat_title()
set_chat_description()
set_chat_photo()
delete_chat_photo()
get_chats()
get_chat_info()
get_chat_members()
is_admin()
get_banned_users()
ban_member()
unban_member()
mute_member()
set_admin()
remove_admin()
create_channel()
create_group()
leave_chat()
join_group_by_invite()
check_chat_username()
set_chat_username()
```

### Invites & join requests

```text
get_chat_invite_link()
get_chat_invite_links()
edit_chat_invite_link()
delete_chat_invite_link()
get_join_requests()
approve_join_request()
decline_join_request()
decline_all_join_requests()
```

### Messages & reactions

```text
send_message()
mention_user()
get_messages()
get_message_by_id()
delete_messages()
edit_message()
forward_messages()
pin_message()
unpin_message()
react_message()
get_reactions()
search_messages()
report_message()
```

### Files & media

```text
send_file()
send_photo()
send_video()
send_document()
send_voice()
send_audio()
download_media()
```

All file upload methods that expose `progress=` support the built-in progress
display or a custom sync/async callback. `send_photo()`, `send_video()`, and
`send_file()` also support `spoiler=True` for supported media.

### Polls

```text
send_poll()
vote_poll()
close_poll()
get_poll_results()
```

### Stories

```text
get_story_link()
download_story()
get_user_stories()
has_story()
send_story_view()
send_story_reaction()
reply_to_story()
```

There is currently no `send_story()` method for posting a brand-new story.

### Conference calls

```text
create_group_call()
resolve_group_call()
join_group_call()
leave_group_call()
end_group_call()
get_group_call_info()
mute_participant()
remove_participant()
ban_participant()
unban_participant()
get_banned_participants()
get_active_group_calls()
```

### Legacy audio placeholders

```text
start_audio_stream()
play_audio_file()
play_audio_queue()
```

These legacy placeholders are deprecated no-ops in the shipped code; use
`CallAudioSession` for actual LiveKit audio playback.

---

## Version note

This README documents the public API shipped with the uploaded SplusLib source
and the current `2.0.2` PyPI release. The PyPI page lists `2.0.2` as the
latest release on August 16, 2026. The uploaded source archive itself still
contains an internal `__version__ = "2.0.0"` value, so the README version is
based on the published package version rather than that stale internal string.


## Messaging

```python
await client.send_message(chat_id, "Hello there!")

msgs = await client.get_messages(chat_id, limit=10)
msg = await client.get_message_by_id(chat_id, message_id)

await client.edit_message(chat_id, message_id, "New text")
await client.delete_messages(chat_id, [message_id, ...])
await client.forward_messages(from_chat_id, to_chat_id, [message_id, ...])

await client.pin_message(chat_id, message_id)
await client.unpin_message(chat_id, message_id)

await client.react_message(chat_id, message_id, "👍")
reactions = await client.get_reactions(chat_id, message_id)

results = await client.search_messages(chat_id, query="hello", limit=20)
```

---

## Files, photos, video, voice, audio

**You pass a file path (or URL, or raw bytes) directly — no manual byte
reading needed.** A console progress bar is shown by default.

```python
await client.send_photo(chat_id, "/path/to/photo.jpg")
await client.send_video(chat_id, "/path/to/movie.mp4", caption="check this out")
await client.send_document(chat_id, "/path/to/report.pdf")
await client.send_voice(chat_id, "/path/to/voice.ogg")   # playable voice message
await client.send_audio(chat_id, "/path/to/song.mp3")     # music-player style
await client.send_file(chat_id, "/path/to/anything")        # auto-detects type
```

Default output looks like:
```
Uploading movie.mp4: [############--------]  62% (12.4/20.0 MB)
```

Control it with the `progress=` kwarg on any send method:

```python
await client.send_file(chat_id, path, progress=False)          # no output at all
await client.send_file(chat_id, path, progress=my_callback)     # your own callback

def my_callback(sent: int, total: int):
    print(f"{sent}/{total} bytes")
```

`my_callback` may be a regular function or an `async def` — both work.

Downloading:
```python
saved_path = await client.download_media(message_dict, file_path="/save/here.jpg")
```

**Spoiler media** (blurred "tap to reveal" overlay, same as the official
apps' spoiler toggle): pass `spoiler=True` to `send_photo`, `send_video`, or
`send_file`. Only affects photos/videos sent as quick media; ignored for
documents or other file types.

```python
await client.send_photo(chat_id, "/path/to/spoiler.jpg", spoiler=True)
await client.send_video(chat_id, "/path/to/spoiler.mp4", spoiler=True)
```

---

## Stories

```python
# Does a user currently have an active story? Returns info + a link if so.
info = await client.has_story(user_id)
# {"has_story": True, "stories": [...], "latest_story_id": 123, "link": "https://..."}
if info["has_story"]:
    print("They posted:", info["link"])

# List all of a peer's currently active stories (empty list if none)
stories = await client.get_user_stories(user_id)
for story in stories:
    print(story["id"], story["media"])

# Mark a story as viewed/seen
await client.send_story_view(user_id, story_id)

# React to a story with an emoji (pass None to remove your reaction)
await client.send_story_reaction(user_id, story_id, "❤")
await client.send_story_reaction(user_id, story_id, None)

# Reply to a story with a text message -- by owner + id, or by link
await client.reply_to_story(user_id, story_id, "nice!")
await client.reply_to_story("https://splus.ir/username/s/123", text="nice!")

# Get a shareable link to a specific story, or omit story_id for
# whatever they currently have up
link = await client.get_story_link(user_id, story_id)
link = await client.get_story_link(user_id)

# Download a story's photo/video to disk (or bytes, in memory)
path = await client.download_story(user_id, story_id)
data = await client.download_story(user_id, story_id, bytes)
```

Each story dict has: `id`, `peer_id`, `date`, `expire_date`, `caption`,
`pinned`, `is_public`, `close_friends`, `noforwards`, `edited`, `out`,
`views_count`, `reactions_count`, `media` (raw media dict; feed to
`download_story` rather than parsing this yourself).

**Note on `get_story_link`:** some Soroush Plus accounts/setups reject this
specific request server-side with a `NOT_SUPPORTED` error even when
everything about the story itself is fine (public, has a username, etc).
This is a server-side limitation outside the library's control — when it
happens, `get_story_link` returns `None` instead of raising, same as if
there were simply no story to link to.

**Note on posting a new story:** SplusLib currently has **no `send_story`
method** — the underlying TL schema this library ships with doesn't include
a story-upload request at all, so posting a brand-new story isn't possible
through this library right now.

---

## Account management

```python
me = await client.get_me()
# {"id": ..., "first_name": ..., "last_name": ..., "username": ...,
#  "phone": ..., "bio": ..., "is_bot": ..., "is_premium": ..., "is_verified": ...}

await client.update_profile(first_name="New Name", last_name="", about="New bio")
await client.update_username("my_new_username")

await client.set_profile_photo("/path/to/avatar.jpg")   # progress bar by default too
await client.delete_profile_photos()                     # deletes all, or pass photo_ids=[...]

await client.block_user(user_id)
await client.unblock_user(user_id)
# stories-only block: they can still message you, just can't see it if
# you're blocking them from seeing your stories, or vice versa for unblock
await client.block_user(user_id, only_stories=True)
```

---

## Group / chat management

```python
# Title, description, photo
await client.set_chat_title(chat_id, "New Group Name")
await client.set_chat_description(chat_id, "New description")
await client.set_chat_photo(chat_id, "/path/to/photo.jpg")   # progress bar by default
await client.delete_chat_photo(chat_id)

# Public username for a group/channel you admin
available = await client.check_chat_username(chat_id, "newusername")
await client.set_chat_username(chat_id, "newusername")   # "" removes it, makes chat private

# Full info: description, pinned message, admin/member/online counts, etc
info = await client.get_chat_info(chat_id)

# Membership & moderation
members = await client.get_chat_members(chat_id, limit=100)
is_admin = await client.is_admin(chat_id, user_id)   # or no user_id = check self

await client.ban_member(chat_id, user_id)
await client.unban_member(chat_id, user_id)
await client.mute_member(chat_id, user_id, seconds=3600)
await client.set_admin(chat_id, user_id)
await client.remove_admin(chat_id, user_id)

# Creation & joining
new_channel = await client.create_channel(title, description="", megagroup=True)
new_group = await client.create_group(title, users=[user_id, ...])
await client.join_group_by_invite(invite_link)
await client.leave_chat(chat_id)

# Listing
chats = await client.get_chats(limit=100)
```

Every one of these raises `errors.NotAdminError` (or a more specific
subclass) if the bot account can't do it — see
[Error handling](#error-handling).

---

## Invite links & join requests

```python
# Create a fresh invite link with custom settings
link = await client.get_chat_invite_link(
    chat_id, title="My link", usage_limit=50, request_needed=True,
)

# List existing invite links (active by default, revoked=True for revoked ones)
links = await client.get_chat_invite_links(chat_id)
for l in links:
    print(l["link"], l["usage"], l["title"])

# Edit an existing link's settings
await client.edit_chat_invite_link(chat_id, link, title="New title")

# Revoke it (deactivate, but keep it listed)
await client.edit_chat_invite_link(chat_id, link, revoke=True)

# Permanently delete a revoked link
await client.delete_chat_invite_link(chat_id, link)
```

For links created with `request_needed=True`, people who tap them show up
as pending join requests instead of joining immediately:

```python
requests = await client.get_join_requests(chat_id)
for req in requests:
    print(req["user_id"], req["date"], req["about"])
    await client.approve_join_request(chat_id, req["user_id"])
    # or:
    await client.decline_join_request(chat_id, req["user_id"])

# Decline everyone pending at once (optionally scoped to one link)
await client.decline_all_join_requests(chat_id)
```

---

## Contacts

```python
contact = await client.add_contact(phone, first_name="John", last_name="Doe")
contacts = await client.get_contacts()
await client.delete_contact(user_id)
```

---

## Conference calls (join + play audio)

Joining a call and playing/switching/stopping audio in it are two separate
steps, handled by two different pieces:

1. `client.join_group_call(...)` — MTProto-level: resolves the call and gets
   back a LiveKit `url` + `token`.
2. `CallAudioSession` (in `spluslib.call_audio`) — actually connects to
   LiveKit with that `url`/`token` and streams real audio into the call.

```python
from spluslib.call_audio import CallAudioSession

call = await client.join_group_call(slug="atp-nwz-yux")
# call = {"id": ..., "slug": ..., "url": "wss://...", "token": "eyJ...", ...}

session = CallAudioSession()
await session.connect(call["url"], call["token"])

# Play one track and wait for it to finish naturally:
await session.play("/path/to/song.mp3")
await session.wait_until_done()

# Or loop a track until you switch/stop it yourself (e.g. from a
# chat-command handler elsewhere in your bot):
await session.play("/path/to/song.mp3", loop=True)
await session.play("/path/to/other_song.mp3", loop=True)   # switch, instant
await session.stop()                                        # silence, stay in call
await session.disconnect()                                  # leave the call
```

Other call-management methods on `SplusClient` itself:

```python
new_call = await client.create_group_call(title="My Call", chat_id=chat_id)
info = await client.resolve_group_call(slug)
await client.leave_group_call(slug=slug)
await client.end_group_call(slug=slug)
call_info = await client.get_group_call_info(slug)

await client.mute_participant(slug, user_id)
await client.remove_participant(slug, user_id)
await client.ban_participant(slug, user_id)
await client.unban_participant(slug, user_id)
banned = await client.get_banned_participants(slug)

active_calls = await client.get_active_group_calls()
```

**Requirements:** `pip install livekit --break-system-packages`, and
`ffmpeg` installed and on `PATH` (used to decode audio files to raw PCM;
`CallAudioSession` spawns it as a subprocess).

**⚠️ Deprecated placeholders:** `SplusClient.start_audio_stream()`,
`.play_audio_file()`, and `.play_audio_queue()` are leftover placeholders
from before `CallAudioSession` existed. They always return `False` and do
nothing. Use `CallAudioSession` instead, as shown above.

---

## Error handling

Every `spluslib` method raises a subclass of `spluslib.errors.SplusError`
on failure, instead of silently returning `None`/`False`. Every exception
also carries the original low-level exception on `.original`, if you need
the raw details.

```python
from spluslib import errors

try:
    await client.set_admin(chat_id, user_id)
except errors.NotAdminError:
    print("I'm not an admin here.")
except errors.UserNotInChatError:
    print("That user isn't in this chat.")
except errors.FloodWaitError as e:
    print(f"Rate-limited, wait {e.seconds} seconds.")
except errors.SplusError as e:
    print(f"Something else went wrong: {e}  (raw: {e.original})")
```

### Exception reference

| Exception | Meaning |
|---|---|
| `SplusError` | Base class for everything below |
| `NotAdminError` | Bot isn't an admin (or lacks the specific right) for this action |
| `NoPermissionError` | Action blocked by chat settings/restrictions, distinct from not-admin |
| `UserNotFoundError` | Couldn't find that user |
| `UserNotInChatError` | That user isn't a member of the chat |
| `UserAlreadyInChatError` | That user is already a member |
| `UserBlockedYouError` | That user has blocked you |
| `UserPrivacyError` | Blocked by the target's privacy settings |
| `UserDeactivatedError` | That account was deleted/deactivated |
| `ChatNotFoundError` | Couldn't find that chat |
| `InvalidChatError` | That id/link isn't a valid chat |
| `MessageTooLongError` | Message text too long |
| `MessageNotFoundError` | Couldn't find that message |
| `MessageNotModifiedError` | Edited content was identical to the existing message |
| `EmptyMessageError` | Message text/caption can't be empty here |
| `InvalidMediaError` | The file/photo/video was rejected as invalid/unsupported |
| `FileTooLargeError` | File exceeds the size limit |
| `InvalidUsernameError` | Username isn't in a valid format |
| `UsernameTakenError` | Username already taken |
| `UsernameNotFoundError` | No account/chat has that username |
| `FloodWaitError` | Rate-limited; `.seconds` tells you how long to wait |
| `TooManyRequestsError` | Sending requests too fast in general |
| `InvalidPhoneError` | Phone number invalid/not registered |
| `InvalidCodeError` | Login code is wrong |
| `ExpiredCodeError` | Login code expired |
| `InvalidPasswordError` | 2FA password is wrong |
| `PasswordNeededError` | Account has 2FA enabled, password required |
| `CallNotFoundError` | Couldn't resolve that conference call |
| `NotInCallError` | Action needs an active call connection (call `.connect()` first) |
| `AlreadyInCallError` | Already connected to a call |
| `UnknownError` | No specific mapping exists yet; check `.original` for the real error |

`errors.translate(exc)` is the function that performs this mapping
internally; you generally won't need to call it yourself.

---

## Full method reference

### Lifecycle
`start(phone=None, *, password=None, code_callback=None, force_sms=False, first_name='New User', last_name='', max_attempts=3)`,
`stop()`, `run_until_disconnected()`, async context manager support
(`async with SplusClient(...) as client:`).

### Events
`on(event_type, *args, **kwargs)`, `add_event_handler(callback, event_type)`,
`remove_event_handler(callback, event_type)`,
`on_message`, `on_edited`, `on_deleted`, `on_read`, `on_chat_action`,
`on_user_update`, `on_callback`, `on_inline`, `on_album`, `on_raw`.

### Account
`get_me()`, `update_profile(first_name=..., last_name=..., about=...)`,
`update_username(username)`, `set_profile_photo(photo, *, progress=True)`,
`delete_profile_photos(photo_ids=None)`,
`block_user(chat_id, *, only_stories=False)`,
`unblock_user(chat_id, *, only_stories=False)`.

### Group/chat settings
`set_chat_title(chat_id, title)`, `set_chat_description(chat_id, description)`,
`set_chat_photo(chat_id, photo, *, progress=True)`, `delete_chat_photo(chat_id)`,
`check_chat_username(chat_id, username)`, `set_chat_username(chat_id, username)`.

### Invite links & join requests
`get_chat_invite_link(chat_id, *, title=None, expire_date=None, usage_limit=None, request_needed=False)`
(creates a new link),
`get_chat_invite_links(chat_id, *, revoked=False, admin_id=None, limit=100)`
(lists existing links),
`edit_chat_invite_link(chat_id, link, *, revoke=False, title=None, expire_date=None, usage_limit=None, request_needed=None)`,
`delete_chat_invite_link(chat_id, link)`,
`get_join_requests(chat_id, *, link=None, query=None, limit=100)`,
`approve_join_request(chat_id, user_id)`, `decline_join_request(chat_id, user_id)`,
`decline_all_join_requests(chat_id, *, link=None)`.

### Chats
`get_chats(limit=100)`, `get_chat_info(chat_id)`,
`get_chat_members(chat_id, limit=None, filter_admins=False)`,
`is_admin(chat_id, user_id=None)`.

### Moderation
`ban_member(chat_id, user_id, ...)`, `unban_member(chat_id, user_id)`,
`mute_member(chat_id, user_id, seconds=...)`, `set_admin(chat_id, user_id)`,
`remove_admin(chat_id, user_id)`.

### Creation / joining
`create_channel(title, description='', megagroup=False)`,
`create_group(title, users=[...])`, `join_group_by_invite(invite_link)`,
`leave_chat(chat_id)`.

### Messages
`send_message(chat_id, text, ...)`, `get_messages(chat_id, limit=20, ...)`,
`get_message_by_id(chat_id, message_id)`, `delete_messages(chat_id, ids)`,
`edit_message(chat_id, message_id, text)`,
`forward_messages(from_chat_id, to_chat_id, ids)`,
`pin_message(chat_id, message_id)`, `unpin_message(chat_id, message_id)`,
`react_message(chat_id, message_id, reaction)`,
`get_reactions(chat_id, message_id)`, `search_messages(chat_id, query, ...)`.

### Files / media
`send_file(chat_id, file, ..., spoiler=False, progress=True)`,
`send_photo(chat_id, photo, ..., spoiler=False, progress=True)`,
`send_video`, `send_document`, `send_voice`, `send_audio`
(all accept `progress=`; `send_photo`/`send_video`/`send_file` accept
`spoiler=`), `download_media(message, file_path=None)`.

### Stories
`has_story(chat_id)`, `get_user_stories(chat_id)`,
`send_story_view(chat_id, story_id)`,
`send_story_reaction(chat_id, story_id, emoji=None, *, add_to_recent=False)`,
`reply_to_story(chat_id_or_link, story_id=None, text='', *, parse_mode='md', silent=False)`,
`get_story_link(chat_id, story_id=None)`,
`download_story(chat_id, story_id, file_path=None, *, progress=True)`.

### Contacts
`add_contact(phone, first_name, last_name='')`, `get_contacts()`,
`delete_contact(user_id)`.

### Conference calls
`create_group_call(...)`, `resolve_group_call(slug)`,
`join_group_call(slug=None, meet_link=None, muted=True, video_stopped=True, max_retries=3)`,
`leave_group_call(slug=None, meet_link=None)`, `end_group_call(...)`,
`get_group_call_info(slug)`, `mute_participant(...)`,
`remove_participant(...)`, `ban_participant(...)`, `unban_participant(...)`,
`get_banned_participants(slug)`, `get_active_group_calls()`.

### `spluslib.call_audio.CallAudioSession`
`connect(url, token)`, `play(file_path, *, loop=False)`, `stop()`,
`wait_until_done()`, `disconnect()`, properties `is_connected`, `is_playing`.

---

## Known limitations

- **No `send_story` method.** The underlying TL schema shipped with this
  library has no story-upload request at all — posting a brand-new story
  isn't possible through SplusLib right now, on any account.
- **`get_story_link` can return `None` even for valid, public stories.**
  Some Soroush Plus setups reject the underlying `ExportStoryLink` request
  server-side with `NOT_SUPPORTED`. The library treats this the same as
  "no link available" (returns `None`) rather than raising, since it's a
  server-side limitation the caller can't do anything about.
- `SplusClient.start_audio_stream()` / `.play_audio_file()` /
  `.play_audio_queue()` are deprecated no-op placeholders — use
  `CallAudioSession` instead.
- `CallAudioSession` currently supports one outbound audio track (bot →
  call). It does not currently handle receiving/mixing incoming audio from
  other participants.
- File uploads/downloads go through the standard MTProto upload path; very
  large files will be chunked automatically by the underlying engine but
  will still take time proportional to your connection speed — the
  progress bar reflects real transfer progress, not an estimate.

---

## For AI assistants reading this repo

If you are an LLM/coding assistant helping someone work with this codebase,
here is what you need to know to be immediately useful:

1. **Entry point**: `from spluslib import SplusClient, events, errors` and,
   for calls, `from spluslib.call_audio import CallAudioSession`. Nothing
   else needs to be imported for typical usage.
2. **Everything is async.** Every I/O method on `SplusClient` and
   `CallAudioSession` must be awaited.
3. **`SplusClient` wraps a vendored Telethon-style engine** located at
   `spluslib/_base/`. That folder is a private implementation detail (note
   the leading underscore) — don't import from it directly in user-facing
   code; use the `SplusClient` methods, or fall back to
   `client._client.<telethon_style_method>(...)` only if no `SplusClient`
   method covers the need (see `__getattr__` forwarding, described above).
4. **Error handling**: assume every `SplusClient`/`CallAudioSession` method
   can raise `spluslib.errors.SplusError` subclasses. When writing example
   code or fixing bugs, wrap risky calls in `try/except errors.SplusError`
   (or a specific subclass) rather than a bare `except Exception`, since the
   whole point of `errors.py` is that callers get to distinguish failure
   reasons.
5. **File arguments accept a local path (`str`), a URL, or raw `bytes`** —
   never require the caller to pre-read a file into bytes. This applies to
   `send_file`/`send_photo`/`send_video`/`send_document`/`send_voice`/
   `send_audio`/`set_profile_photo`/`set_chat_photo`.
6. **Progress bars**: any method with a `progress=` kwarg defaults to
   `progress=True` (built-in console bar). Set `progress=False` to silence
   it, or pass a callable `(bytes_sent, total_bytes) -> None` (sync or
   async) for custom handling.
7. **Two-step call-audio flow**: `join_group_call()` only gets connection
   info (`url`/`token`); it does **not** connect to the call's audio.
   `CallAudioSession.connect(url, token)` is the step that actually joins
   the LiveKit room and publishes an audio track. Always pair them:
   ```python
   call = await client.join_group_call(slug=...)
   session = CallAudioSession()
   await session.connect(call["url"], call["token"])
   ```
8. **`CallAudioSession.play()` does not block.** It starts playback in the
   background and returns immediately. If example code needs to wait for a
   track to finish, use `await session.wait_until_done()` explicitly (only
   meaningful when `loop=False`) or otherwise keep the process alive (e.g.
   `await client.run_until_disconnected()`), or playback (and the whole
   call connection) will be torn down when the script exits.
9. **Do not suggest `tgcalls`** as a dependency — `start_audio_stream` /
   `play_audio_file` / `play_audio_queue` reference it in old, now-dead
   docstrings, but the actual, working implementation uses `livekit`
   (`pip install livekit`) via `CallAudioSession`, not `tgcalls`.
10. **Session files**: `SplusClient(session_name)` creates a local SQLite
    session file (`<session_name>.session`) on first successful login.
    Treat this file as a credential — it grants full account access without
    needing the login code again.
11. **Story field names are inconsistent between event types.** On a
    `NewMessage`-family event, the message id is `event.id` (not
    `event.msg_id`). On a story's own dict from `get_user_stories()` /
    `has_story()`, the story id is `story["id"]`, and the owner is
    `story["peer_id"]` — these are two separate identifiers you pass
    together to `send_story_view`, `send_story_reaction`,
    `reply_to_story`, `get_story_link`, and `download_story`.
12. **There is no `send_story` (post-a-new-story) method** — the TL schema
    this library ships with doesn't define that request at all. Don't
    invent or guess at an implementation for it; tell the user it isn't
    currently supported.
13. **`get_story_link` returning `None` is not necessarily a bug** in
    caller code — some Soroush Plus setups reject the request server-side
    (`NOT_SUPPORTED`) even for perfectly valid public stories. Treat a
    `None` result the same as "no story to link to," don't assume the
    chat_id/story_id passed in was wrong.
14. **`chat_id` parameters accept a numeric `int`, a numeric-looking
    `str`, a `@username` string, or `"me"`** — they're normalized
    internally, so callers don't need to pre-convert types.

---

<br>

# مستندات فارسی

**نسخه‌ی ۲.۰.۲**

کتابخونه‌ی کامل و سطح‌بالای پایتون برای ساخت یوزربات روی **Soroush Plus**،
ساخته‌شده روی یک فورک اختصاصی Soroush Plus از موتور MTProto (همون چیزی که
پایه‌ی Telethon هست). ارسال/دریافت پیام، فایل و مدیا، استوری، مدیریت گروه،
مدیریت اکانت، و تماس‌های صوتی/کنفرانس واقعی (با LiveKit) — همه از طریق یک
API ساده و یکدست.

## فهرست مطالب (فارسی)

- [چه چیزهایی توی ۲.۰.۰ جدیده](#چه-چیزهایی-توی-۲۰۰-جدیده)
- [محتوای این ریپازیتوری](#محتوای-این-ریپازیتوری)
- [نصب](#نصب)
- [شروع سریع](#شروع-سریع)
- [مفاهیم پایه](#مفاهیم-پایه)
- [ایونت‌ها](#ایونتها)
- [API آبجکت رویداد و پیام](#api-آبجکت-رویداد-و-پیام)
- [مرجع کامل متدهای `SplusClient`](#مرجع-کامل-متدهای-splusclient)
- [پیام‌رسانی](#پیامرسانی)
- [فایل، عکس، ویدیو، ویس، صدا](#فایل-عکس-ویدیو-ویس-صدا)
- [استوری](#استوری)
- [مدیریت اکانت](#مدیریت-اکانت)
- [مدیریت گروه/چت](#مدیریت-گروهچت)
- [لینک دعوت و درخواست‌های عضویت](#لینک-دعوت-و-درخواستهای-عضویت)
- [مخاطبین](#مخاطبین)
- [تماس‌های کنفرانسی (ورود + پخش صدا)](#تماسهای-کنفرانسی-ورود--پخش-صدا)
- [مدیریت خطاها](#مدیریت-خطاها)
- [محدودیت‌های شناخته‌شده](#محدودیتهای-شناختهشده)

---

## وضعیت نسخه ۲.۰.x

- **استوری.** چک کردن این‌که یه کاربر استوری فعال داره یا نه، لیست‌گیری
  استوری‌های فعال یه peer، سین/ری‌اکشن/ریپلای روی استوری، دانلود عکس/ویدیوی
  استوری، و گرفتن لینک استوری — بخش [استوری](#استوری) رو ببین.
- **مدیای اسپویلر.** `send_photo`/`send_video`/`send_file` حالا `spoiler=True`
  قبول می‌کنن برای ارسال مدیای تار با overlay «برای دیدن ضربه بزن».
- **بلاک/آنبلاک.** `block_user()` / `unblock_user()`، شامل گزینه‌ی بلاک فقط
  از استوری.
- **مدیریت کامل لینک دعوت.** لیست‌گیری از لینک‌های موجود یه چت، ویرایش
  تنظیماتشون یا غیرفعال‌کردنشون، حذفشون — نه فقط ساخت لینک جدید. بخش
  [لینک دعوت و درخواست‌های عضویت](#لینک-دعوت-و-درخواستهای-عضویت) رو ببین.
- **درخواست‌های عضویت.** لیست درخواست‌های عضویت در انتظار یه چت، قبول یا رد
  کردن تک‌تکشون، یا رد کردن همه‌شون یه‌جا.
- **یوزرنیم چت.** چک کردن در دسترس بودن و تنظیم یوزرنیم عمومی برای
  گروه/کانالی که توش ادمینی.
- **اسم دستگاه قابل‌تشخیص.** `SplusClient(session_name)` الان به‌صورت
  پیش‌فرض توی تنظیمات ← دستگاه‌ها به‌شکل `"<session_name> (SplusLib)"`
  نمایش داده میشه، نه یه اسم عمومی بر پایه‌ی سیستم‌عامل — یعنی هر سشن بات
  با یه نگاه قابل‌تشخیصه. با `device_model=...` می‌تونی عوضش کنی.

---

## محتوای این ریپازیتوری

```
spluslib/
├── __init__.py       # نقطه‌ی ورود پکیج
├── client.py           # SplusClient -- API اصلی سطح‌بالا (حدود ۱۰۵ متد عمومی)
├── events.py             # اسامی ساده برای کلاس‌های ایونت
├── errors.py               # هرم exception های قابل‌فهم
├── call_audio.py             # CallAudioSession -- اتصال واقعی صوتی به تماس‌ها با LiveKit
└── _base/                      # موتور داخلی MTProto (فورک Telethon مخصوص Soroush Plus)
```

**همه‌چیز توی یک پوشه‌ست.** هیچ پکیج جدایی برای نصب لازم نیست — پوشه‌ی
`_base` یک زیرپکیج داخلی و خصوصیه. همیشه فقط از `spluslib` ایمپورت کن.

---

## نصب

```bash
# ۱. پوشه‌ی spluslib/ رو توی پروژه‌ت کپی کن (یا این ریپو رو clone کن)

# ۲. دو وابستگی بیرونی رو نصب کن:
pip install livekit --break-system-packages
# ffmpeg هم باید نصب و توی PATH باشه (فقط برای decode کردن فایل صوتی موقع
# پخش توی تماس لازمه -- اگه از CallAudioSession استفاده نمی‌کنی لازم نیست)
```

همین. موتور MTProto (`_base`) به‌جز کتابخونه‌ی استاندارد پایتون وابستگی
بیرونی نداره (به‌جز `pyaes`, `rsa`, `pysocks` که کتابخونه‌های خانواده‌ی
Telethon معمولاً لازم دارن؛ اگه توی محیطت نیستن نصبشون کن:
`pip install pyaes rsa pysocks --break-system-packages`).

---

## شروع سریع

```python
import asyncio
from spluslib import SplusClient, events, errors

client = SplusClient("my_session")

@client.on_message(pattern=r"^/start$")
async def start_cmd(event):
    await event.reply("سلام! زنده‌ام.")

async def main():
    await client.start("+989123456789")   # شماره با کد کشور
    await client.run_until_disconnected()

asyncio.run(main())
```

اجراش کن، کد تأیید رو وارد کن (به‌صورت تعاملی، یا با `code_callback=` برای
حالت غیرتعاملی)، و بات آماده‌ست.

به‌صورت پیش‌فرض این سشن توی تنظیمات ← دستگاه‌ها به‌شکل
`"my_session (SplusLib)"` نمایش داده میشه — اگه اسم دیگه‌ای می‌خوای،
`device_model="..."` رو به `SplusClient(...)` بده.

---

## مفاهیم پایه

- **یک کلاینت، یک اکانت.** `SplusClient(session_name)` یه فایل session محلی
  می‌سازه (یا از قبلی استفاده می‌کنه). هر instance از `SplusClient` معادل
  یک اکانت لاگین‌شده‌ی Soroush Plus هست.
- **همه‌چیز async هست.** هر متدی که با شبکه کار داره یک coroutine هست — باید
  با `await` داخل یک `async def` صداش بزنی، و نقطه‌ی ورود برنامه رو با
  `asyncio.run(...)` اجرا کنی.
- **ورودی/خروجی dict.** متدهای سطح‌بالا دیکشنری پایتون معمولی برمی‌گردونن
  (مثلاً `{"id": ..., "text": ..., "chat_id": ...}`)، نه شیء خام TL — پس
  نیازی نیست ساختار MTProto رو بشناسی.
- **موقع خطا، exception پرتاب می‌کنه نه None/False.** هر متد در صورت بروز
  مشکل (نداشتن دسترسی، پیدا نشدن چت، محدودیت نرخ، و غیره) یکی از
  زیرکلاس‌های `spluslib.errors.SplusError` رو raise می‌کنه (بخش
  [مدیریت خطاها](#مدیریت-خطاها) رو ببین). هیچ متدی بی‌سروصدا `None`/`False`
  برنمی‌گردونه و دلیل رو مخفی نمی‌کنه.
- **راه فرار.** هر چیزی که `SplusClient` پوششش نداده باز هم در دسترسه:
  `client._client` همون instance موتور زیرین (`_base.SoroushClient`، سبک
  Telethon) هست، و `SplusClient.__getattr__` هر attribute ناشناخته رو
  خودکار بهش forward می‌کنه. یعنی `await client.یک_متد_native(...)` حتی اگه
  مستقیم روی `SplusClient` تعریف نشده باشه هم کار می‌کنه.

---

## ایونت‌ها

به‌جای سبک پرحرفِ Telethon:

```python
@client.on(events.NewMessage)
async def handler(event):
    ...
```

SplusLib یه متد کوتاه به‌ازای هر نوع ایونت میده:

| متد | زمان فراخوانی |
|---|---|
| `on_message(**filters)` | پیام جدید (ورودی/خروجی) |
| `on_edited(**filters)` | پیام ویرایش‌شده |
| `on_deleted(**filters)` | پیام حذف‌شده (`event.deleted_ids`) |
| `on_read(**filters)` | رسید خوانده‌شدن |
| `on_chat_action(**filters)` | ورود/خروج عضو، تغییر اسم/عکس، پین، ساخت گروه (`event.user_joined` و غیره) |
| `on_user_update(**filters)` | تغییر وضعیت آنلاین/آفلاین، تایپ کردن، عکس پروفایل |
| `on_callback(**filters)` | فشردن دکمه‌ی اینلاین (`await event.answer(...)`) |
| `on_inline(**filters)` | کوئری اینلاین (`@bot query`) |
| `on_album(**filters)` | مدیای گروهی (آلبوم) |
| `on_raw(**filters)` | آپدیت‌های خام و پردازش‌نشده (فقط برای موارد پیشرفته) |

همه‌ی filterهای معمول Telethon کار می‌کنن چون مستقیم پاس داده میشن:
`pattern=`, `chats=`, `incoming=`, `outgoing=`, `from_users=`,
`blacklist_chats=`, `func=` و غیره.

سبک قدیمی‌تر `@client.on(events.X, ...)` هم هنوز کار می‌کنه، برای مواردی که
شورت‌کات‌ها پوشش نمیدن.

می‌تونی handlerها رو به‌صورت برنامه‌ای هم ثبت/حذف کنی، بدون decorator:
`client.add_event_handler(callback, event_type)` و
`client.remove_event_handler(callback, event_type)`.

---


## API آبجکت رویداد و پیام

در رویدادهای پیام، `event` مانند یک `Message` رفتار می‌کند؛ یعنی خیلی از
ویژگی‌ها و متدهای پیام را می‌توانی مستقیم روی خود رویداد صدا بزنی:

```python
@client.on_message()
async def handler(msg):
    await msg.reply("سلام!")
    await msg.respond("پیام جداگانه")
    await msg.edit("متن ویرایش‌شده")
    await msg.delete()
    await msg.forward_to("@another_chat")
    path = await msg.download_media("/tmp")
    await msg.mark_read()
    await msg.pin()
    await msg.unpin()
```

### ویژگی‌های مهم پیام

`text`, `raw_text`, `is_reply`, `forward`, `reply_to_msg_id`,
`reply_to_chat`, `reply_to_sender`, `buttons`, `button_count`, `file`,
`photo`, `document`, `web_preview`, `audio`, `voice`, `video`,
`video_note`, `gif`, `sticker`, `contact`, `game`, `geo`, `invoice`,
`poll`, `venue`, `dice`, `action_entities`, `via_bot`, `via_input_bot`,
و `to_id`.

### متدهای مهم پیام

```text
get_buttons()
get_reply_message()
respond(...)
reply(...)
forward_to(...)
edit(...)
delete(...)
download_media(...)
click(...)
mark_read()
pin(...)
unpin()
get_sender()
get_chat()
```

### دکمه‌ها و Poll

```python
await msg.click(0, 0)
await msg.click(text="تأیید")
await msg.click(data=b"payload")

buttons = await msg.get_buttons()
```

`click()` علاوه بر دکمه‌ها می‌تواند برای رأی‌دادن به Poll هم استفاده شود.

### اطلاعات پیام اصلی در Reply

```python
if msg.is_reply:
    replied = await msg.get_reply_message()
    if replied:
        print(replied.raw_text)
```

### فرستنده و چت

```python
sender = await msg.get_sender()
chat = await msg.get_chat()
```

### API Callback

```python
await event.answer("انجام شد!")
await event.respond("پاسخ")
await event.reply("ریپلای")
await event.edit("ویرایش")
await event.delete()

message = await event.get_message()
```

### فیلترهای آماده

```python
@client.on_message(events.Command("start"))
async def start(msg):
    await msg.reply("سلام!")

@client.on_message(events.Text(contains="hello"))
async def hello(msg):
    await msg.reply("سلام!")

@client.on_message(events.Private())
async def private(msg):
    ...

@client.on_message(events.Group())
async def group(msg):
    ...
```

فیلترهای آماده شامل `Command`, `Text`, `Private`, `Group`, `Channel`,
`Incoming`, `Outgoing`, `And` و `Or` هستند.

---

## مرجع کامل متدهای `SplusClient`

### چرخه و رویدادها

`start()`, `stop()`, `run_until_disconnected()`, `on()`,
`add_event_handler()`, `remove_event_handler()`, `on_message()`,
`on_edited()`, `on_update()`, `on_deleted()`, `on_read()`, `on_reaction()`,
`on_chat_action()`, `on_user_update()`, `on_callback()`, `on_inline()`,
`on_album()`, `on_raw()`.

### اکانت و مخاطبین

`get_me()`, `update_profile()`, `update_username()`, `set_profile_photo()`,
`delete_profile_photos()`, `block_user()`, `unblock_user()`, `add_contact()`,
`get_contacts()`, `delete_contact()`, `get_user_by_phone()`, `report_user()`.

### چت و گروه

`set_chat_title()`, `set_chat_description()`, `set_chat_photo()`,
`delete_chat_photo()`, `get_chats()`, `get_chat_info()`, `get_chat_members()`,
`is_admin()`, `get_banned_users()`, `ban_member()`, `unban_member()`,
`mute_member()`, `set_admin()`, `remove_admin()`, `create_channel()`,
`create_group()`, `leave_chat()`, `join_group_by_invite()`,
`check_chat_username()`, `set_chat_username()`.

### لینک دعوت و درخواست عضویت

`get_chat_invite_link()`, `get_chat_invite_links()`,
`edit_chat_invite_link()`, `delete_chat_invite_link()`,
`get_join_requests()`, `approve_join_request()`, `decline_join_request()`,
`decline_all_join_requests()`.

### پیام‌ها

`send_message()`, `mention_user()`, `get_messages()`, `get_message_by_id()`,
`delete_messages()`, `edit_message()`, `forward_messages()`, `pin_message()`,
`unpin_message()`, `react_message()`, `get_reactions()`,
`search_messages()`, `report_message()`.

### فایل و مدیا

`send_file()`, `send_photo()`, `send_video()`, `send_document()`,
`send_voice()`, `send_audio()`, `download_media()`.

### Poll

`send_poll()`, `vote_poll()`, `close_poll()`, `get_poll_results()`.

### استوری

`get_story_link()`, `download_story()`, `get_user_stories()`, `has_story()`,
`send_story_view()`, `send_story_reaction()`, `reply_to_story()`.

در حال حاضر متد `send_story()` برای ساخت استوری جدید وجود ندارد.

### تماس‌های کنفرانسی

`create_group_call()`, `resolve_group_call()`, `join_group_call()`,
`leave_group_call()`, `end_group_call()`, `get_group_call_info()`,
`mute_participant()`, `remove_participant()`, `ban_participant()`,
`unban_participant()`, `get_banned_participants()`,
`get_active_group_calls()`.

### متدهای صوتی قدیمی

`start_audio_stream()`, `play_audio_file()`, `play_audio_queue()` در نسخه‌ی
فعلی placeholder منسوخ‌شده هستند و عملیات واقعی انجام نمی‌دهند؛ برای پخش
صدا در تماس از `CallAudioSession` استفاده کن.

---

## یادداشت نسخه

این README بر اساس API موجود در سورس آپلودشده و نسخه‌ی منتشرشده‌ی `2.0.2`
تنظیم شده است. صفحه‌ی PyPI، نسخه‌ی `2.0.2` را به‌عنوان انتشار فعلی در
۱۶ اوت ۲۰۲۶ نشان می‌دهد. در سورس آرشیوی که بررسی شد، مقدار داخلی
`__version__` هنوز `2.0.0` است؛ بنابراین شماره‌ی نسخه‌ی README بر اساس
نسخه‌ی منتشرشده در PyPI تنظیم شده است.


## پیام‌رسانی

```python
await client.send_message(chat_id, "سلام!")

msgs = await client.get_messages(chat_id, limit=10)
msg = await client.get_message_by_id(chat_id, message_id)

await client.edit_message(chat_id, message_id, "متن جدید")
await client.delete_messages(chat_id, [message_id, ...])
await client.forward_messages(from_chat_id, to_chat_id, [message_id, ...])

await client.pin_message(chat_id, message_id)
await client.unpin_message(chat_id, message_id)

await client.react_message(chat_id, message_id, "👍")
reactions = await client.get_reactions(chat_id, message_id)

results = await client.search_messages(chat_id, query="سلام", limit=20)
```

---

## فایل، عکس، ویدیو، ویس، صدا

**مسیر فایل (یا URL، یا bytes خام) رو مستقیم پاس بده — نیازی به خوندن دستی
بایت‌ها نیست.** به‌صورت پیش‌فرض یه progress bar توی کنسول نشون داده میشه.

```python
await client.send_photo(chat_id, "/path/to/photo.jpg")
await client.send_video(chat_id, "/path/to/movie.mp4", caption="ببین این چیه")
await client.send_document(chat_id, "/path/to/report.pdf")
await client.send_voice(chat_id, "/path/to/voice.ogg")   # پیام صوتی قابل‌پخش
await client.send_audio(chat_id, "/path/to/song.mp3")     # سبک پلیر موزیک
await client.send_file(chat_id, "/path/to/anything")        # تشخیص خودکار نوع فایل
```

خروجی پیش‌فرض این شکلیه:
```
Uploading movie.mp4: [############--------]  62% (12.4/20.0 MB)
```

با پارامتر `progress=` روی هر متد ارسال کنترلش کن:

```python
await client.send_file(chat_id, path, progress=False)          # بدون هیچ خروجی
await client.send_file(chat_id, path, progress=my_callback)     # callback خودت

def my_callback(sent: int, total: int):
    print(f"{sent}/{total} بایت")
```

`my_callback` می‌تونه یه تابع معمولی یا `async def` باشه — هر دو کار می‌کنن.

دانلود:
```python
saved_path = await client.download_media(message_dict, file_path="/save/here.jpg")
```

**مدیای اسپویلر** (تار شده پشت یه overlay «برای دیدن ضربه بزن»، دقیقاً مثل
سوییچ اسپویلر توی اپ‌های رسمی): `spoiler=True` رو به `send_photo`,
`send_video`, یا `send_file` بده. فقط روی عکس/ویدیویی که به‌عنوان مدیای
سریع ارسال میشه اثر داره؛ روی داکیومنت یا بقیه‌ی انواع فایل بی‌اثره.

```python
await client.send_photo(chat_id, "/path/to/spoiler.jpg", spoiler=True)
await client.send_video(chat_id, "/path/to/spoiler.mp4", spoiler=True)
```

---

## استوری

```python
# آیا الان یه کاربر استوری فعال داره؟ اطلاعات + لینک رو (اگه داشت) برمی‌گردونه
info = await client.has_story(user_id)
# {"has_story": True, "stories": [...], "latest_story_id": 123, "link": "https://..."}
if info["has_story"]:
    print("این استوری رو گذاشته:", info["link"])

# لیست همه‌ی استوری‌های فعال یه کاربر/چت (اگه نداشت، لیست خالی)
stories = await client.get_user_stories(user_id)
for story in stories:
    print(story["id"], story["media"])

# سین کردن (علامت‌زدن به‌عنوان دیده‌شده) یه استوری
await client.send_story_view(user_id, story_id)

# ری‌اکشن به یه استوری (برای حذف ری‌اکشن، None بده)
await client.send_story_reaction(user_id, story_id, "❤")
await client.send_story_reaction(user_id, story_id, None)

# ریپلای متنی روی یه استوری -- با آیدی مالک+استوری، یا با لینک
await client.reply_to_story(user_id, story_id, "قشنگه!")
await client.reply_to_story("https://splus.ir/username/s/123", text="قشنگه!")

# گرفتن لینک یه استوری خاص، یا بدون story_id برای آخرین استوری فعالش
link = await client.get_story_link(user_id, story_id)
link = await client.get_story_link(user_id)

# دانلود عکس/ویدیوی یه استوری روی دیسک (یا bytes، توی حافظه)
path = await client.download_story(user_id, story_id)
data = await client.download_story(user_id, story_id, bytes)
```

هر دیکشنری استوری این فیلدها رو داره: `id`, `peer_id`, `date`,
`expire_date`, `caption`, `pinned`, `is_public`, `close_friends`,
`noforwards`, `edited`, `out`, `views_count`, `reactions_count`, `media`
(دیکشنری خام مدیا؛ به‌جای پارس‌کردن دستیش، به `download_story` بدش).

**نکته درباره‌ی `get_story_link`:** بعضی از اکانت‌ها/تنظیمات سروش پلاس این
درخواست خاص رو سمت سرور با خطای `NOT_SUPPORTED` رد می‌کنن، حتی وقتی همه‌چیز
درباره‌ی خود استوری درسته (عمومیه، یوزرنیم داره و غیره). این یه محدودیت
سمت سروره که خارج از کنترل کتابخونه‌ست — وقتی این اتفاق بیفته،
`get_story_link` به‌جای raise کردن، `None` برمی‌گردونه، دقیقاً مثل حالتی که
اصلاً استوری‌ای برای لینک‌دادن وجود نداشته باشه.

**نکته درباره‌ی گذاشتن استوری جدید:** SplusLib فعلاً **هیچ متد
`send_story` نداره** — چون schema خام TL که این کتابخونه باهاش میاد اصلاً
درخواست آپلود استوری رو نداره، پس گذاشتن یه استوری کاملاً جدید فعلاً از
طریق این کتابخونه ممکن نیست.

---

## مدیریت اکانت

```python
me = await client.get_me()
# {"id": ..., "first_name": ..., "last_name": ..., "username": ...,
#  "phone": ..., "bio": ..., "is_bot": ..., "is_premium": ..., "is_verified": ...}

await client.update_profile(first_name="اسم جدید", last_name="", about="بیو جدید")
await client.update_username("my_new_username")

await client.set_profile_photo("/path/to/avatar.jpg")   # این هم progress bar داره
await client.delete_profile_photos()                     # همه رو حذف می‌کنه، یا photo_ids=[...] بده

await client.block_user(user_id)
await client.unblock_user(user_id)
# بلاک فقط از استوری: هنوز می‌تونه بهت پیام بده، فقط استوریت رو نمی‌بینه
await client.block_user(user_id, only_stories=True)
```

---

## مدیریت گروه/چت

```python
# اسم، توضیحات، عکس
await client.set_chat_title(chat_id, "اسم جدید گروه")
await client.set_chat_description(chat_id, "توضیحات جدید")
await client.set_chat_photo(chat_id, "/path/to/photo.jpg")   # progress bar پیش‌فرض
await client.delete_chat_photo(chat_id)

# یوزرنیم عمومی برای گروه/کانالی که توش ادمینی
available = await client.check_chat_username(chat_id, "newusername")
await client.set_chat_username(chat_id, "newusername")   # "" یعنی حذفش کن، چت خصوصی بشه

# اطلاعات کامل: توضیحات، پیام پین‌شده، تعداد ادمین/عضو/آنلاین و غیره
info = await client.get_chat_info(chat_id)

# عضویت و مدیریت
members = await client.get_chat_members(chat_id, limit=100)
is_admin = await client.is_admin(chat_id, user_id)   # بدون user_id = چک خود بات

await client.ban_member(chat_id, user_id)
await client.unban_member(chat_id, user_id)
await client.mute_member(chat_id, user_id, seconds=3600)
await client.set_admin(chat_id, user_id)
await client.remove_admin(chat_id, user_id)

# ساخت و پیوستن
new_channel = await client.create_channel(title, description="", megagroup=True)
new_group = await client.create_group(title, users=[user_id, ...])
await client.join_group_by_invite(invite_link)
await client.leave_chat(chat_id)

# لیست
chats = await client.get_chats(limit=100)
```

هر کدوم از این‌ها اگه بات دسترسی لازم رو نداشته باشه `errors.NotAdminError`
(یا زیرکلاس دقیق‌تری) raise می‌کنه — بخش [مدیریت خطاها](#مدیریت-خطاها) رو
ببین.

---

## لینک دعوت و درخواست‌های عضویت

```python
# ساخت یه لینک دعوت جدید با تنظیمات دلخواه
link = await client.get_chat_invite_link(
    chat_id, title="لینک من", usage_limit=50, request_needed=True,
)

# لیست لینک‌های دعوت موجود (پیش‌فرض فعال‌ها، برای غیرفعال‌شده‌ها revoked=True)
links = await client.get_chat_invite_links(chat_id)
for l in links:
    print(l["link"], l["usage"], l["title"])

# ویرایش تنظیمات یه لینک موجود
await client.edit_chat_invite_link(chat_id, link, title="عنوان جدید")

# غیرفعال کردنش (revoke، ولی توی لیست می‌مونه)
await client.edit_chat_invite_link(chat_id, link, revoke=True)

# حذف کامل یه لینک غیرفعال‌شده
await client.delete_chat_invite_link(chat_id, link)
```

برای لینک‌هایی که با `request_needed=True` ساخته شدن، کسایی که روشون بزنن
به‌جای پیوستن مستقیم، به‌عنوان درخواست عضویت در انتظار تأیید نمایش داده
میشن:

```python
requests = await client.get_join_requests(chat_id)
for req in requests:
    print(req["user_id"], req["date"], req["about"])
    await client.approve_join_request(chat_id, req["user_id"])
    # یا:
    await client.decline_join_request(chat_id, req["user_id"])

# رد کردن همه‌ی درخواست‌های در انتظار یه‌جا (یا فقط برای یه لینک خاص)
await client.decline_all_join_requests(chat_id)
```

---

## مخاطبین

```python
contact = await client.add_contact(phone, first_name="John", last_name="Doe")
contacts = await client.get_contacts()
await client.delete_contact(user_id)
```

---

## تماس‌های کنفرانسی (ورود + پخش صدا)

ورود به تماس و پخش/تعویض/توقف صدا توش، دو مرحله‌ی جدا هستن که با دو بخش
متفاوت انجام میشن:

۱. `client.join_group_call(...)` — سطح MTProto: تماس رو resolve می‌کنه و
   `url` + `token` مربوط به LiveKit رو برمی‌گردونه.
۲. `CallAudioSession` (توی `spluslib.call_audio`) — واقعاً با اون
   `url`/`token` به LiveKit وصل میشه و صدای واقعی رو توی تماس پخش می‌کنه.

```python
from spluslib.call_audio import CallAudioSession

call = await client.join_group_call(slug="atp-nwz-yux")
# call = {"id": ..., "slug": ..., "url": "wss://...", "token": "eyJ...", ...}

session = CallAudioSession()
await session.connect(call["url"], call["token"])

# پخش یه آهنگ و صبر تا تمام‌شدن طبیعیش:
await session.play("/path/to/song.mp3")
await session.wait_until_done()

# یا لوپ‌کردن یه آهنگ تا خودت عوض/متوقفش کنی (مثلاً از یه دستور چت):
await session.play("/path/to/song.mp3", loop=True)
await session.play("/path/to/other_song.mp3", loop=True)   # عوض کردن، فوری
await session.stop()                                        # سکوت، توی تماس بمون
await session.disconnect()                                  # خروج از تماس
```

بقیه‌ی متدهای مدیریت تماس روی خود `SplusClient`:

```python
new_call = await client.create_group_call(title="تماس من", chat_id=chat_id)
info = await client.resolve_group_call(slug)
await client.leave_group_call(slug=slug)
await client.end_group_call(slug=slug)
call_info = await client.get_group_call_info(slug)

await client.mute_participant(slug, user_id)
await client.remove_participant(slug, user_id)
await client.ban_participant(slug, user_id)
await client.unban_participant(slug, user_id)
banned = await client.get_banned_participants(slug)

active_calls = await client.get_active_group_calls()
```

**پیش‌نیازها:** `pip install livekit --break-system-packages`، و `ffmpeg`
نصب و توی `PATH` (برای decode کردن فایل‌های صوتی به PCM خام؛
`CallAudioSession` اون رو به‌عنوان subprocess اجرا می‌کنه).

**⚠️ متدهای منسوخ:** `SplusClient.start_audio_stream()`،
`.play_audio_file()`، و `.play_audio_queue()` باقی‌مونده‌ی کدهای قدیمی قبل
از ساخته‌شدن `CallAudioSession` هستن. همیشه `False` برمی‌گردونن و هیچ کاری
نمی‌کنن. به‌جاشون از `CallAudioSession` طبق بالا استفاده کن.

---

## مدیریت خطاها

هر متد `spluslib` در صورت شکست، یکی از زیرکلاس‌های
`spluslib.errors.SplusError` رو raise می‌کنه، به‌جای این‌که بی‌سروصدا
`None`/`False` برگردونه. هر exception هم exception خام اصلی رو روی
`.original` نگه می‌داره، اگه به جزئیات خام نیاز داشتی.

```python
from spluslib import errors

try:
    await client.set_admin(chat_id, user_id)
except errors.NotAdminError:
    print("من اینجا ادمین نیستم.")
except errors.UserNotInChatError:
    print("این کاربر عضو این چت نیست.")
except errors.FloodWaitError as e:
    print(f"محدودیت نرخ، {e.seconds} ثانیه صبر کن.")
except errors.SplusError as e:
    print(f"یه مشکل دیگه پیش اومد: {e}  (خام: {e.original})")
```

### فهرست Exception ها

| Exception | معنی |
|---|---|
| `SplusError` | کلاس پایه‌ی همه‌ی موارد زیر |
| `NotAdminError` | بات ادمین نیست (یا دسترسی خاص لازم رو نداره) |
| `NoPermissionError` | عملیات به‌خاطر تنظیمات/محدودیت چت مسدود شده، جدا از عدم ادمین بودن |
| `UserNotFoundError` | کاربر پیدا نشد |
| `UserNotInChatError` | کاربر عضو این چت نیست |
| `UserAlreadyInChatError` | کاربر از قبل عضو هست |
| `UserBlockedYouError` | این کاربر تو رو بلاک کرده |
| `UserPrivacyError` | به‌خاطر تنظیمات حریم‌خصوصی مقصد مسدود شده |
| `UserDeactivatedError` | این اکانت حذف/غیرفعال شده |
| `ChatNotFoundError` | چت پیدا نشد |
| `InvalidChatError` | این آیدی/لینک یه چت معتبر نیست |
| `MessageTooLongError` | متن پیام خیلی طولانیه |
| `MessageNotFoundError` | پیام پیدا نشد |
| `MessageNotModifiedError` | محتوای ویرایش‌شده با پیام فعلی یکسانه |
| `EmptyMessageError` | متن/کپشن پیام نمی‌تونه خالی باشه |
| `InvalidMediaError` | فایل/عکس/ویدیو نامعتبر یا پشتیبانی‌نشده بود |
| `FileTooLargeError` | فایل از حد مجاز بزرگ‌تره |
| `InvalidUsernameError` | یوزرنیم فرمت معتبر نداره |
| `UsernameTakenError` | یوزرنیم قبلاً گرفته شده |
| `UsernameNotFoundError` | هیچ اکانت/چتی این یوزرنیم رو نداره |
| `FloodWaitError` | محدودیت نرخ؛ `.seconds` مدت انتظار رو میگه |
| `TooManyRequestsError` | ارسال درخواست خیلی سریع به‌طور کلی |
| `InvalidPhoneError` | شماره تلفن نامعتبر/ثبت‌نشده |
| `InvalidCodeError` | کد ورود اشتباهه |
| `ExpiredCodeError` | کد ورود منقضی شده |
| `InvalidPasswordError` | رمز 2FA اشتباهه |
| `PasswordNeededError` | اکانت 2FA فعال داره، رمز لازمه |
| `CallNotFoundError` | تماس کنفرانسی پیدا/resolve نشد |
| `NotInCallError` | این عملیات نیاز به اتصال فعال به تماس داره (اول `.connect()` بزن) |
| `AlreadyInCallError` | از قبل به یه تماس وصلی |
| `UnknownError` | هنوز نگاشت خاصی براش نداریم؛ `.original` رو برای خطای واقعی چک کن |

---

## محدودیت‌های شناخته‌شده

- **متد `send_story` وجود نداره.** schema خام TL که این کتابخونه باهاش میاد
  اصلاً درخواست آپلود استوری رو نداره — گذاشتن یه استوری کاملاً جدید فعلاً
  از هیچ اکانتی از طریق SplusLib ممکن نیست.
- **`get_story_link` حتی برای استوری‌های معتبر و عمومی هم ممکنه `None`
  برگردونه.** بعضی از تنظیمات سروش پلاس درخواست خام `ExportStoryLink` رو
  سمت سرور با `NOT_SUPPORTED` رد می‌کنن. کتابخونه این حالت رو دقیقاً مثل
  «لینکی در کار نیست» در نظر می‌گیره (یعنی `None` برمی‌گردونه) به‌جای
  raise کردن، چون این یه محدودیت سمت سروره که کاری از دست فراخوان‌کننده
  براش برنمیاد.
- `SplusClient.start_audio_stream()` / `.play_audio_file()` /
  `.play_audio_queue()` جایگزین‌های منسوخ و بی‌اثر هستن — به‌جاشون از
  `CallAudioSession` استفاده کن.
- `CallAudioSession` فعلاً فقط یک track صوتی خروجی (بات → تماس) پشتیبانی
  می‌کنه. دریافت/میکس صدای ورودی از بقیه‌ی اعضا فعلاً پشتیبانی نمیشه.
- آپلود/دانلود فایل از مسیر استاندارد MTProto عبور می‌کنه؛ فایل‌های خیلی
  بزرگ به‌طور خودکار توسط موتور زیرین chunk میشن ولی زمانش متناسب با سرعت
  اینترنتته — progress bar پیشرفت واقعی رو نشون میده، نه یه تخمین.

---

* --Erfan Mirdehghan--*
