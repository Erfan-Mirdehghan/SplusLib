# SplusLib

High-level, async Python library for **Soroush Plus**. Two independent clients, pick whichever fits:

- **`SplusClient`** — an MTProto *userbot* client (logs in as a real account, phone number + login code, can do anything a person can do in the app: messages, files, stories, groups, calls, ...).
- **`BotClient`** — a client for the official **HTTP Bot API** (`api.splus.ir`), which is a near-exact clone of the Telegram Bot API. Logs in with a bot token from `splus.ir/fatherbot`, no phone number involved.

They're fully independent to use, but ship together — one `pip install spluslib` gets both `SplusClient` and `BotClient` working, no extras required:

```bash
pip install spluslib                    # everything: SplusClient + BotClient
pip install spluslib[all]               # + SOCKS proxy support + conference calls (rarely needed)
```

---

## BotClient (official HTTP Bot API)

```python
import asyncio
from spluslib import BotClient

bot = BotClient("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")  # from splus.ir/fatherbot

@bot.on_message(lambda m: m.get("text") == "/start")
async def start(msg):
    await msg.reply("Hello! I'm alive.")

@bot.on_callback_query()
async def on_click(query):
    await query.answer(text="Got it!")
    await bot.send_message(query.chat_id, f"You picked: {query.data}")

async def main():
    await bot.run_polling()

asyncio.run(main())
```

### Two ways to call any method

1. **Exact official method name** — every single Bot API method works this way, even ones with no explicit wrapper below, since Soroush's Bot API mirrors Telegram's method-for-method:

   ```python
   await bot.sendDice(chat_id=chat_id, emoji="🎯")
   await bot.getMe()
   ```

2. **Pythonic snake_case wrappers** for the common ones — accept local file paths, URLs, or raw bytes directly, with console progress bars for uploads:

   ```python
   await bot.send_photo(chat_id, "photo.jpg")
   await bot.send_voice(chat_id, "voice.mp3")
   await bot.send_document(chat_id, "report.pdf", caption="Here you go")
   ```

Both hit the same HTTP endpoint — use whichever reads better.

### Messages you receive

Handlers receive `BotMessage`/`BotCallbackQuery` — real `dict` subclasses (so `msg["text"]`, `"photo" in msg`, `json.dumps(msg)` all still work exactly like the raw API), with convenience on top:

```python
@bot.on_message()
async def handler(msg):
    print(msg.text, msg.chat_id, msg.sender_id)
    await msg.reply("got it")                    # sendMessage to this chat, replying to msg
    await msg.reply_photo("photo.jpg")            # sendPhoto, same deal
    file_path = await msg.get_file_and_download()  # downloads whatever file is attached, if any
```

For explicit type annotations (so your editor autocompletes even without inference from the decorator), both are importable from the top level:

```python
from spluslib import BotClient, BotMessage, BotCallbackQuery

bot = BotClient(token)

@bot.on_message()
async def handler(msg: BotMessage):
    await msg.reply("test")

@bot.on_callback_query()
async def on_click(query: BotCallbackQuery):
    await query.answer()
```

### Keyboards

```python
from spluslib import inline_keyboard, reply_keyboard, remove_keyboard, force_reply
# or equivalently: bot.inline_keyboard(...), bot.reply_keyboard(...), etc.

kb = inline_keyboard([
    [{"text": "Yes", "callback_data": "yes"}, {"text": "No", "callback_data": "no"}],
    [{"text": "Visit site", "url": "https://example.com"}],
])
await bot.send_message(chat_id, "Pick one:", reply_markup=kb)

kb = reply_keyboard([["Option A", "Option B"], ["Cancel"]])
await bot.send_message(chat_id, "Choose:", reply_markup=kb)

await bot.send_message(chat_id, "Keyboard removed", reply_markup=remove_keyboard())
```

### Polls

