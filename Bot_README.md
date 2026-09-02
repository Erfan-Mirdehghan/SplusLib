# 📘 Complete Guide to SplusLib – BotClient

**SplusLib** is a high-level, asynchronous Python library for **Soroush Plus**. It provides two independent clients:

- **`SplusClient`** – an MTProto userbot client (logs in with a phone number and verification code, can do everything a regular user can do).
- **`BotClient`** – a client for the official **HTTP Bot API** (`api.splus.ir`), which is an almost exact clone of the Telegram Bot API. It authenticates with a bot token from `splus.ir/botfather`, with no phone number required.

This documentation covers **`BotClient`** in full detail.

---

## 📦 Installation

```bash
pip install spluslib
```

To install with SOCKS proxy support (for `SplusClient`):

```bash
pip install spluslib[socks]
```

To install with conference call support (for `SplusClient`):

```bash
pip install spluslib[calls]
```

---

## 🚀 Quick Start

```python
import asyncio
from spluslib.bot_client import BotClient, BotMessage, BotCallbackQuery

bot = BotClient("TOKEN")  # Get your token from splus.ir/botfather

@bot.on_message(lambda m: m.get("text") == "/start")
async def start(msg: BotMessage):
    await msg.reply("Hello! I'm alive.")

@bot.on_callback_query()
async def on_click(query: BotCallbackQuery):
    await query.answer(text=f"You pressed: {query.data}")

async def main():
    await bot.run_polling()

asyncio.run(main())
```

---

## 🧩 Importing

```python
from spluslib.bot_client import BotClient, BotMessage, BotCallbackQuery
```

Helper classes are also available directly from the top-level package:

```python
from spluslib import BotClient, BotMessage, BotCallbackQuery
```

---

## 🔧 Creating a BotClient Instance

```python
bot = BotClient(
    token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    base_url="https://api.splus.ir",           # optional
    file_base_url="https://api.splus.ir/file", # optional
    request_timeout=60.0,                      # optional
    connector=None,                            # aiohttp connector
    debug=False                                # for verbose logging
)
```

- **`token`** – bot token (required)
- **`base_url`** – API base URL (default: `https://api.splus.ir`)
- **`file_base_url`** – file download base URL (default: `https://api.splus.ir/file`)
- **`request_timeout`** – request timeout in seconds
- **`debug=True`** – prints every request and raw response to `stderr` (useful for troubleshooting)

---

## 📡 Calling API Methods

### 1. Using the Exact Official Method Name (camelCase)

Every official Bot API method can be called via `call()` or directly as a method attribute:

```python
await bot.call("sendMessage", chat_id=chat_id, text="Hello")
await bot.sendDice(chat_id=chat_id, emoji="🎯")
await bot.getMe()
```

### 2. Using snake_case Convenience Wrappers

Common methods have snake_case wrappers that accept local file paths, URLs, or raw bytes directly, and show upload progress bars:

```python
await bot.send_message(chat_id, "Text", parse_mode="HTML")
await bot.send_photo(chat_id, "photo.jpg", caption="Image")
await bot.send_document(chat_id, "report.pdf")
```

---

## 📨 Receiving and Handling Events

### Event Decorators

```python
@bot.on_message()                     # new messages
@bot.on_edited_message()              # edited messages
@bot.on_callback_query()              # inline button clicks
@bot.on_inline_query()                # inline queries (e.g., @bot query)
@bot.on_update()                      # every update, regardless of type
```

Handlers can be **asynchronous** or **synchronous**.

### Filtering with Predicates

You can pass a predicate function to the decorator to filter updates:

```python
@bot.on_message(lambda m: "text" in m and m["text"].startswith("/"))
async def command_handler(msg: BotMessage):
    await msg.reply("Command received")
```

---

## 💬 Message and Query Helper Classes

### `BotMessage` – Subclass of the Message Dictionary

