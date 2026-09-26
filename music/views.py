from __future__ import annotations

import discord

from .utils import (
    format_track_duration,
    get_loop_emoji,
    get_loop_name,
    get_source_emoji,
    get_source_name,
    get_player_status,
    make_volume_bar,
    shorten_title,
)


MUSIC_COLOR = discord.Color.blurple()


# ============================================================
# PLAYER EMBED
# ============================================================

def build_player_embed(player) -> discord.Embed:

    embed = discord.Embed(
        title="🎵 Music Player",
        color=MUSIC_COLOR,
    )

    track = player.current

    # --------------------------------------------------------
    # NOTHING PLAYING
    # --------------------------------------------------------

    if not track:

        embed.description = (
            "```"
            "🎧  Сейчас ничего не играет\n"
            "```\n"
            "Добавь трек командой **/play**"
        )

        embed.add_field(
            name="📋 Очередь",
            value=(
                f"`{len(player.queue)}` трек(ов)"
                if player.queue
                else "`Пусто`"
            ),
            inline=True,
        )

        embed.add_field(
            name="🔊 Громкость",
            value=make_volume_bar(player.volume),
            inline=True,
        )

        embed.add_field(
            name="🔁 Повтор",
            value=(
                f"{get_loop_emoji(player.loop_mode)} "
                f"{get_loop_name(player.loop_mode)}"
            ),
            inline=True,
        )

        embed.set_footer(
            text="YouTube • SoundCloud • Music Player"
        )

        return embed

    # --------------------------------------------------------
    # TRACK
    # --------------------------------------------------------

    title = shorten_title(
        track.title,
        100,
    )

    source_name = get_source_name(track)

    source_emoji = get_source_emoji(track)

    duration = format_track_duration(
        track.duration
    )

    status = get_player_status(
        player
    )

    embed.description = (
        f"### {title}\n"
        f"{source_emoji} **{source_name}**"
        f"  •  `⏱ {duration}`\n\n"
        f"{status}"
    )

    # --------------------------------------------------------
    # THUMBNAIL
    # --------------------------------------------------------

    if track.thumbnail:

        try:
            embed.set_thumbnail(
                url=track.thumbnail
            )
        except Exception:
            pass

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

    embed.add_field(
        name="👤 Исполнитель",
        value=shorten_title(
            track.uploader or "Неизвестно",
            100,
        ),
        inline=True,
    )

    # --------------------------------------------------------
    # QUEUE
    # --------------------------------------------------------

    queue_count = len(player.queue)

    if queue_count == 0:
        queue_text = "`Пусто`"

    elif queue_count == 1:
        queue_text = "`1` трек"

    else:
        queue_text = f"`{queue_count}` трек(ов)"

    embed.add_field(
        name="📋 В очереди",
        value=queue_text,
        inline=True,
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    embed.add_field(
        name="🔊 Громкость",
        value=make_volume_bar(
            player.volume
        ),
        inline=False,
    )

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    embed.add_field(
        name="🔁 Повтор",
        value=(
            f"{get_loop_emoji(player.loop_mode)} "
            f"{get_loop_name(player.loop_mode)}"
        ),
        inline=True,
    )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    embed.set_footer(
        text="YouTube • SoundCloud • Music Player"
    )

    return embed


# ============================================================
# MUSIC CONTROL VIEW
# ============================================================

class MusicControlView(discord.ui.View):

    def __init__(
        self,
        player,
        timeout: float | None = None,
    ):
        super().__init__(
            timeout=timeout
        )

        self.player = player

    # ========================================================
    # REFRESH PANEL
    # ========================================================

    async def refresh_panel(
        self,
        interaction: discord.Interaction,
    ):

        embed = build_player_embed(
            self.player
        )

        # Если interaction ещё не обработан —
        # редактируем исходное сообщение напрямую.
        if not interaction.response.is_done():

            try:

                await interaction.response.edit_message(
                    embed=embed,
                    view=self,
                )

                return

            except discord.HTTPException:
                pass

        # Если interaction уже был defer().
        if interaction.message:

            try:

                await interaction.message.edit(
                    embed=embed,
                    view=self,
                )

            except discord.NotFound:
                pass

            except discord.Forbidden:
                pass

            except discord.HTTPException:
                pass

    async def update_message(
        self,
        interaction: discord.Interaction,
    ):

        await self.refresh_panel(
            interaction
        )

    # ========================================================
    # PAUSE / RESUME
    # ========================================================

    @discord.ui.button(
        emoji="⏯️",
        style=discord.ButtonStyle.primary,
        custom_id="music_pause_resume",
        row=0,
    )
    async def pause_resume(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        player = self.player

        if player.is_paused():

            if player.resume():

                await self.refresh_panel(
                    interaction
                )

                return

        elif player.is_currently_playing():

            if player.pause():

                await self.refresh_panel(
                    interaction
                )

                return

        await interaction.response.send_message(
            "❌ Сейчас ничего не играет.",
            ephemeral=True,
        )

    # ========================================================
    # SKIP
    # ========================================================

    @discord.ui.button(
        emoji="⏭️",
        style=discord.ButtonStyle.secondary,
        custom_id="music_skip",
        row=0,
    )
    async def skip(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        success = await self.player.skip()

        if not success:

            await interaction.response.send_message(
                "❌ Сейчас нечего пропускать.",
                ephemeral=True,
            )

            return

        await interaction.response.defer()

        await self.player.update_message()

    # ========================================================
    # SHUFFLE
    # ========================================================

    @discord.ui.button(
        emoji="🔀",
        style=discord.ButtonStyle.secondary,
        custom_id="music_shuffle",
        row=0,
    )
    async def shuffle(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if len(self.player.queue) < 2:

            await interaction.response.send_message(
                "❌ В очереди недостаточно треков.",
                ephemeral=True,
            )

            return

        self.player.shuffle()

        await self.refresh_panel(
            interaction
        )

    # ========================================================
    # LOOP
    # ========================================================

    @discord.ui.button(
        emoji="🔁",
        style=discord.ButtonStyle.secondary,
        custom_id="music_loop",
        row=0,
    )
    async def loop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        mode = self.player.cycle_loop()

        button.emoji = get_loop_emoji(
            mode
        )

        await self.refresh_panel(
            interaction
        )

    # ========================================================
    # STOP
    # ========================================================

    @discord.ui.button(
        emoji="⏹️",
        style=discord.ButtonStyle.danger,
        custom_id="music_stop",
        row=0,
    )
    async def stop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.player.stop()

        await self.refresh_panel(
            interaction
        )

    # ========================================================
    # VOLUME DOWN
    # ========================================================

    @discord.ui.button(
        emoji="🔉",
        style=discord.ButtonStyle.secondary,
        custom_id="music_volume_down",
        row=1,
    )
    async def volume_down(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        current = int(
            self.player.volume * 100
        )

        new_volume = max(
            0,
            current - 10,
        )

        self.player.set_volume(
            new_volume
        )

        await self.refresh_panel(
            interaction
        )

    # ========================================================
    # VOLUME UP
    # ========================================================

    @discord.ui.button(
        emoji="🔊",
        style=discord.ButtonStyle.secondary,
        custom_id="music_volume_up",
        row=1,
    )
    async def volume_up(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        current = int(
            self.player.volume * 100
        )

        new_volume = min(
            100,
            current + 10,
        )

        self.player.set_volume(
            new_volume
        )

        await self.refresh_panel(
            interaction
        )

    # ========================================================
    # QUEUE
    # ========================================================

    @discord.ui.button(
        emoji="📋",
        label="Очередь",
        style=discord.ButtonStyle.secondary,
        custom_id="music_queue",
        row=1,
    )
    async def queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        tracks = self.player.get_queue()

        if not tracks:

            await interaction.response.send_message(
                "📋 Очередь сейчас пуста.",
                ephemeral=True,
            )

            return

        lines = []

        for index, track in enumerate(
            tracks[:15],
            start=1,
        ):

            duration = format_track_duration(
                track.duration
            )

            title = shorten_title(
                track.title,
                45,
            )

            source_emoji = get_source_emoji(
                track
            )

            lines.append(
                f"`{index:02}` "
                f"{source_emoji} "
                f"**{title}** "
                f"`{duration}`"
            )

        embed = discord.Embed(
            title="📋 Music Queue",
            description="\n".join(lines),
            color=MUSIC_COLOR,
        )

        embed.add_field(
            name="🎵 В очереди",
            value=f"`{len(tracks)}`",
            inline=True,
        )

        if self.player.current:

            embed.add_field(
                name="▶️ Сейчас играет",
                value=shorten_title(
                    self.player.current.title,
                    45,
                ),
                inline=True,
            )

        if len(tracks) > 15:

            embed.set_footer(
                text=(
                    f"И ещё "
                    f"{len(tracks) - 15} трек(ов)"
                )
            )

        else:

            embed.set_footer(
                text="YouTube • SoundCloud"
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # ========================================================
    # DISCONNECT
    # ========================================================

    @discord.ui.button(
        emoji="🔌",
        label="Выйти",
        style=discord.ButtonStyle.danger,
        custom_id="music_disconnect",
        row=1,
    )
    async def disconnect(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.player.disconnect()

        # disconnect() уже обновил панель.
        await interaction.response.defer()