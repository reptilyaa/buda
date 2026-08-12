import os
import discord
from discord.ext import commands

import sqlite3
from dotenv import load_dotenv
from yt_dlp import YoutubeDL
import asyncio
import re
import time
BRIGADE_COOLDOWN = 300  # 5 минут в секундах
last_brigade_call = 0


# ====== Настройки ======
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# ====== Telegram ↔ Discord Bridge ======

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "0")

DISCORD_CHAT_CHANNEL_ID = os.getenv(
    "DISCORD_CHAT_CHANNEL_ID", "0"
)

DISCORD_TG_CHANNEL_ID = os.getenv(
    "DISCORD_TG_CHANNEL_ID", "0"
)

telegram_session = None
telegram_task = None
telegram_bot_id = None
telegram_offset = 0



# ============================================================
# TELEGRAM ↔ DISCORD BRIDGE
# ============================================================

import aiohttp
import os
import asyncio
import io

# ============================================================
# НАСТРОЙКИ
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "0"
).strip()

DISCORD_CHAT_CHANNEL_ID = os.getenv(
    "DISCORD_CHAT_CHANNEL_ID",
    "0"
).strip()

DISCORD_TG_CHANNEL_ID = os.getenv(
    "DISCORD_TG_CHANNEL_ID",
    "0"
).strip()

# ============================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================

telegram_session = None
telegram_task = None

telegram_bot_id = None
telegram_offset = 0

# ============================================================
# TELEGRAM API
# ============================================================

async def telegram_api(method, data=None):

    global telegram_session

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN не указан в .env"
        )

        return None

    if telegram_session is None:

        telegram_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=120
            )
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )

    try:

        async with telegram_session.post(
            url,
            data=data or {}
        ) as response:

            raw = await response.read()

            try:

                result = await response.json(
                    content_type=None
                )

            except Exception:

                text = raw.decode(
                    "utf-8",
                    errors="replace"
                )

                print(
                    "❌ Telegram вернул "
                    f"не JSON: {text[:500]}"
                )

                return None

            if not result.get("ok"):

                print(
                    "❌ Telegram API ошибка: "
                    f"{result}"
                )

            return result

    except Exception as e:

        print(
            "❌ Ошибка подключения "
            f"к Telegram: {e}"
        )

        return None


# ============================================================
# TELEGRAM FILE DOWNLOAD
# ============================================================

async def telegram_download_file(file_id):

    global telegram_session

    file_info = await telegram_api(
        "getFile",
        {
            "file_id": file_id
        }
    )

    if (
        not file_info
        or not file_info.get("ok")
    ):

        print(
            "❌ Не удалось получить "
            "информацию о Telegram-файле"
        )

        return None, None

    file_path = (
        file_info["result"]
        .get("file_path")
    )

    if not file_path:

        print(
            "❌ Telegram file_path отсутствует"
        )

        return None, None

    if telegram_session is None:

        telegram_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=120
            )
        )

    url = (
        f"https://api.telegram.org/"
        f"file/bot{TELEGRAM_TOKEN}/"
        f"{file_path}"
    )

    try:

        async with telegram_session.get(
            url
        ) as response:

            if response.status != 200:

                error_text = await response.text(
                    encoding="utf-8",
                    errors="replace"
                )

                print(
                    "❌ Ошибка скачивания "
                    f"Telegram-файла: "
                    f"{response.status}"
                )

                print(
                    f"Telegram ответ: "
                    f"{error_text[:500]}"
                )

                return None, None

            file_data = await response.read()

            if not file_data:

                print(
                    "❌ Telegram вернул "
                    "пустой файл"
                )

                return None, None

            filename = os.path.basename(
                file_path
            )

            print(
                f"📥 Telegram файл скачан: "
                f"{filename} "
                f"({len(file_data)} байт)"
            )

            return file_data, filename

    except Exception as e:

        print(
            "❌ Ошибка скачивания "
            f"Telegram-файла: {e}"
        )

        return None, None


# ============================================================
# SPLIT MESSAGE
# ============================================================

def split_message(text, limit):

    if not text:

        return []

    if len(text) <= limit:

        return [text]

    parts = []

    while len(text) > limit:

        cut = text.rfind(
            "\n",
            0,
            limit
        )

        if cut <= 0:

            cut = text.rfind(
                " ",
                0,
                limit
            )

        if cut <= 0:

            cut = limit

        parts.append(
            text[:cut]
        )

        text = text[cut:].lstrip()

    if text:

        parts.append(text)

    return parts


# ============================================================
# TELEGRAM TEXT
# ============================================================

async def send_telegram_text(text):

    if not text:

        return

    parts = split_message(
        text,
        4000
    )

    for part in parts:

        await telegram_api(
            "sendMessage",
            {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": part
            }
        )

        await asyncio.sleep(
            0.1
        )


# ============================================================
# TELEGRAM FILE UPLOAD
# ============================================================