All normal dict features (`msg["text"]`, `"photo" in msg`, `json.dumps(msg)`) work, plus convenient methods:

```python
@bot.on_message()
async def handler(msg: BotMessage):
    print(msg.chat_id, msg.message_id, msg.sender_id, msg.text)
    
    # Reply to the same chat with reply_to_message_id set automatically
    await msg.reply("Reply")
    await msg.reply_photo("cat.jpg")
    await msg.reply_audio("song.mp3")
    await msg.reply_document("file.pdf")
    await msg.reply_video("video.mp4")
    await msg.reply_voice("voice.ogg")
    await msg.reply_animation("gif.mp4")
    await msg.reply_dice(emoji="🎯")
    
    # Delete the message
    await msg.delete()
    
    # Get the attached file (if any) and download it
    file_content = await msg.get_file_and_download()        # returns bytes
    file_path = await msg.get_file_and_download("saved")    # saves to path
```

### `BotCallbackQuery` – Subclass of the Callback Query Dictionary

```python
@bot.on_callback_query()
async def on_click(query: BotCallbackQuery):
    print(query.data, query.chat_id, query.sender_id)
    
    # Answer the query (required to remove the loading state)
    await query.answer(text="Received!", show_alert=False)
    
    # Access the originating message
    msg = query.message
    if msg:
        await msg.reply("Button was pressed")
```

---

## 🖼️ Sending Files

All file-sending methods accept the following inputs:

- **Local file path** (string) – uploaded
- **URL** (string starting with `http://` or `https://`) – Soroush fetches it directly (no upload)
- **Existing `file_id`** – sent instantly
- **Raw `bytes`** – uploaded

All have a `progress` parameter (default `True`) that shows a console progress bar:

```python
await bot.send_photo(chat_id, "photo.jpg", caption="Caption", parse_mode="HTML")
await bot.send_audio(chat_id, "song.mp3", performer="Artist", title="Song")
await bot.send_document(chat_id, "file.pdf", caption="Report")
await bot.send_video(chat_id, "video.mp4", supports_streaming=True)
await bot.send_animation(chat_id, "animation.gif")
await bot.send_voice(chat_id, "voice.ogg", duration=10)
await bot.send_video_note(chat_id, "note.mp4", length=240)
await bot.send_sticker(chat_id, "sticker.webp")
```

### Sending Albums (Media Groups)

```python
await bot.send_media_group(chat_id, [
    {"type": "photo", "media": "https://example.com/1.jpg", "caption": "First"},
    {"type": "photo", "media": "https://example.com/2.jpg"},
])
```

For local files, use the `attach://` convention (identical to Telegram):

```python
await bot.send_media_group(chat_id, [
    {"type": "photo", "media": "attach://photo1", "caption": "Local"},
], photo1=open("photo.jpg", "rb"))   # or pass a file path
```

---

## 📥 Downloading Files

```python
# Get file info
file_info = await bot.get_file(file_id)
file_path = file_info["file_path"]

# Download as bytes
data = await bot.download_file(file_id)

# Or save to a specific path
path = await bot.download_file(file_id, "saved.jpg")
```

---

## ⌨️ Keyboards

### 1. Inline Keyboard

```python
from spluslib.bot_client import inline_keyboard  # or bot.inline_keyboard

kb = inline_keyboard([
    [{"text": "Yes", "callback_data": "yes"}, {"text": "No", "callback_data": "no"}],
    [{"text": "Website", "url": "https://example.com"}],
])
await bot.send_message(chat_id, "Choose:", reply_markup=kb)
```

### 2. Reply Keyboard (Custom Keyboard)

```python
from spluslib.bot_client import reply_keyboard

kb = reply_keyboard([
    ["Option A", "Option B"],
    ["Cancel"]
], resize_keyboard=True, one_time_keyboard=False)
await bot.send_message(chat_id, "Select an option:", reply_markup=kb)
```

### 3. Remove Keyboard

