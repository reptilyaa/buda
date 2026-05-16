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

# ====== XP и статистика ======
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    uid = message.author.id
    gid = message.guild.id

    cursor.execute("SELECT xp, level, messages FROM xp WHERE user_id=? AND guild_id=?", (uid, gid))
    row = cursor.fetchone()

    if row is None:
        cursor.execute("INSERT INTO xp(user_id, guild_id, xp, level, messages) VALUES (?,?,?,?,?)", (uid, gid, 0, 1, 0))
        xp, lvl, msgs = 0, 1, 0
    else:
        xp, lvl, msgs = row

    msgs += 1
    xp += 5

    if xp >= lvl * 100:
        lvl += 1
        xp = 0
        # Удаляем отправку сообщения в чат
        # try:
        #     await message.channel.send(f"🔥 **{message.author.name} поднял уровень! Теперь {lvl}!**")
        # except:
        #     pass

    cursor.execute("UPDATE xp SET xp=?, level=?, messages=? WHERE user_id=? AND guild_id=?", (xp, lvl, msgs, uid, gid))

    cursor.execute("SELECT week_messages FROM server_stats WHERE guild_id=?", (gid,))
    s = cursor.fetchone()

    if s is None:
        cursor.execute("INSERT INTO server_stats(guild_id, week_messages) VALUES (?,?)", (gid, 1))
    else:
        cursor.execute("UPDATE server_stats SET week_messages = week_messages + 1 WHERE guild_id=?", (gid,))

    conn.commit()
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
    "Суприм флексит единственным киллом с орбиты"
]



class AGPGView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🚨 Вызвать бригаду",
        style=discord.ButtonStyle.danger
    )
    async def call_brigade(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        global last_brigade_call
        now = time.time()
        remaining = BRIGADE_COOLDOWN - (now - last_brigade_call)

        # Определяем, можно ли использовать response или followup
        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            try:
                await send_func(
                    f"⏳ **Бригаду можно вызывать раз в 5 минут.**\n"
                    f"Попробуй через **{minutes} мин {seconds} сек**.",
                    ephemeral=True
                )
            except Exception:
                pass
            return

        last_brigade_call = now
        try:
            await send_func(
                f"🚨 **БРИГАДА ВЫЗВАНА!** <@{AGPG_ADMIN_ID}>",
                allowed_mentions=discord.AllowedMentions(users=True)
            )
        except Exception:
            pass




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
    await tree.sync()

    activity = discord.Activity(
        type=discord.ActivityType.playing,
        name="Пишется на Melon Music"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    print(f"Бот запущен как {bot.user}")


bot.run(TOKEN)

