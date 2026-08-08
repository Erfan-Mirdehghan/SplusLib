pypi https://pypi.org/project/spluslib/

# SplusLib

A complete, high-level Python userbot library for **Soroush Plus**, built on a
Soroush-Plus-specific fork of the MTProto engine that powers Telethon.
Messaging, files/media, group management, account management, and real
LiveKit-based voice/conference calls — all through a simple, consistent API.

> 📄 مستندات فارسی: پایین همین فایل، بعد از بخش انگلیسی. / Persian
> documentation is further down in this same file, after the English section.

---

## Table of Contents (English)

- [What's in this repo](#whats-in-this-repo)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Core concepts](#core-concepts)
- [Events](#events)
- [Messaging](#messaging)
- [Files, photos, video, voice, audio](#files-photos-video-voice-audio)
- [Account management](#account-management)
- [Group / chat management](#group--chat-management)
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

## What's in this repo

```
spluslib/
├── __init__.py       # package entry point, exports SplusClient, events, errors, CallAudioSession
├── client.py          # SplusClient -- the main high-level API (~2000 lines, ~80 public methods)
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
```

---

## Group / chat management

```python
# Title, description, photo
await client.set_chat_title(chat_id, "New Group Name")
await client.set_chat_description(chat_id, "New description")
await client.set_chat_photo(chat_id, "/path/to/photo.jpg")   # progress bar by default
await client.delete_chat_photo(chat_id)

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
`delete_profile_photos(photo_ids=None)`.

### Group/chat settings
`set_chat_title(chat_id, title)`, `set_chat_description(chat_id, description)`,
`set_chat_photo(chat_id, photo, *, progress=True)`, `delete_chat_photo(chat_id)`.

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
`send_file(chat_id, file, ..., progress=True)`,
`send_photo`, `send_video`, `send_document`, `send_voice`, `send_audio`
(all accept `progress=`), `download_media(message, file_path=None)`.

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

---

<br>

# مستندات فارسی

کتابخونه‌ی کامل و سطح‌بالای پایتون برای ساخت یوزربات روی **Soroush Plus**،
ساخته‌شده روی یک فورک اختصاصی Soroush Plus از موتور MTProto (همون چیزی که
پایه‌ی Telethon هست). ارسال/دریافت پیام، فایل و مدیا، مدیریت گروه، مدیریت
اکانت، و تماس‌های صوتی/کنفرانس واقعی (با LiveKit) — همه از طریق یک API ساده
و یکدست.

## فهرست مطالب (فارسی)

- [محتوای این ریپازیتوری](#محتوای-این-ریپازیتوری)
- [نصب](#نصب)
- [شروع سریع](#شروع-سریع)
- [مفاهیم پایه](#مفاهیم-پایه)
- [ایونت‌ها](#ایونتها)
- [پیام‌رسانی](#پیامرسانی)
- [فایل، عکس، ویدیو، ویس، صدا](#فایل-عکس-ویدیو-ویس-صدا)
- [مدیریت اکانت](#مدیریت-اکانت)
- [مدیریت گروه/چت](#مدیریت-گروهچت)
- [مخاطبین](#مخاطبین)
- [تماس‌های کنفرانسی (ورود + پخش صدا)](#تماسهای-کنفرانسی-ورود--پخش-صدا)
- [مدیریت خطاها](#مدیریت-خطاها)
- [محدودیت‌های شناخته‌شده](#محدودیتهای-شناختهشده)

---

## محتوای این ریپازیتوری

```
spluslib/
├── __init__.py       # نقطه‌ی ورود پکیج
├── client.py           # SplusClient -- API اصلی سطح‌بالا (حدود ۸۰ متد عمومی)
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
```

---

## مدیریت گروه/چت

```python
# اسم، توضیحات، عکس
await client.set_chat_title(chat_id, "اسم جدید گروه")
await client.set_chat_description(chat_id, "توضیحات جدید")
await client.set_chat_photo(chat_id, "/path/to/photo.jpg")   # progress bar پیش‌فرض
await client.delete_chat_photo(chat_id)

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