```python
from spluslib.bot_client import remove_keyboard

await bot.send_message(chat_id, "Keyboard removed", reply_markup=remove_keyboard())
```

### 4. Force Reply

```python
from spluslib.bot_client import force_reply

await bot.send_message(chat_id, "Please reply:", reply_markup=force_reply(input_field_placeholder="Type your message..."))
```

> **Note:** All keyboard helper functions are also available as static methods on `BotClient` itself:  
> `bot.inline_keyboard(...)`, `bot.reply_keyboard(...)`, `bot.remove_keyboard()`, `bot.force_reply(...)`

---

## 📊 Polls

```python
# Simple poll
await bot.send_poll(chat_id, "Best pizza topping?", ["Pepperoni", "Mushroom", "Pineapple"])

# Quiz
await bot.send_poll(chat_id, "2 + 2 = ?", ["3", "4", "5"],
                    type="quiz", correct_option_id=1,
                    explanation="Simple math!")

# Stop a poll
await bot.stop_poll(chat_id, message_id)
```

---

## 👥 Chat and Member Management

```python
# Ban/Unban
await bot.ban_chat_member(chat_id, user_id, until_date=timestamp, revoke_messages=True)
await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)

# Restrict
await bot.restrict_chat_member(chat_id, user_id, {"can_send_messages": False}, until_date=...)

# Promote to admin
await bot.promote_chat_member(chat_id, user_id, can_delete_messages=True, can_invite_users=True)

# Set custom admin title
await bot.set_chat_administrator_custom_title(chat_id, user_id, "Senior Admin")

# Chat info
chat = await bot.get_chat(chat_id)
admins = await bot.get_chat_administrators(chat_id)
count = await bot.get_chat_member_count(chat_id)
member = await bot.get_chat_member(chat_id, user_id)

# Chat settings
await bot.set_chat_title(chat_id, "New Title")
await bot.set_chat_description(chat_id, "Description")
await bot.set_chat_photo(chat_id, "photo.jpg")
await bot.delete_chat_photo(chat_id)
await bot.leave_chat(chat_id)

# Pinning
await bot.pin_chat_message(chat_id, message_id, disable_notification=False)
await bot.unpin_chat_message(chat_id, message_id)
```

---

## 🔗 Invite Links and Join Requests

```python
# Create an invite link
link_info = await bot.create_chat_invite_link(
    chat_id,
    name="Special Link",
    expire_date=timestamp,
    member_limit=10,
    creates_join_request=True
)

# Edit a link
await bot.edit_chat_invite_link(chat_id, invite_link, name="New", member_limit=20)

# Revoke a link
await bot.revoke_chat_invite_link(chat_id, invite_link)

# Approve/decline join requests
await bot.approve_chat_join_request(chat_id, user_id)
await bot.decline_chat_join_request(chat_id, user_id)
```

---

## 🌐 Webhook vs. Polling

### Polling (Default)

```python
await bot.run_polling(
    poll_timeout=30,         # long-poll timeout
    limit=100,               # updates per request
    allowed_updates=["message", "callback_query"],
    drop_pending_updates=False,
    on_error=my_error_handler   # optional
)
```

To stop polling:

```python
bot.stop_polling()
```

### Webhook (Soroush pushes updates to you)

```python
await bot.run_webhook(
    url="https://your-domain.com/bot",  # must be public and reachable
    host="0.0.0.0",          # local bind address
    port=8443,               # local port
    path="/bot",             # path (defaults to path in `url`)
    certificate="cert.pem",  # optional SSL certificate
    ip_address="1.2.3.4",    # optional fixed IP
    max_connections=40,
    allowed_updates=None,
    drop_pending_updates=False,
    secret_token="my-secret"  # recommended for security
)
```

**Important:** Set `secret_token` to reject spoofed requests.  
To stop the webhook:

```python
await bot.stop_webhook(delete=True)  # also unregisters the webhook
```

---

## 🧪 Debugging with `debug=True`

