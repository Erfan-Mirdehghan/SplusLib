# 📚 BotClient - Python Library for Soroush Plus Bot API

<div align="center">

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)

**یک کتابخانه قدرتمند، کامل و آسان‌برای استفاده از API بات سروش‌پلاس**

[English](README.md) | [فارسی](README.fa.md)

</div>

---

## 👨‍💻 توسعه‌دهنده

**سازنده:** Erfan Mirdehghan (عرفان میردهقان)

---

## ✨ ویژگی‌ها

- ✅ **پشتیبانی کامل از API بات سروش‌پلاس** - تمام متدهای رسمی API
- ✅ **Async/Await** - کاملاً غیرهمزمان با `aiohttp`
- ✅ **ارسال فایل** - پشتیبانی از آپلود فایل‌های محلی، URL و bytes
- ✅ **دریافت فایل** - دانلود فایل‌ها با `file_id`
- ✅ **کیبوردهای اینلاین و پاسخ** - ساخت آسان کیبوردهای تعاملی
- ✅ **نظرسنجی (Poll)** - ارسال و مدیریت نظرسنجی‌ها
- ✅ **مدیریت گروه** - بن، آنبن، محدودیت، ترفیع و...
- ✅ **وب‌هوک (Webhook)** - پشتیبانی از دریافت به‌روزرسانی‌ها از طریق Webhook
- ✅ **پولینگ (Polling)** - دریافت به‌روزرسانی‌ها با Long Polling
- ✅ **پیشرفت آپلود** - نمایش نوار پیشرفت برای آپلود فایل‌ها
- ✅ **مدیریت خطا** - مدیریت خودکار خطاها و محدودیت سرعت
- ✅ **دیباگ** - نمایش درخواست‌ها برای رفع اشکال

---

## 📦 نصب

```bash
pip install spluslib
```

یا اگر می‌خواهید از آخرین نسخه استفاده کنید:

```bash
pip install git+https://github.com/yourusername/spluslib.git
```

### پیش‌نیازها

```bash
pip install aiohttp
```

---

## 🚀 شروع سریع

### ۱. دریافت توکن بات

ابتدا در پیام‌رسان سروش‌پلاس به ربات `@soroush_plus_bot` پیام دهید و یک بات جدید بسازید. توکن خود را کپی کنید.

### ۲. کد اولیه

```python
import asyncio
from spluslib.bot_client import BotClient

# ایجاد نمونه بات
bot = BotClient("YOUR_BOT_TOKEN_HERE")

# تعریف یک هندلر برای پیام‌ها
@bot.on_message()
async def echo(message):
    if "text" in message:
        await bot.send_message(
            message["chat"]["id"],
            f"شما گفتید: {message['text']}"
        )

# اجرای بات
async def main():
    await bot.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📖 راهنمای کامل

### ایجاد نمونه بات

```python
from spluslib.bot_client import BotClient

# حالت عادی
bot = BotClient("TOKEN")

# با دیباگ فعال
bot = BotClient("TOKEN", debug=True)

# با تنظیمات سفارشی
bot = BotClient(
    "TOKEN",
    base_url="https://api.splus.ir",  # URL پیش‌فرض
    request_timeout=120.0,             # تایم‌اوت ۱۲۰ ثانیه
    debug=True
)
```

### ارسال پیام

```python
# ارسال پیام ساده
await bot.send_message(chat_id, "سلام!")

# ارسال پیام با قالب‌بندی HTML
await bot.send_message(
    chat_id,
    "<b>سلام</b> <i>دنیا!</i>",
    parse_mode="HTML"
)

# ارسال پیام با قالب‌بندی MarkdownV2
from spluslib.bot_client import escape_markdown

text = escape_markdown("سلام! *دنیا*")
await bot.send_message(
    chat_id,
    text,
    parse_mode="MarkdownV2"
)

# ارسال پیام با کیبورد
keyboard = bot.inline_keyboard([
    [{"text": "✅ بله", "callback_data": "yes"}]
])
await bot.send_message(
    chat_id,
    "یک گزینه انتخاب کنید:",
    reply_markup=keyboard
)
```

### دریافت پیام‌ها

#### روش ۱: Polling (پیش‌فرض)

```python
@bot.on_message()
async def handler(message):
    chat_id = message["chat"]["id"]
    text = message.get("text")
    
    if text == "/start":
        await bot.send_message(chat_id, "سلام! به بات خوش آمدید.")
    elif text == "/help":
        await bot.send_message(chat_id, "دستورات موجود: /start, /help")

await bot.run_polling()
```

#### روش ۲: Webhook

```python
# راه‌اندازی Webhook
await bot.run_webhook(
    "https://your-domain.com/webhook",
    port=8443,
    secret_token="your-secret-token"
)
```

### ارسال فایل‌ها

```python
# ارسال عکس
await bot.send_photo(chat_id, "photo.jpg")
await bot.send_photo(chat_id, "https://example.com/image.jpg")
await bot.send_photo(chat_id, image_bytes)

