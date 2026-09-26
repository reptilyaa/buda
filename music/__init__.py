# music/__init__.py

from .player import MusicPlayer
from .sources import Track, get_track
from .views import MusicControlView, build_player_embed

__all__ = [
    "MusicPlayer",
    "Track",
    "get_track",
    "MusicControlView",
    "build_player_embed",
]