If you encounter a cryptic error, enable `debug=True` to see the full request and raw response:

```python
bot = BotClient(token, debug=True)
```

Output is printed to `stderr` and includes the method, parameters, file attachments, and the complete response body.

---

## 📚 Complete Method Reference for `BotClient`

| Category | Methods |
|----------|---------|
| **Lifecycle** | `get_me()`, `log_out()`, `close_bot()`, `close()` |
| **Updates & Webhook** | `get_updates()`, `set_webhook()`, `delete_webhook()`, `get_webhook_info()` |
| **Messages** | `send_message()`, `forward_message()`, `copy_message()`, `edit_message_text()`, `edit_message_caption()`, `edit_message_reply_markup()`, `delete_message()`, `pin_chat_message()`, `unpin_chat_message()`, `send_chat_action()` |
| **Media** | `send_photo()`, `send_audio()`, `send_document()`, `send_video()`, `send_animation()`, `send_voice()`, `send_video_note()`, `send_sticker()`, `send_media_group()` |
| **Location & Contact** | `send_location()`, `send_contact()` |
| **Dice & Polls** | `send_dice()`, `send_poll()`, `stop_poll()` |
| **Chat Management** | `get_chat()`, `leave_chat()`, `get_chat_administrators()`, `get_chat_member_count()`, `get_chat_member()`, `set_chat_title()`, `set_chat_description()`, `set_chat_photo()`, `delete_chat_photo()`, `ban_chat_member()`, `unban_chat_member()`, `restrict_chat_member()`, `promote_chat_member()`, `set_chat_administrator_custom_title()`, `set_chat_permissions()` |
| **Invite Links** | `create_chat_invite_link()`, `edit_chat_invite_link()`, `revoke_chat_invite_link()`, `approve_chat_join_request()`, `decline_chat_join_request()` |
| **Files** | `get_file()`, `download_file()`, `get_file_url()` |
| **Bot Commands** | `set_my_commands()`, `delete_my_commands()`, `get_my_commands()` |
| **Callback Queries** | `answer_callback_query()` |
| **Misc** | `get_user_profile_photos()` |

---

## 💡 Complete Examples

### Echo Bot

```python
import asyncio
from spluslib.bot_client import BotClient, BotMessage

bot = BotClient("TOKEN")

@bot.on_message(lambda m: m.get("text") is not None)
async def echo(msg: BotMessage):
    await msg.reply(msg.text)

asyncio.run(bot.run_polling())
```

### Bot with Inline Keyboard

```python
@bot.on_message(lambda m: m.get("text") == "/menu")
async def show_menu(msg: BotMessage):
    kb = bot.inline_keyboard([
        [{"text": "Option 1", "callback_data": "opt1"}],
        [{"text": "Option 2", "callback_data": "opt2"}],
    ])
    await msg.reply("Menu:", reply_markup=kb)

@bot.on_callback_query()
async def menu_click(query: BotCallbackQuery):
    await query.answer(text=f"Selected: {query.data}")
    await bot.send_message(query.chat_id, f"You chose {query.data}.")
```

### Sending Files with Custom Progress

```python
# With default progress bar
await bot.send_document(chat_id, "large_file.zip", progress=True)

# With custom progress function
def my_progress(current, total):
    print(f"Progress: {current/total*100:.1f}%")

await bot.send_video(chat_id, "video.mp4", progress=my_progress)
```

---

## 🔗 Useful Links

- **GitHub Repository:** [https://github.com/Erfan-Mirdehghan/SplusLib](https://github.com/Erfan-Mirdehghan/SplusLib)
- **Soroush Plus:** [https://splus.ir](https://splus.ir)
- **`@botfather` for bot tokens:** Search for it on Soroush Plus.

---

## 📄 License

MIT License

---

**Note:** This documentation is based on the current version of the library. For any changes or updates, refer to the official repository and documentation.

---

**Happy coding!** 🚀