# ارسال فایل صوتی (Voice)
await bot.send_voice(chat_id, "voice.ogg")

# ارسال فایل صوتی (Audio) با متادیتا
await bot.send_audio(
    chat_id,
    "song.mp3",
    title="آهنگ زیبا",
    performer="خواننده",
    duration=180
)

# ارسال فایل معمولی
await bot.send_document(chat_id, "document.pdf")

# ارسال ویدیو
await bot.send_video(
    chat_id,
    "video.mp4",
    caption="ویدیوی تست",
    supports_streaming=True
)
```

### کیبوردهای تعاملی

#### کیبورد اینلاین (Inline Keyboard)

```python
keyboard = bot.inline_keyboard([
    [
        {"text": "✅ بله", "callback_data": "yes"},
        {"text": "❌ خیر", "callback_data": "no"}
    ],
    [
        {"text": "🔗 لینک", "url": "https://example.com"}
    ]
])

await bot.send_message(chat_id, "انتخاب کنید:", reply_markup=keyboard)

# هندلر کلیک
@bot.on_callback_query()
async def on_callback(query):
    if query.data == "yes":
        await query.answer("✅ انتخاب شد!")
    elif query.data == "no":
        await query.answer("❌ رد شد!")
```

#### کیبورد پاسخ (Reply Keyboard)

```python
keyboard = bot.reply_keyboard([
    ["گزینه ۱", "گزینه ۲"],
    ["گزینه ۳"]
])

await bot.send_message(
    chat_id,
    "یک گزینه انتخاب کنید:",
    reply_markup=keyboard
)

# حذف کیبورد
await bot.send_message(
    chat_id,
    "کیبورد حذف شد",
    reply_markup=bot.remove_keyboard()
)
```

### نظرسنجی (Poll)

```python
# نظرسنجی عادی
await bot.send_poll(
    chat_id,
    "بهترین زبان برنامه‌نویسی؟",
    ["Python", "JavaScript", "Go", "Rust"]
)

# آزمون (Quiz)
await bot.send_poll(
    chat_id,
    "۲ + ۲ = ؟",
    ["۳", "۴", "۵"],
    type="quiz",
    correct_option_id=1,
    explanation="جواب درست ۴ است!"
)
```

### دریافت فایل

```python
# دریافت اطلاعات فایل
file_info = await bot.get_file(file_id)

# دانلود فایل به صورت bytes
file_bytes = await bot.download_file(file_id)

# ذخیره فایل روی دیسک
file_path = await bot.download_file(file_id, "downloaded.jpg")

# دریافت فایل از پیام
@bot.on_message()
async def on_file(message):
    if "photo" in message or "document" in message:
        file_data = await message.get_file_and_download()
        if file_data:
            await message.reply("فایل دریافت شد!")
```

### مدیریت گروه

```python
# بن کردن کاربر
await bot.ban_chat_member(group_id, user_id)

# آنبن کردن
await bot.unban_chat_member(group_id, user_id)

# محدود کردن (مثلاً بی‌صدا کردن)
await bot.restrict_chat_member(
    group_id,
    user_id,
    {"can_send_messages": False}
)

# ترفیع به ادمین
await bot.promote_chat_member(
    group_id,
    user_id,
    can_delete_messages=True,
    can_invite_users=True
)

# دریافت لیست ادمین‌ها
admins = await bot.get_chat_administrators(group_id)

# تعداد اعضا
count = await bot.get_chat_member_count(group_id)
```

### لینک‌های دعوت

```python
# ایجاد لینک دعوت
invite = await bot.create_chat_invite_link(
    group_id,
    name="لینک ویژه",
    member_limit=10,
    expire_date=int(time.time()) + 86400  # ۱ روز
)

# ویرایش لینک
await bot.edit_chat_invite_link(
    group_id,
    invite["invite_link"],
    member_limit=20
)

# لغو لینک
await bot.revoke_chat_invite_link(group_id, invite["invite_link"])
```

### دستورات بات

```python
# تنظیم دستورات
await bot.set_my_commands([
    {"command": "start", "description": "شروع"},
    {"command": "help", "description": "راهنما"},
    {"command": "about", "description": "درباره بات"}
])

# دریافت دستورات
commands = await bot.get_my_commands()
```

### مدیریت خطا

```python
try:
    await bot.send_message(chat_id, "سلام!")
except FloodWaitError as e:
    print(f"لطفاً {e.seconds} ثانیه صبر کنید")
except BotAPIError as e:
    print(f"خطای API: {e}")