async def telegram_upload_file(
    method,
    field_name,
    filename,
    file_bytes,
    caption=None,
    extra=None
):

    global telegram_session

    if telegram_session is None:

        telegram_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=120
            )
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )

    form = aiohttp.FormData()

    form.add_field(
        "chat_id",
        str(TELEGRAM_CHAT_ID)
    )

    form.add_field(
        field_name,
        file_bytes,
        filename=filename,
        content_type="application/octet-stream"
    )

    if caption:

        form.add_field(
            "caption",
            caption[:1024]
        )

    if extra:

        for key, value in extra.items():

            form.add_field(
                key,
                str(value)
            )

    try:

        async with telegram_session.post(
            url,
            data=form
        ) as response:

            raw = await response.read()

            try:

                result = await response.json(
                    content_type=None
                )

            except Exception:

                print(
                    "❌ Telegram upload "
                    "вернул не JSON"
                )

                print(
                    raw.decode(
                        "utf-8",
                        errors="replace"
                    )[:500]
                )

                return None

            if not result.get("ok"):

                print(
                    "❌ Ошибка отправки "
                    f"файла в Telegram: "
                    f"{result}"
                )

            return result

    except Exception as e:

        print(
            "❌ Ошибка upload "
            f"в Telegram: {e}"
        )

        return None


# ============================================================
# DISCORD → TELEGRAM
# ============================================================

async def send_to_telegram(
    text=None,
    attachments=None,
    username="Пользователь"
):

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN не указан"
        )

        return

    if (
        not TELEGRAM_CHAT_ID
        or TELEGRAM_CHAT_ID == "0"
    ):

        print(
            "❌ TELEGRAM_CHAT_ID не указан"
        )

        return

    # ========================================================
    # ТЕКСТ
    # ========================================================

    if text:

        telegram_text = (
            f"👤 {username}: {text}"
        )

        await send_telegram_text(
            telegram_text
        )

    # ========================================================
    # ВЛОЖЕНИЯ
    # ========================================================

    if not attachments:

        return

    for attachment in attachments:

        try:

            print(
                f"📎 Discord attachment: "
                f"{attachment.filename}"
            )

            file_data = await attachment.read()

            if not file_data:

                print(
                    "⚠️ Файл пустой"
                )

                continue

            filename = (
                attachment.filename
                or "file"
            )

            content_type = (
                attachment.content_type
                or ""
            ).lower()

            caption = (
                f"👤 {username}"
            )

            # =================================================
            # IMAGE
            # =================================================

            if content_type.startswith(
                "image/"
            ):

                result = await telegram_upload_file(
                    "sendPhoto",
                    "photo",
                    filename,
                    file_data,
                    caption
                )

            # =================================================
            # VIDEO
            # =================================================

            elif content_type.startswith(
                "video/"
            ):

                result = await telegram_upload_file(
                    "sendVideo",
                    "video",
                    filename,
                    file_data,
                    caption
                )

            # =================================================
            # AUDIO
            # =================================================

            elif content_type.startswith(
                "audio/"
            ):

                result = await telegram_upload_file(
                    "sendAudio",
                    "audio",
                    filename,
                    file_data,
                    caption
                )

            # =================================================
            # ОСТАЛЬНОЕ → DOCUMENT
            # =================================================

            else:

                result = await telegram_upload_file(
                    "sendDocument",
                    "document",
                    filename,
                    file_data,
                    caption
                )

            if result and result.get("ok"):

                print(
                    "✅ Discord → Telegram "
                    "файл отправлен"
                )

            else:

                print(
                    "❌ Discord → Telegram "
                    "файл не отправлен"
                )

        except Exception as e:

            print(
                "❌ Ошибка Discord → "
                f"Telegram файла: {e}"
            )


# ============================================================
# TELEGRAM → DISCORD
# ============================================================