```python
await bot.send_poll(chat_id, "Best pizza topping?", ["Pepperoni", "Mushroom", "Pineapple"])

await bot.send_poll(chat_id, "2 + 2 = ?", ["3", "4", "5"],
                     type="quiz", correct_option_id=1, explanation="Basic arithmetic!")

await bot.stop_poll(chat_id, message_id)
```

### Files

```python
await bot.send_photo(chat_id, "local.jpg")               # local path -- uploaded, streamed from disk
await bot.send_photo(chat_id, "https://example.com/x.jpg")  # URL -- Soroush fetches it directly
await bot.send_photo(chat_id, "AgACAgIAAx...")            # existing file_id -- instant, no upload
await bot.send_photo(chat_id, raw_bytes)                  # raw bytes also accepted

file_info = await bot.get_file(file_id)
data = await bot.download_file(file_id)                   # bytes
path = await bot.download_file(file_id, "saved.jpg")      # or save straight to a path
```

`send_photo`, `send_audio`, `send_document`, `send_video`, `send_animation`, `send_voice`, `send_video_note`, `send_sticker`, `send_media_group` all follow this same pattern.

### Chat & member management

```python
await bot.ban_chat_member(chat_id, user_id)
await bot.unban_chat_member(chat_id, user_id)
await bot.restrict_chat_member(chat_id, user_id, {"can_send_messages": False})
await bot.promote_chat_member(chat_id, user_id, can_delete_messages=True)
await bot.set_chat_title(chat_id, "New title")
await bot.get_chat_administrators(chat_id)
await bot.get_chat_member(chat_id, user_id)

link = await bot.create_chat_invite_link(chat_id, name="Marketing")
await bot.approve_chat_join_request(chat_id, user_id)
```

### Long polling vs. webhook

```python
# Long polling (default, simplest -- works anywhere, no public URL needed)
await bot.run_polling()

# Webhook (Soroush pushes updates to you instead) -- starts a built-in
# HTTP server, registers it with setWebhook(), and prints the result:
await bot.run_webhook("https://your-domain.com/bot", port=8443)
```

`run_webhook` binds a local HTTP server (`host=`/`port=`) and tells Soroush to POST updates to your public `url` — put a reverse proxy (nginx, Caddy, ...) in front if your public port differs from the one you bind to. Pass `secret_token=` to reject spoofed requests. Call `await bot.stop_webhook()` to unregister and stop.

### Debugging opaque errors

If a call fails with a terse error, turn on `debug=True` to see the exact outgoing request and full raw response:

```python
bot = BotClient(token, debug=True)
```

---

## SplusClient (MTProto userbot)

```python
import asyncio
from spluslib import SplusClient

client = SplusClient("my_session")

@client.on_message()
async def handler(event):
    await event.reply("Hello!")

async def main():
    await client.start("+989123456789")
    await client.run_until_disconnected()

asyncio.run(main())
```

Covers messaging (send/edit/delete/forward/pin/react), rich text formatting (Markdown/HTML, including underline/spoiler/blockquote), mentions, polls, reporting, files/photos/video/voice/audio, stories, account and group management, invite links, contacts, and conference calls. Event decorators mirror `BotClient`'s style: `on_message`, `on_edited`, `on_update` (both new and edited), `on_deleted`, `on_read`, `on_reaction`, `on_chat_action`, `on_user_update`, `on_callback`, `on_inline`, `on_album`, `on_raw`.

Editor autocomplete (`event.reply`, `msg.sender_id`, etc.) is fully typed via bundled `.pyi` stubs — works out of the box in VS Code/Pylance and similar.

---

## Requirements

- Python 3.8+
- `aiohttp`, `pyaes`, `rsa` — all installed automatically with `pip install spluslib`, no extras needed for either client
- `PySocks` (only if you need SOCKS proxy support with `SplusClient`) — `pip install spluslib[socks]`
- `livekit` (only for `SplusClient`'s `CallAudioSession`, joining conference calls) — `pip install spluslib[calls]`

## License

MIT
