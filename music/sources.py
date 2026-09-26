# music/sources.py

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import yt_dlp


@dataclass
class Track:
    title: str
    url: str
    webpage_url: str
    duration: int | None
    thumbnail: str | None
    uploader: str | None
    source: str
    http_headers: dict[str, str] | None = None


YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "extract_flat": False,

    # Не скачиваем файл на диск.
    "skip_download": True,

    # Не используем слишком агрессивные настройки.
    "nocheckcertificate": False,
}


def _detect_source(info: dict[str, Any]) -> str:
    extractor = str(
        info.get("extractor_key")
        or info.get("extractor")
        or ""
    ).lower()

    webpage_url = str(
        info.get("webpage_url")
        or info.get("original_url")
        or ""
    ).lower()

    if "soundcloud" in extractor or "soundcloud" in webpage_url:
        return "soundcloud"

    return "youtube"


def _build_track(info: dict[str, Any]) -> Track:
    webpage_url = (
        info.get("webpage_url")
        or info.get("original_url")
        or info.get("url")
    )

    stream_url = info.get("url")

    if not webpage_url:
        raise RuntimeError("У трека отсутствует webpage_url.")

    if not stream_url:
        raise RuntimeError("yt-dlp не вернул URL аудиопотока.")

    return Track(
        title=info.get("title") or "Без названия",
        url=stream_url,
        webpage_url=webpage_url,
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        uploader=info.get("uploader") or info.get("channel"),
        source=_detect_source(info),
        http_headers=info.get("http_headers") or {},
    )


def _extract_sync(query: str) -> dict[str, Any]:
    """
    Первичное получение информации о треке.
    """

    options = dict(YTDL_OPTIONS)

    # Для обычного текста ищем первый результат YouTube.
    if not re.match(r"^https?://", query.strip(), re.IGNORECASE):
        query = f"ytsearch1:{query}"

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            query,
            download=False,
        )

    if not info:
        raise RuntimeError("yt-dlp не вернул информацию о треке.")

    # ytsearch возвращает playlist-like объект.
    if "entries" in info:
        entries = [
            entry
            for entry in info.get("entries", [])
            if entry
        ]

        if not entries:
            raise RuntimeError("По запросу ничего не найдено.")

        info = entries[0]

    return info


def _refresh_sync(webpage_url: str) -> dict[str, Any]:
    """
    Получает НОВЫЙ URL аудиопотока непосредственно
    перед воспроизведением.
    """

    options = dict(YTDL_OPTIONS)

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            webpage_url,
            download=False,
        )

    if not info:
        raise RuntimeError(
            "Не удалось заново получить поток."
        )

    if "entries" in info:
        entries = [
            entry
            for entry in info.get("entries", [])
            if entry
        ]

        if not entries:
            raise RuntimeError(
                "Не удалось получить данные трека."
            )

        info = entries[0]

    return info


async def get_track(query: str) -> Track:
    """
    Найти трек.
    """

    info = await asyncio.to_thread(
        _extract_sync,
        query.strip(),
    )

    return _build_track(info)


async def refresh_track(track: Track) -> Track:
    """
    Обновить прямой URL аудиопотока.

    Важно:
    track.webpage_url остаётся постоянной ссылкой
    на YouTube/SoundCloud, а track.url получает
    свежий CDN URL.
    """

    info = await asyncio.to_thread(
        _refresh_sync,
        track.webpage_url,
    )

    refreshed = _build_track(info)

    # Сохраняем исходную стабильную страницу.
    refreshed.webpage_url = track.webpage_url

    return refreshed


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "LIVE"

    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "LIVE"

    if seconds < 0:
        return "LIVE"

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"