async def send_telegram_media_to_discord(
    channel,
    message,
    username
):

    caption = (
        message.get("caption")
        or ""
    )

    # ========================================================
    # ВСПОМОГАТЕЛЬНАЯ ОТПРАВКА ФАЙЛА
    # ========================================================

    async def send_file_to_discord(
        file_id,
        filename,
        label=None
    ):

        file_data, downloaded_name = (
            await telegram_download_file(
                file_id
            )
        )

        if not file_data:

            return False

        final_filename = (
            filename
            or downloaded_name
            or "file"
        )

        discord_caption = (
            f"👤 **{username}**"
        )

        if label:

            discord_caption += (
                f"\n{label}"
            )

        if caption:

            discord_caption += (
                f"\n{caption}"
            )

        # ====================================================
        # ВАЖНО:
        # bytes → BytesIO
        # ====================================================

        file_object = io.BytesIO(
            file_data
        )

        file_object.seek(0)

        try:

            await channel.send(
                content=discord_caption,
                file=discord.File(
                    file_object,
                    filename=final_filename
                )
            )

        finally:

            file_object.close()

        return True

    # ========================================================
    # PHOTO
    # ========================================================

    if message.get("photo"):

        photo = message["photo"][-1]

        success = await send_file_to_discord(
            photo["file_id"],
            "photo.jpg"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "фото отправлено"
            )

        return

    # ========================================================
    # VIDEO
    # ========================================================

    if message.get("video"):

        video = message["video"]

        success = await send_file_to_discord(
            video["file_id"],
            video.get("file_name")
            or "video.mp4"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "видео отправлено"
            )

        return

    # ========================================================
    # ANIMATION / GIF
    # ========================================================

    if message.get("animation"):

        animation = message[
            "animation"
        ]

        success = await send_file_to_discord(
            animation["file_id"],
            animation.get("file_name")
            or "animation.mp4",
            "🎞️ Анимация"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "GIF отправлен"
            )

        return

    # ========================================================
    # AUDIO
    # ========================================================

    if message.get("audio"):

        audio = message["audio"]

        success = await send_file_to_discord(
            audio["file_id"],
            audio.get("file_name")
            or "audio.mp3"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "аудио отправлено"
            )

        return

    # ========================================================
    # VOICE
    # ========================================================

    if message.get("voice"):

        voice = message["voice"]

        success = await send_file_to_discord(
            voice["file_id"],
            "voice.ogg",
            "🎙️ Голосовое сообщение"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "voice отправлен"
            )

        return

    # ========================================================
    # VIDEO NOTE
    # ========================================================

    if message.get("video_note"):

        video_note = message[
            "video_note"
        ]

        success = await send_file_to_discord(
            video_note["file_id"],
            "video_note.mp4",
            "🎥 Видеосообщение"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "video note отправлен"
            )

        return

    # ========================================================
    # DOCUMENT
    # ========================================================

    if message.get("document"):

        document = message[
            "document"
        ]

        success = await send_file_to_discord(
            document["file_id"],
            document.get("file_name")
            or "file"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "документ отправлен"
            )

        return

    # ========================================================
    # STICKER
    # ========================================================

    if message.get("sticker"):

        sticker = message[
            "sticker"
        ]

        sticker_name = "sticker.webp"

        if sticker.get("is_animated"):

            sticker_name = (
                "sticker.tgs"
            )

        elif sticker.get("is_video"):

            sticker_name = (
                "sticker.webm"
            )

        success = await send_file_to_discord(
            sticker["file_id"],
            sticker_name,
            "🎨 Стикер"
        )

        if success:

            print(
                "✅ Telegram → Discord "
                "стикер отправлен"
            )

        return

    # ========================================================
    # КОНТАКТ
    # ========================================================

    if message.get("contact"):

        contact = message[
            "contact"
        ]

        first_name = (
            contact.get("first_name")
            or ""
        )

        last_name = (
            contact.get("last_name")
            or ""
        )

        phone = (
            contact.get("phone_number")
            or "Не указан"
        )

        await channel.send(
            f"👤 **{username}**\n"
            f"📇 Контакт: "
            f"{first_name} {last_name}\n"
            f"📞 {phone}"
        )

        print(
            "✅ Telegram → Discord "
            "контакт отправлен"
        )

        return

    # ========================================================
    # LOCATION
    # ========================================================

    if message.get("location"):

        location = message[
            "location"
        ]

        latitude = location.get(
            "latitude"
        )

        longitude = location.get(
            "longitude"
        )

        await channel.send(
            f"👤 **{username}**\n"
            f"📍 Геолокация:\n"
            f"{latitude}, {longitude}\n"
            f"https://maps.google.com/"
            f"?q={latitude},{longitude}"
        )

        print(
            "✅ Telegram → Discord "
            "геолокация отправлена"
        )

        return

    # ========================================================
    # VENUE
    # ========================================================

    if message.get("venue"):

        venue = message[
            "venue"
        ]

        title = (
            venue.get("title")
            or "Место"
        )

        address = (
            venue.get("address")
            or "Адрес не указан"
        )

        await channel.send(
            f"👤 **{username}**\n"
            f"📍 **{title}**\n"
            f"{address}"
        )

        print(
            "✅ Telegram → Discord "
            "место отправлено"
        )

        return

    # ========================================================
    # ПЛАТЕЖ / ДРУГИЕ ТИПЫ
    # ========================================================

    print(
        "⚠️ Telegram сообщение "
        "не содержит поддерживаемого media-типа"
    )


# ============================================================
# TELEGRAM POLLING
# ============================================================

