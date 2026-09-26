from __future__ import annotations

import asyncio
import random
import shlex
from collections import deque
from typing import Optional

import discord

from .sources import Track, get_track, refresh_track


class MusicPlayer:
    """
    Музыкальный плеер одного Discord-сервера.

    Отвечает за:
    - voice connection
    - очередь
    - текущий трек
    - FFmpeg
    - громкость
    - pause / resume
    - skip
    - stop
    - loop
    - обновление Music Panel
    """

    def __init__(
        self,
        bot: discord.Client,
        guild_id: int,
    ):
        self.bot = bot
        self.guild_id = guild_id

        # =====================================================
        # VOICE
        # =====================================================

        self.voice_client: Optional[discord.VoiceClient] = None

        # =====================================================
        # QUEUE
        # =====================================================

        self.queue: deque[Track] = deque()

        self.current: Optional[Track] = None

        # =====================================================
        # SETTINGS
        # =====================================================

        # 0.7 = 70%
        self.volume: float = 0.7

        # off / track / queue
        self.loop_mode: str = "off"

        # =====================================================
        # STATE
        # =====================================================

        self.is_playing: bool = False

        # =====================================================
        # MUSIC PANEL
        # =====================================================

        # Одно постоянное сообщение Music Player.
        self.message: Optional[discord.Message] = None

        # =====================================================
        # INTERNAL FLAGS
        # =====================================================

        self._play_lock = asyncio.Lock()

        self._skip_requested = False

        self._disconnect_requested = False

    # =========================================================
    # PLAYER MESSAGE
    # =========================================================

    async def update_message(self):
        """
        Обновляет существующую Music Panel.

        Важно:
        новое сообщение НЕ создаётся.

        Редактируется старое сообщение:
            self.message
        """

        if not self.message:
            return

        try:
            from .views import (
                MusicControlView,
                build_player_embed,
            )

            embed = build_player_embed(self)

            view = MusicControlView(self)

            await self.message.edit(
                embed=embed,
                view=view,
            )

        except discord.NotFound:
            # Сообщение удалили.
            self.message = None

        except discord.Forbidden as e:
            print(
                f"[MUSIC] Нет прав на обновление панели: {e}"
            )

        except discord.HTTPException as e:
            print(
                f"[MUSIC] Ошибка обновления панели: {e}"
            )

        except Exception as e:
            print(
                f"[MUSIC] Неожиданная ошибка панели: {e}"
            )

    # =========================================================
    # VOICE
    # =========================================================

    async def connect(
        self,
        channel: discord.VoiceChannel,
    ):
        """
        Подключиться к голосовому каналу.

        Если бот уже подключён:
        - остаётся в текущем канале;
        - либо перемещается в новый.
        """

        self._disconnect_requested = False

        # -----------------------------------------------------
        # Уже подключён
        # -----------------------------------------------------

        if (
            self.voice_client
            and self.voice_client.is_connected()
        ):
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)

            return self.voice_client

        # -----------------------------------------------------
        # Новое подключение
        # -----------------------------------------------------

        self.voice_client = await channel.connect(
            reconnect=True
        )

        return self.voice_client

    async def disconnect(self):
        """
        Полностью отключить плеер.
        После выхода старая Music Player панель удаляется.
        Следующий /play создаст новую панель.
        """

        self._disconnect_requested = True
        self._skip_requested = True

        # -----------------------------------------------------
        # Запоминаем старую панель
        # -----------------------------------------------------

        old_message = self.message

        # Сразу забываем старую панель
        self.message = None

        # -----------------------------------------------------
        # Останавливаем FFmpeg
        # -----------------------------------------------------

        if self.voice_client:

            try:

                if (
                        self.voice_client.is_playing()
                        or self.voice_client.is_paused()
                ):
                    self.voice_client.stop()

                await self.voice_client.disconnect(
                    force=True
                )

            except Exception as e:

                print(
                    f"[MUSIC] Ошибка disconnect: {e}"
                )

        # -----------------------------------------------------
        # Сбрасываем состояние
        # -----------------------------------------------------

        self.voice_client = None

        self.current = None

        self.queue.clear()

        self.is_playing = False

        # -----------------------------------------------------
        # Удаляем старую Music Player панель
        # -----------------------------------------------------

        if old_message:

            try:

                await old_message.delete()

                print(
                    "[MUSIC] Старая Music Player панель удалена."
                )

            except discord.NotFound:
                # Панель уже была удалена
                pass

            except discord.HTTPException as e:

                print(
                    f"[MUSIC] Не удалось удалить старую панель: {e}"
                )

        # -----------------------------------------------------
        # Сбрасываем состояние
        # -----------------------------------------------------

        self.current = None

        self.queue.clear()

        self.is_playing = False

        # -----------------------------------------------------
        # Обновляем панель
        # -----------------------------------------------------

        await self.update_message()

    # =========================================================
    # QUEUE
    # =========================================================

    def add_to_queue(
        self,
        track: Track,
    ):
        """
        Добавить трек в конец очереди.
        """

        self.queue.append(track)

    def add_to_front(
        self,
        track: Track,
    ):
        """
        Добавить трек в начало очереди.
        """

        self.queue.appendleft(track)

    def get_queue(self) -> list[Track]:
        """
        Вернуть копию очереди.

        Используется MusicControlView.
        """

        return list(self.queue)

    def clear_queue(self):
        """
        Полностью очистить очередь.
        """

        self.queue.clear()

    def shuffle_queue(self):
        """
        Перемешать очередь.
        """

        if len(self.queue) < 2:
            return

        items = list(self.queue)

        random.shuffle(items)

        self.queue = deque(items)

    def shuffle(self):
        """
        Совместимость с MusicControlView.

        Можно использовать:
            player.shuffle()
        """

        self.shuffle_queue()

    def queue_size(self) -> int:
        return len(self.queue)

    # =========================================================
    # PLAY NEXT
    # =========================================================

    async def play_next(self) -> bool:
        """
        Запустить следующий трек.

        True:
            трек успешно запущен.

        False:
            запуск не удался или очередь пуста.
        """

        async with self._play_lock:

            # -------------------------------------------------
            # DISCONNECT
            # -------------------------------------------------

            if self._disconnect_requested:
                return False

            # -------------------------------------------------
            # VOICE
            # -------------------------------------------------

            if not self.voice_client:
                return False

            if not self.voice_client.is_connected():
                return False

            # -------------------------------------------------
            # Уже играет
            # -------------------------------------------------

            if (
                self.voice_client.is_playing()
                or self.voice_client.is_paused()
            ):
                return False

            # -------------------------------------------------
            # SELECT TRACK
            # -------------------------------------------------

            if (
                self.loop_mode == "track"
                and self.current is not None
            ):
                track = self.current

            else:

                if not self.queue:

                    self.current = None
                    self.is_playing = False

                    # Обновляем панель.
                    await self.update_message()

                    return False

                track = self.queue.popleft()

            self._skip_requested = False

            # -------------------------------------------------
            # REFRESH URL
            # -------------------------------------------------

            try:

                fresh_track = await refresh_track(
                    track
                )

            except Exception as e:

                self.is_playing = False

                print(
                    "[MUSIC] Ошибка обновления трека "
                    f"'{track.title}': {e}"
                )

                # Если есть ещё треки,
                # пробуем следующий.
                if self.queue:

                    asyncio.create_task(
                        self._play_next_after_error()
                    )

                return False

            self.current = fresh_track

            print(
                "[MUSIC] Playing: "
                f"{fresh_track.title}"
            )

            # -------------------------------------------------
            # FFmpeg OPTIONS
            # -------------------------------------------------

            before_options = (
                "-reconnect 1 "
                "-reconnect_streamed 1 "
                "-reconnect_delay_max 5"
            )

            headers = (
                fresh_track.http_headers
                or {}
            )

            # -------------------------------------------------
            # HTTP HEADERS
            # -------------------------------------------------

            if headers:

                header_lines = []

                for key, value in headers.items():

                    if not key:
                        continue

                    if value is None:
                        continue

                    header_lines.append(
                        f"{key}: {value}"
                    )

                if header_lines:

                    header_blob = (
                        "\r\n".join(
                            header_lines
                        )
                        + "\r\n"
                    )

                    before_options += (
                        " -headers "
                        + shlex.quote(
                            header_blob
                        )
                    )

            # -------------------------------------------------
            # FFMPEG
            # -------------------------------------------------

            try:

                audio_source = (
                    discord.FFmpegPCMAudio(
                        fresh_track.url,

                        before_options=(
                            before_options
                        ),

                        options="-vn",
                    )
                )

                audio_source = (
                    discord.PCMVolumeTransformer(
                        audio_source,
                        volume=self.volume,
                    )
                )

                self.is_playing = True

                self.voice_client.play(
                    audio_source,
                    after=self._after_track,
                )

                # -------------------------------------------------
                # UPDATE PANEL
                # -------------------------------------------------

                await self.update_message()

                return True

            except Exception as e:

                self.is_playing = False

                print(
                    "[MUSIC] Ошибка запуска FFmpeg: "
                    f"{e}"
                )

                # Возвращаем текущий трек
                # в очередь, если он не был skip.
                if (
                    self.current is not None
                    and not self._skip_requested
                ):
                    self.queue.appendleft(
                        self.current
                    )

                self.current = None

                await self.update_message()

                if self.queue:

                    asyncio.create_task(
                        self._play_next_after_error()
                    )

                return False

    # =========================================================
    # PLAY NEXT AFTER ERROR
    # =========================================================

    async def _play_next_after_error(self):
        """
        Попытаться запустить следующий трек
        после ошибки.
        """

        await asyncio.sleep(1)

        if self._disconnect_requested:
            return

        if not self.voice_client:
            return

        if not self.voice_client.is_connected():
            return

        if (
            self.voice_client.is_playing()
            or self.voice_client.is_paused()
        ):
            return

        await self.play_next()

    # =========================================================
    # AFTER TRACK
    # =========================================================

    def _after_track(
        self,
        error: Optional[Exception],
    ):
        """
        Callback discord.py.

        Важно:
        этот callback может выполняться
        не внутри asyncio event loop.
        """

        if error:

            print(
                "[MUSIC] FFmpeg error: "
                f"{error}"
            )

        try:

            asyncio.run_coroutine_threadsafe(
                self._handle_after_track(),
                self.bot.loop,
            )

        except Exception as e:

            print(
                "[MUSIC] Ошибка after callback: "
                f"{e}"
            )

    async def _handle_after_track(self):
        """
        Обработка окончания трека.
        """

        self.is_playing = False

        # -----------------------------------------------------
        # DISCONNECT
        # -----------------------------------------------------

        if self._disconnect_requested:

            await self.update_message()

            return

        # -----------------------------------------------------
        # LOOP TRACK
        # -----------------------------------------------------

        if (
            self.loop_mode == "track"
            and self.current is not None
        ):

            await asyncio.sleep(0.2)

            if self._disconnect_requested:
                return

            await self.play_next()

            return

        # -----------------------------------------------------
        # LOOP QUEUE
        # -----------------------------------------------------

        if (
            self.loop_mode == "queue"
            and self.current is not None
        ):

            self.queue.append(
                self.current
            )

        # -----------------------------------------------------
        # NEXT TRACK
        # -----------------------------------------------------

        await asyncio.sleep(0.2)

        if self._disconnect_requested:
            return

        if self.queue:

            await self.play_next()

        else:

            self.current = None
            self.is_playing = False

            await self.update_message()

    # =========================================================
    # PAUSE
    # =========================================================

    def pause(self) -> bool:

        if not self.voice_client:
            return False

        if not self.voice_client.is_playing():
            return False

        self.voice_client.pause()

        return True

    # =========================================================
    # RESUME
    # =========================================================

    def resume(self) -> bool:

        if not self.voice_client:
            return False

        if not self.voice_client.is_paused():
            return False

        self.voice_client.resume()

        return True

    # =========================================================
    # SKIP
    # =========================================================

    async def skip(self) -> bool:
        """
        Пропустить текущий трек.
        """

        if not self.voice_client:
            return False

        if not (
            self.voice_client.is_playing()
            or self.voice_client.is_paused()
        ):
            return False

        self._skip_requested = True

        self.voice_client.stop()

        return True

    # =========================================================
    # STOP
    # =========================================================

    async def stop(self):
        """
        Полностью остановить музыку
        и очистить очередь.
        """

        self.queue.clear()

        self._skip_requested = True

        if self.voice_client:

            if (
                self.voice_client.is_playing()
                or self.voice_client.is_paused()
            ):
                self.voice_client.stop()

        self.current = None

        self.is_playing = False

        await self.update_message()

    # =========================================================
    # VOLUME
    # =========================================================

    def set_volume(
        self,
        volume: float,
    ):
        """
        Установить громкость.

        Основной формат:
            0.0 - 1.0

        Но также понимает:
            0 - 100

        Это сделано для совместимости
        с кнопками MusicControlView.
        """

        # -----------------------------------------------------
        # Если передали 0-100
        # -----------------------------------------------------

        if volume > 1:

            volume = volume / 100

        # -----------------------------------------------------
        # Ограничение
        # -----------------------------------------------------

        volume = max(
            0.0,
            min(
                1.0,
                volume,
            ),
        )

        self.volume = volume

        # -----------------------------------------------------
        # Изменяем уже играющий источник
        # -----------------------------------------------------

        if (
            self.voice_client
            and self.voice_client.source
            and isinstance(
                self.voice_client.source,
                discord.PCMVolumeTransformer,
            )
        ):

            self.voice_client.source.volume = (
                volume
            )

    def get_volume_percent(self) -> int:
        """
        Вернуть громкость в процентах.
        """

        return int(
            round(
                self.volume * 100
            )
        )

    # =========================================================
    # LOOP
    # =========================================================

    def set_loop(
        self,
        mode: str,
    ):
        """
        Установить режим повторения.

        off
        track
        queue
        """

        if mode not in {
            "off",
            "track",
            "queue",
        }:

            raise ValueError(
                "Неизвестный режим loop."
            )

        self.loop_mode = mode

    def cycle_loop(self) -> str:
        """
        Переключить:

        off
          ↓
        track
          ↓
        queue
          ↓
        off
        """

        modes = [
            "off",
            "track",
            "queue",
        ]

        current_index = modes.index(
            self.loop_mode
        )

        self.loop_mode = modes[
            (current_index + 1)
            % len(modes)
        ]

        return self.loop_mode

    # =========================================================
    # STATUS
    # =========================================================

    def is_currently_playing(
        self,
    ) -> bool:

        if not self.voice_client:
            return False

        return (
            self.voice_client.is_playing()
            or self.voice_client.is_paused()
        )

    def is_paused(
        self,
    ) -> bool:

        if not self.voice_client:
            return False

        return self.voice_client.is_paused()

    # =========================================================
    # QUERY
    # =========================================================

    async def add_query(
        self,
        query: str,
    ) -> Track:
        """
        Найти трек и добавить его в очередь.
        """

        track = await get_track(
            query
        )

        self.add_to_queue(
            track
        )

        return track