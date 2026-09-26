# music/utils.py

from typing import Optional

from .sources import Track, format_duration


# =========================================================
# DURATION
# =========================================================

def format_track_duration(seconds: Optional[int]) -> str:
    """
    Форматирует длительность трека.

    Примеры:
        65 -> 01:05
        3661 -> 1:01:01
        None -> LIVE
    """

    return format_duration(seconds)


# =========================================================
# PROGRESS BAR
# =========================================================

def make_progress_bar(
    current: int,
    total: Optional[int],
    length: int = 14,
) -> str:
    """
    Создаёт красивый текстовый прогресс-бар.

    Например:

    ━━━━━━━●━━━━━━━
    """

    if not total or total <= 0:
        return "🔴 LIVE"

    current = max(0, min(current, total))

    progress = current / total

    position = int(progress * (length - 1))

    bar = ""

    for i in range(length):
        if i == position:
            bar += "●"
        elif i < position:
            bar += "━"
        else:
            bar += "─"

    return bar


# =========================================================
# SOURCE
# =========================================================

def get_source_name(track: Track) -> str:
    """
    Возвращает красивое название источника.
    """

    source = (track.source or "").lower()

    if "soundcloud" in source:
        return "SoundCloud"

    if "youtube" in source:
        return "YouTube"

    return "Music"


def get_source_emoji(track: Track) -> str:
    """
    Возвращает emoji источника.
    """

    source = (track.source or "").lower()

    if "soundcloud" in source:
        return "🟠"

    if "youtube" in source:
        return "🔴"

    return "🎵"


# =========================================================
# LOOP
# =========================================================

def get_loop_name(mode: str) -> str:
    """
    Человекочитаемое название режима повтора.
    """

    names = {
        "off": "Выключен",
        "track": "Трек",
        "queue": "Очередь",
    }

    return names.get(mode, "Выключен")


def get_loop_emoji(mode: str) -> str:
    """
    Emoji для режима повтора.
    """

    emojis = {
        "off": "➡️",
        "track": "🔂",
        "queue": "🔁",
    }

    return emojis.get(mode, "➡️")


# =========================================================
# QUEUE
# =========================================================

def format_queue(
    tracks: list[Track],
    max_items: int = 10,
) -> str:
    """
    Красиво отображает очередь.
    """

    if not tracks:
        return "Очередь пуста."

    lines = []

    for index, track in enumerate(tracks[:max_items], start=1):

        duration = format_track_duration(track.duration)

        lines.append(
            f"`{index:02}` • "
            f"**{track.title}** "
            f"`{duration}`"
        )

    if len(tracks) > max_items:
        remaining = len(tracks) - max_items

        lines.append(
            f"\n… и ещё **{remaining}** трек(ов)"
        )

    return "\n".join(lines)


# =========================================================
# TRACK TITLE
# =========================================================

def shorten_title(
    title: str,
    max_length: int = 55,
) -> str:
    """
    Не позволяет слишком длинному названию
    сломать красивый embed.
    """

    if len(title) <= max_length:
        return title

    return title[:max_length - 3] + "..."


# =========================================================
# VOLUME
# =========================================================

def make_volume_bar(
    volume: float,
    length: int = 10,
) -> str:
    """
    Создаёт индикатор громкости.

    Например:

    🔊 ███████░░░ 70%
    """

    volume = max(0.0, min(1.0, volume))

    filled = round(volume * length)
    empty = length - filled

    return (
        "🔊 "
        + "█" * filled
        + "░" * empty
        + f" {round(volume * 100)}%"
    )


# =========================================================
# PLAYER STATUS
# =========================================================

def get_player_status(player) -> str:
    """
    Возвращает текущий статус проигрывателя.
    """

    if player.is_paused():
        return "⏸️ На паузе"

    if player.is_currently_playing():
        return "▶️ Сейчас играет"

    if player.current:
        return "⏳ Готовится к воспроизведению"

    return "⏹️ Ничего не играет"