async def telegram_polling():

    global telegram_bot_id
    global telegram_offset

    print(
        "🔄 Запускаю Telegram bridge..."
    )

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN не указан "
            "в .env"
        )

        return

    # ========================================================
    # GET ME
    # ========================================================

    me = await telegram_api(
        "getMe"
    )

    if (
        not me
        or not me.get("ok")
    ):

        print(
            "❌ Telegram бот "
            "не подключился"
        )

        return

    telegram_bot_id = (
        me["result"]["id"]
    )

    print(
        f"✅ Telegram бот подключен: "
        f"@{me['result'].get('username', 'unknown')}"
    )

    # ========================================================
    # WEBHOOK
    # ========================================================

    webhook = await telegram_api(
        "getWebhookInfo"
    )

    if (
        webhook
        and webhook.get("ok")
    ):

        webhook_url = (
            webhook["result"].get(
                "url",
                ""
            )
        )

        if webhook_url:

            print(
                "⚠️ У Telegram "
                f"установлен webhook: "
                f"{webhook_url}"
            )

            delete_webhook = (
                await telegram_api(
                    "deleteWebhook",
                    {
                        "drop_pending_updates":
                            "false"
                    }
                )
            )

            if (
                delete_webhook
                and delete_webhook.get("ok")
            ):

                print(
                    "✅ Webhook удалён"
                )

            else:

                print(
                    "❌ Не удалось "
                    "удалить webhook"
                )

        else:

            print(
                "✅ Webhook не установлен"
            )

    # ========================================================
    # НАСТРОЙКИ
    # ========================================================

    print(
        f"🎯 Telegram Chat ID: "
        f"{TELEGRAM_CHAT_ID}"
    )

    print(
        f"🎯 Discord #общение: "
        f"{DISCORD_CHAT_CHANNEL_ID}"
    )

    print(
        f"🎯 Discord #тг: "
        f"{DISCORD_TG_CHANNEL_ID}"
    )

    print(
        "📡 Telegram bridge "
        "ожидает сообщения..."
    )

    # ========================================================
    # ОСНОВНОЙ ЦИКЛ
    # ========================================================

    while True:

        try:

            result = await telegram_api(
                "getUpdates",
                {
                    "offset":
                        telegram_offset,

                    "timeout":
                        30,

                    "allowed_updates":
                        '["message"]'
                }
            )

            if not result:

                await asyncio.sleep(
                    3
                )

                continue

            if not result.get("ok"):

                print(
                    "❌ Telegram "
                    f"getUpdates ошибка: "
                    f"{result}"
                )

                await asyncio.sleep(
                    5
                )

                continue

            updates = result.get(
                "result",
                []
            )

            for update in updates:

                print(
                    "📩 TELEGRAM UPDATE:",
                    update
                )

                telegram_offset = (
                    update["update_id"]
                    + 1
                )

                message = update.get(
                    "message"
                )

                if not message:

                    continue

                # =================================================
                # CHAT
                # =================================================

                chat = message.get(
                    "chat",
                    {}
                )

                chat_id = str(
                    chat.get(
                        "id",
                        ""
                    )
                )

                chat_title = (
                    chat.get("title")
                    or chat.get("username")
                    or chat.get("first_name")
                    or "Без названия"
                )

                print(
                    f"💬 Telegram чат: "
                    f"{chat_title}"
                )

                print(
                    f"🆔 Telegram Chat ID: "
                    f"{chat_id}"
                )

                # =================================================
                # CHAT ID
                # =================================================

                if (
                    TELEGRAM_CHAT_ID
                    and TELEGRAM_CHAT_ID
                    != "0"
                    and chat_id
                    != TELEGRAM_CHAT_ID
                ):

                    print(
                        "⚠️ Это другой "
                        "Telegram чат"
                    )

                    continue

                # =================================================
                # ОТПРАВИТЕЛЬ
                # =================================================

                sender = message.get(
                    "from"
                )

                if not sender:

                    print(
                        "⚠️ Не удалось "
                        "определить отправителя"
                    )

                    continue

                sender_id = sender.get(
                    "id"
                )

                if (
                    sender_id
                    == telegram_bot_id
                ):

                    continue

                username = (
                    sender.get(
                        "username"
                    )
                    or sender.get(
                        "first_name"
                    )
                    or "Пользователь"
                )

                # =================================================
                # DISCORD CHANNEL
                # =================================================

                try:

                    channel = bot.get_channel(
                        int(
                            DISCORD_TG_CHANNEL_ID
                        )
                    )

                except Exception as e:

                    print(
                        "❌ Ошибка получения "
                        f"Discord канала: {e}"
                    )

                    continue

                if channel is None:

                    print(
                        "❌ Discord канал "
                        "#тг не найден"
                    )

                    continue

                # =================================================
                # TEXT
                # =================================================

                text = message.get(
                    "text"
                )

                if text:

                    discord_text = (
                        f"👤 **{username}**: "
                        f"{text}"
                    )

                    parts = split_message(
                        discord_text,
                        1900
                    )

                    for part in parts:

                        try:

                            await channel.send(
                                part
                            )

                            print(
                                "✅ Telegram → "
                                "Discord текст"
                            )

                        except Exception as e:

                            print(
                                "❌ Ошибка "
                                f"отправки текста: {e}"
                            )

                    continue

                # =================================================
                # MEDIA
                # =================================================

                try:

                    await send_telegram_media_to_discord(
                        channel,
                        message,
                        username
                    )

                except Exception as e:

                    print(
                        "❌ Ошибка обработки "
                        f"Telegram media: {e}"
                    )

        except asyncio.CancelledError:

            print(
                "🛑 Telegram bridge "
                "остановлен"
            )

            break

        except Exception as e:

            print(
                "❌ Ошибка Telegram "
                f"polling: {e}"
            )

            await asyncio.sleep(
                5
            )


# ============================================================
# ЗАПУСК TELEGRAM BRIDGE
# ============================================================

async def start_telegram_bridge():

    global telegram_task

    if (
        telegram_task is not None
        and not telegram_task.done()
    ):

        print(
            "⚠️ Telegram bridge "
            "уже запущен"
        )

        return

    telegram_task = (
        asyncio.create_task(
            telegram_polling()
        )
    )

    print(
        "🌉 Telegram ↔ Discord "
        "bridge запущен"
    )