```

---

## 📘 راهنمای قالب‌بندی

### HTML

```python
text = """
<b>پررنگ</b>
<i>ایتالیک</i>
<u>زیرخط</u>
<s>خط خورده</s>
<a href="https://example.com">لینک</a>
<code>کد درون‌خطی</code>
<pre>بلوک کد</pre>
<pre><code class="language-python">print("سلام!")</code></pre>
<blockquote>نقل قول</blockquote>
<blockquote expandable>نقل قول بازشونده</blockquote>
"""

await bot.send_message(chat_id, text, parse_mode="HTML")
```

### MarkdownV2

```python
from spluslib.bot_client import escape_markdown

text = escape_markdown("""
*پررنگ*
_ایتالیک_
__زیرخط__
~خط خورده~
||اسپویلر||
[لینک](https://example.com)
`کد درون‌خطی`
```
بلوک کد
```
```python
print("سلام!")
```
> نقل قول
> ادامه نقل قول
""")

await bot.send_message(chat_id, text, parse_mode="MarkdownV2")
```

---

## 🔧 مثال‌های پیشرفته

### ۱. ربات Echo با کیبورد اینلاین

```python
import asyncio
from spluslib.bot_client import BotClient

bot = BotClient("YOUR_TOKEN")

@bot.on_message(lambda m: m.get("text") == "/start")
async def start(message):
    keyboard = bot.inline_keyboard([
        [{"text": "📝 Echo", "callback_data": "echo"}],
        [{"text": "📊 Status", "callback_data": "status"}]
    ])
    await message.reply(
        "به ربات Echo خوش آمدید!",
        reply_markup=keyboard
    )

@bot.on_callback_query()
async def callback(query):
    await query.answer()
    
    if query.data == "echo":
        await bot.send_message(
            query.chat_id,
            "یک پیام بفرستید تا Echo کنم..."
        )
    elif query.data == "status":
        await bot.send_message(
            query.chat_id,
            "✅ ربات فعال است!"
        )

@bot.on_message(lambda m: m.get("text") and not m.get("text").startswith("/"))
async def echo(message):
    await message.reply(f"🔊 {message.text}")

async def main():
    await bot.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
```

### ۲. ربات مدیریت گروه

```python
from spluslib.bot_client import BotClient

bot = BotClient("YOUR_TOKEN")

@bot.on_message(lambda m: m.get("text") == "/ban")
async def ban_user(message):
    if "reply_to_message" in message:
        user_id = message["reply_to_message"]["from"]["id"]
        await bot.ban_chat_member(message.chat_id, user_id)
        await message.reply(f"🚫 کاربر بن شد!")
    else:
        await message.reply("❌ روی پیام کاربر ریپلای کنید!")

@bot.on_message(lambda m: m.get("text") == "/mute")
async def mute_user(message):
    if "reply_to_message" in message:
        user_id = message["reply_to_message"]["from"]["id"]
        await bot.restrict_chat_member(
            message.chat_id,
            user_id,
            {"can_send_messages": False}
        )
        await message.reply("🔇 کاربر بی‌صدا شد!")
    else:
        await message.reply("❌ روی پیام کاربر ریپلای کنید!")
```

---

## 🐛 رفع اشکال

### فعال‌سازی دیباگ

```python
bot = BotClient("TOKEN", debug=True)
```

### مدیریت خطا در Polling

```python
async def error_handler(error):
    print(f"❌ خطا: {error}")

await bot.run_polling(on_error=error_handler)
```

### خطاهای رایج

| خطا | راه‌حل |
|-----|--------|
| `Bad Request: NOT_SUPPORTED` | فرمت فایل پشتیبانی نمی‌شود. از `send_document` استفاده کنید |
| `query is too old` | سریع‌تر به `callback_query` پاسخ دهید |
| `FloodWaitError` | صبر کنید و دوباره تلاش کنید |
| `Bad Request: can't parse entities` | کاراکترهای خاص را با `escape_markdown` Escape کنید |

---

## 📚 مراجع

- [مستندات رسمی API بات سروش‌پلاس](https://soroushplus.com/p/documents/bot-platform)
- [دریافت توکن بات](https://splus.ir/botfather)
- [گیت‌هاب پروژه](https://github.com/yourusername/spluslib)

---
---

## 📄 مجوز

این پروژه تحت مجوز **MIT** منتشر شده است. برای اطلاعات بیشتر فایل [LICENSE](LICENSE) را ببینید.

---

<div align="center">

**ساخته شده با ❤️ توسط Erfan Mirdehghan**

[![GitHub](https://img.shields.io/badge/GitHub-ErfanMirdehghan-181717?style=for-the-badge&logo=github)](https://github.com/ErfanMirdehghan)
[![Telegram](https://img.shields.io/badge/Telegram-@ErfanMirdehghan-2CA5E0?style=for-the-badge&logo=telegram)](https://t.me/ErfanMirdehghan)

</div>