# ====== База данных ======
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS xp (
    user_id INTEGER,
    guild_id INTEGER,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    messages INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS server_stats (
    guild_id INTEGER,
    week_messages INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id)
)
""")
conn.commit()

# ====== Интенты ======
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree




# ====== Утилита defer ======
async def defer_thinking(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except:
        pass

# ====== XP, статистика и Discord → Telegram ======

@bot.event
async def on_message(message):

    # Не обрабатываем сообщения ботов
    if message.author.bot:
        return

    # ============================================================
    # DISCORD #общение → TELEGRAM
    # ============================================================

    if (
        message.guild
        and str(message.channel.id) == DISCORD_CHAT_CHANNEL_ID
    ):

        text = message.content.strip()

        username = (
            message.author.display_name
            or message.author.name
            or "Пользователь"
        )

        # Отправляем в Telegram:
        # - текст
        # - картинки
        # - видео
        # - файлы
        # - аудио
        # и другие Discord-вложения

        if text or message.attachments:

            try:

                await send_to_telegram(
                    text=text,
                    attachments=message.attachments,
                    username=username
                )

                print(
                    f"✅ Discord → Telegram: "
                    f"{username}"
                )

            except Exception as e:

                print(
                    f"❌ Ошибка Discord → Telegram: "
                    f"{e}"
                )

    # ============================================================
    # ДАЛЬШЕ — XP И СТАТИСТИКА
    # ============================================================

    if not message.guild:
        return

    uid = message.author.id
    gid = message.guild.id

    # ============================================================
    # ПОЛУЧАЕМ XP
    # ============================================================

    cursor.execute(
        "SELECT xp, level, messages "
        "FROM xp "
        "WHERE user_id=? AND guild_id=?",
        (uid, gid)
    )

    row = cursor.fetchone()

    if row is None:

        cursor.execute(
            "INSERT INTO xp("
            "user_id, guild_id, xp, level, messages"
            ") VALUES (?, ?, ?, ?, ?)",
            (
                uid,
                gid,
                0,
                1,
                0
            )
        )

        xp = 0
        lvl = 1
        msgs = 0

    else:

        xp, lvl, msgs = row

    # ============================================================
    # ДОБАВЛЯЕМ АКТИВНОСТЬ
    # ============================================================

    msgs += 1
    xp += 5

    # ============================================================
    # LEVEL UP
    # ============================================================

    if xp >= lvl * 100:

        lvl += 1
        xp = 0

        # Сообщение о повышении уровня отключено
        # чтобы бот не спамил в чат.

    # ============================================================
    # СОХРАНЯЕМ XP
    # ============================================================

    cursor.execute(
        "UPDATE xp "
        "SET xp=?, level=?, messages=? "
        "WHERE user_id=? AND guild_id=?",
        (
            xp,
            lvl,
            msgs,
            uid,
            gid
        )
    )

    # ============================================================
    # СТАТИСТИКА СЕРВЕРА
    # ============================================================

    cursor.execute(
        "SELECT week_messages "
        "FROM server_stats "
        "WHERE guild_id=?",
        (gid,)
    )

    s = cursor.fetchone()

    if s is None:

        cursor.execute(
            "INSERT INTO server_stats("
            "guild_id, week_messages"
            ") VALUES (?, ?)",
            (
                gid,
                1
            )
        )

    else:

        cursor.execute(
            "UPDATE server_stats "
            "SET week_messages = "
            "week_messages + 1 "
            "WHERE guild_id=?",
            (gid,)
        )

    # ============================================================
    # СОХРАНЯЕМ БАЗУ
    # ============================================================

    conn.commit()

    # ============================================================
    # ОБЯЗАТЕЛЬНО ОБРАБАТЫВАЕМ КОМАНДЫ
    # ============================================================

    await bot.process_commands(message)


# ====== Остальные команды ======
@tree.command(name="rank", description="Показать ваш уровень и XP на сервере.")
async def rang(interaction: discord.Interaction):
    await defer_thinking(interaction)
    uid = interaction.user.id
    gid = interaction.guild.id
    cursor.execute("SELECT xp, level, messages FROM xp WHERE user_id=? AND guild_id=?", (uid, gid))
    row = cursor.fetchone()
    xp, lvl, msgs = (row if row else (0,1,0))
    embed = discord.Embed(title=f"🏆 Уровень {interaction.user.name}", color=0x9b59b6)
    embed.add_field(name="Уровень", value=lvl)
    embed.add_field(name="XP", value=xp)
    embed.add_field(name="Сообщений", value=msgs)
    await interaction.followup.send(embed=embed)

@tree.command(name="avatar", description="Показать аватар участника.")
async def avatar_cmd(interaction: discord.Interaction, member: discord.Member = None):
    await defer_thinking(interaction)
    member = member or interaction.user
    embed = discord.Embed(title=f"Аватар {member.name}", color=0x9b59b6)
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id}")
    await interaction.followup.send(embed=embed)

@tree.command(name="stats", description="Статистика сервера и топ активных участников.")
async def stats(interaction: discord.Interaction):
    await defer_thinking(interaction)
    gid = interaction.guild.id
    cursor.execute("SELECT week_messages FROM server_stats WHERE guild_id=?", (gid,))
    week = cursor.fetchone()
    week_count = week[0] if week else 0
    cursor.execute("SELECT user_id, messages FROM xp WHERE guild_id=? ORDER BY messages DESC LIMIT 1", (gid,))
    top = cursor.fetchone()
    line = "Нет данных по активности."
    if top:
        top_member = interaction.guild.get_member(top[0])
        if top_member:
            line = f"😳 {top_member.mention} реально активный игрок!"
    embed = discord.Embed(title="📊 Статистика сервера", color=0x9b59b6)
    embed.add_field(name="Сообщений за неделю", value=week_count)
    embed.add_field(name="Топ участник", value=line, inline=False)
    await interaction.followup.send(embed=embed)

@tree.command(name="userinfo", description="Информация об участнике сервера.")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    await defer_thinking(interaction)
    member = member or interaction.user
    embed = discord.Embed(title=f"Информация о {member.name}", color=0x9b59b6)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Присоединился", value=member.joined_at.strftime("%d.%m.%Y"), inline=True)
    embed.add_field(name="Создан", value=member.created_at.strftime("%d.%m.%Y"), inline=True)
    await interaction.followup.send(embed=embed)

@tree.command(name="purge", description="Удалить указанное количество сообщений (максимум 100).")
async def purge(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ У тебя нет прав на удаление сообщений.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    amount = min(amount, 100)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        try: await interaction.followup.send(f"✅ Удалено {len(deleted)} сообщений.", ephemeral=True)
        except: pass
    except Exception as e:
        try: await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)
        except: pass

# ============================
#       ПОЛЕЗНЫЕ КОМАНДЫ
# ============================


@tree.command(name="serverinfo", description="Информация о сервере.")
async def serverinfo(interaction: discord.Interaction):
    await defer_thinking(interaction)
    guild = interaction.guild
    embed = discord.Embed(title=f"Информация о {guild.name}", color=0x9b59b6)
    embed.add_field(name="ID", value=guild.id)
    embed.add_field(name="Участников", value=guild.member_count)
    embed.add_field(name="Каналов", value=len(guild.channels))
    embed.add_field(name="Ролей", value=len(guild.roles))
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.followup.send(embed=embed)

@tree.command(name="roleinfo", description="Информация о роли.")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    await defer_thinking(interaction)
    members = [m.mention for m in role.members][:10]
    member_list = ", ".join(members) + ("..." if len(role.members) > 10 else "")
    embed = discord.Embed(title=f"Информация о роли {role.name}", color=role.color)
    embed.add_field(name="ID", value=role.id)
    embed.add_field(name="Цвет", value=str(role.color))
    embed.add_field(name="Участники", value=member_list or "Нет участников", inline=False)
    embed.add_field(name="Позиция", value=role.position)
    await interaction.followup.send(embed=embed)


@tree.command(name="remind", description="Напоминание через указанное время.")
async def remind(interaction: discord.Interaction, time: int, *, message: str):
    await defer_thinking(interaction)
    await interaction.followup.send(f"⏳ Напоминание установлено на {time} секунд.")
    await asyncio.sleep(time)
    await interaction.followup.send(f"🔔 Напоминание: {message}")



# ====== AGPG мем ======




import time
AGPG_ADMIN_ID = int(os.getenv("AGPG_ADMIN_ID", "0"))

AGPG_MEMES = [
    "Нитфейк и элго",
    "Обижака и мусоровоз",
    "Чесатель носа",
    "Чзх плановый скрин",
    "Парни вупса",
    "Булка в ориг шмотках",
    "Стрибиж занюхнул кофточку",
    "Стрибиж и рынок",
    "Миксер спалил лицо",
    "Нитфейк и миксер обсуждают финал джо джо",
    "Обзор еды нитфейка",
    "Нитфейк и Скворцов",
    "Газ на летней сходке",
    "DUUUDEEE",
    "Мемы про нитфейка (55, печеньки с молоком, расписание, томас шелби)",
    "аозл нуазкй пидорасм (первый мем на AGPG)",
    "Шептун риса",
    "Ебатель лаки",
    "Понос блеванул на стул",
    "Понос и подкаты к вупсу",
    "Понос vs Филечка",
    "Фристи и житель",
    "Рис и истребители",
    "Электрон и подвал",
    "Превращение в диксона",
    "Имран",
    "Инсайд от нитфейка",
    "Шаман и быстрый бег на рнг",
    "Плотная на сходке",
    "ЧЗХЕШЕЧКА",
    "Люто",
    "Запретсиянин фристи",
    "Виттит спиздил акк",
    "Чзх плановый рейд",
    "Деанон от парней вупса",
    "Деанон от петухов виттита",
    "Кай на пк сходке",
    "ЧЗХ",
    "Люто/лютый",
    "Дрист",
    "Жиденький",
    "Фирменный",
    "Фармилкин",
    "Арбузик",
    "Медведь",
    "Обижака",
    "Быдлан",
    "Тупа",
    "DUDE",
    "Диксон",
    "Голливуд",
    "Лампово",
    "Высер",
    "Прострел базы кронусом",
    "Спортсмены",
    "Люксовый вертолет",
    "Гм авенджер суприма",
    "Внедрение в тусу с огурчика",
    "Орбанье подсосов виттита",
    "Чистка лица",
    "Эмблема с виттитом (я хуесос)",
    "Детонатор на сходке",
    "Пранк ксенона на 1 апреля",
    "Суприм флексит единственным киллом с орбиты",
    "Союз юмористов",
    "Юечка моя",
    "Пазор нато",
    "hi sniper battle",
    "explain 45-15",
    "Дамир бро агент",
    "А фанчика можно убивать?",
    "Чувствую",
    "Тупа мы",
    "Хабибно",
    "англицизм говоришь",
    "Проект ориджинал пидорс 2023-2024",
    "Гамблинг и Славя",
    "Лаки вступает в ориджинал пидорс",
    "ЗАШЕЛ К БОССУ БАГ С КРОВАТЬЮ",
    "Босс и акк джоки койн",
    "Гта 6 и его парень оогих",
    "Парни вупса хотели задоксить ксенона, но скинули машину которую продали 11 лет назад и окно соседей.",
    "Damir_bro1027 несокрушимый игрок гта онлайн передоил всех нубхардов в игре"
]

BRIGADE_COOLDOWN = 300  # 5 минут
last_brigade_call = 0

class AGPGView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🚨 Вызвать бригаду",
        style=discord.ButtonStyle.danger,
        custom_id="call_brigade_button"
    )
    async def call_brigade(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        print("Кнопка нажата!")

        global last_brigade_call

        now = time.time()
        remaining = BRIGADE_COOLDOWN - (now - last_brigade_call)

        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)

            await interaction.response.send_message(
                f"⏳ Бригаду можно вызывать раз в 5 минут.\n"
                f"Попробуй через {minutes} мин {seconds} сек.",
                ephemeral=True
            )
            return

        last_brigade_call = now

        await interaction.response.send_message(
            f"🚨 БРИГАДА ВЫЗВАНА! <@{AGPG_ADMIN_ID}>",
            allowed_mentions=discord.AllowedMentions(users=True)
        )




@tree.command(
    name="agpg",
    description="Вызвать рандомный мем AGPG"
)
async def agpg(interaction: discord.Interaction):
    import random
    await defer_thinking(interaction)

    meme = random.choice(AGPG_MEMES)

    embed = discord.Embed(
        title="🧠 AGPG МЕМ",
        description=f"**{meme}**",
        color=0x9b59b6
    )
    embed.set_footer(text="MAKE AGPG GREAT AGAIN")

    await interaction.followup.send(
        embed=embed,
        view=AGPGView()
    )



# ============================
#       РАЗВЛЕКАТЕЛЬНЫЕ
# ============================

@tree.command(name="meme", description="Случайный мем с Reddit.")
async def meme(interaction: discord.Interaction):
    await defer_thinking(interaction)
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://meme-api.com/gimme") as r:
                data = await r.json()
        embed = discord.Embed(title=data.get("title", "Мем"), color=0x9b59b6)
        embed.set_image(url=data.get("url"))
        await interaction.followup.send(embed=embed)
    except Exception:
        await interaction.followup.send("❌ Не удалось загрузить мем. Попробуйте позже.")

@tree.command(name="cat", description="Случайная картинка кота.")
async def cat(interaction: discord.Interaction):
    await defer_thinking(interaction)
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://cataas.com/cat?json=true", timeout=5) as r:
                data = await r.json()

        # URL из JSON иногда уже полный, проверяем
        url = data.get("url", "")
        if url.startswith("http"):
            final_url = url
        else:
            final_url = "https://cataas.com" + url

        await interaction.followup.send(final_url)
    except Exception:
        await interaction.followup.send("❌ Не удалось загрузить картинку кота. Попробуйте позже.")

@tree.command(name="dog", description="Случайная картинка собаки.")
async def dog(interaction: discord.Interaction):
    await defer_thinking(interaction)
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://dog.ceo/api/breeds/image/random", timeout=5) as r:
                data = await r.json()
        await interaction.followup.send(data.get("message"))
    except Exception:
        await interaction.followup.send("❌ Не удалось загрузить картинку собаки. Попробуйте позже.")


@tree.command(name="fact", description="Случайный факт на русском.")
async def fact(interaction: discord.Interaction):
    await defer_thinking(interaction)
    import aiohttp, random
    try:
        facts = [
            "Слон — единственное животное, которое не может прыгать.",
            "Сердце синего кита размером с маленькую машину.",
            "Медузы существуют более 500 миллионов лет.",
            "На Венере день длиннее года.",
            "Карандаш можно использовать для измерения высоты здания (приблизительно)."
        ]
        await interaction.followup.send(f"ℹ️ {random.choice(facts)}")
    except Exception:
        await interaction.followup.send("❌ Не удалось получить факт. Попробуйте позже.")

# ============================
#       МИНИ-ИГРЫ
# ============================

@tree.command(name="guessnumber", description="Угадай число от 1 до 100.")
async def guessnumber(interaction: discord.Interaction):
    import random
    await defer_thinking(interaction)
    number = random.randint(1,100)
    await interaction.followup.send("Я загадал число от 1 до 100. Напишите его в чат!")

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel
    for _ in range(10):
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            guess = int(msg.content)
            if guess == number:
                await interaction.followup.send(f"🎉 Верно! Это число {number}")
                return
            elif guess < number:
                await interaction.followup.send("🔼 Больше!")
            else:
                await interaction.followup.send("🔽 Меньше!")
        except Exception:
            continue
    await interaction.followup.send(f"❌ Время вышло! Я загадал число {number}")

@tree.command(name="help", description="Интерактивная справка по командам.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📘 Справка по командам",
        description="Выберите категорию при помощи кнопок ниже.",
        color=0x9b59b6
    )
    await interaction.response.send_message(
        embed=embed,
        view=HelpView(),
        ephemeral=True
    )
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    async def send_category(self, interaction, title, description):
        embed = discord.Embed(title=title, description=description, color=0x9b59b6)
        await interaction.response.edit_message(embed=embed, view=self)


    @discord.ui.button(label="📊 Уровни", style=discord.ButtonStyle.primary)
    async def xp(self, interaction, button):
        await self.send_category(
            interaction,
            "📊 Уровни и активность",
            (
                "**/rank** — ваш уровень, XP и сообщения.\n"
                "**/stats** — статистика сервера и самый активный участник."
            )
        )

    @discord.ui.button(label="👤 Инфо", style=discord.ButtonStyle.primary)
    async def info(self, interaction, button):
        await self.send_category(
            interaction,
            "👤 Информационные команды",
            (
                "**/userinfo [участник]** — информация о пользователе.\n"
                "**/avatar [участник]** — аватар.\n"
                "**/serverinfo** — информация о сервере.\n"
                "**/roleinfo <роль>** — информация о роли."
            )
        )

    @discord.ui.button(label="🛠 Модерация", style=discord.ButtonStyle.danger)
    async def moderation(self, interaction, button):
        await self.send_category(
            interaction,
            "🛠 Модераторские команды",
            (
                "**/purge <число>** — удалить сообщения (до 100)."
            )
        )

    @discord.ui.button(label="🎉 Развлечения", style=discord.ButtonStyle.success)
    async def fun(self, interaction, button):
        await self.send_category(
            interaction,
            "🎉 Развлекательные команды",
            (
                "**/meme** — случайный мем.\n"
                "**/cat** — кот.\n"
                "**/dog** — собака.\n"
                "**/fact** — интересный факт.\n"
                "**/agpg ** — Рандомный мем AGPG."
            )
        )

    @discord.ui.button(label="🎮 Игры", style=discord.ButtonStyle.success)
    async def games(self, interaction, button):
        await self.send_category(
            interaction,
            "🎮 Мини-игры",
            (
                "**/guessnumber** — угадай число от 1 до 100."
            )
        )

    @discord.ui.button(label="⏰ Полезное", style=discord.ButtonStyle.secondary)
    async def utility(self, interaction, button):
        await self.send_category(
            interaction,
            "⏰ Полезные команды",
            (
                "**/remind <сек> <текст>** — напоминание."
            )
        )


@bot.event
async def on_ready():

    print(f"🤖 Бот запущен как {bot.user}")

    # ============================================================
    # SLASH-КОМАНДЫ
    # ============================================================

    try:
        synced = await tree.sync()

        print(
            f"✅ Синхронизировано slash-команд: {len(synced)}"
        )

    except Exception as e:
        print(
            f"❌ Ошибка синхронизации slash-команд: {e}"
        )

    # ============================================================
    # СТАТУС БОТА
    # ============================================================

    activity = discord.Activity(
        type=discord.ActivityType.playing,
        name="Пишется на Melon Music"
    )

    await bot.change_presence(
        status=discord.Status.online,
        activity=activity
    )

    # ============================================================
    # AGPG PERSISTENT VIEW
    # ============================================================

    try:
        bot.add_view(AGPGView())

        print("✅ AGPGView зарегистрирован")

    except Exception as e:
        print(
            f"❌ Ошибка регистрации AGPGView: {e}"
        )

    # ============================================================
    # ПРОВЕРКА КАНАЛОВ DISCORD
    # ============================================================

    try:
        chat_channel = bot.get_channel(
            int(DISCORD_CHAT_CHANNEL_ID)
        )

        tg_channel = bot.get_channel(
            int(DISCORD_TG_CHANNEL_ID)
        )

        if chat_channel:
            print(
                f"✅ #общение найден: "
                f"{chat_channel.name}"
            )
        else:
            print(
                "❌ #общение не найден. "
                "Проверь DISCORD_CHAT_CHANNEL_ID"
            )

        if tg_channel:
            print(
                f"✅ #тг найден: "
                f"{tg_channel.name}"
            )
        else:
            print(
                "❌ #тг не найден. "
                "Проверь DISCORD_TG_CHANNEL_ID"
            )

    except Exception as e:
        print(
            f"❌ Ошибка проверки Discord-каналов: {e}"
        )

    # ============================================================
    # TELEGRAM BRIDGE
    # ============================================================

    if TELEGRAM_TOKEN:

        try:
            await start_telegram_bridge()

            print(
                "🌉 Telegram ↔ Discord bridge запущен"
            )

        except Exception as e:
            print(
                f"❌ Ошибка запуска Telegram bridge: {e}"
            )

    else:
        print(
            "⚠️ TELEGRAM_TOKEN не указан. "
            "Telegram bridge отключён."
        )

    print("🚀 Бот полностью готов!")


bot.run(TOKEN)

