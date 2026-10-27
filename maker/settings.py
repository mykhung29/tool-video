"""Global settings, storage paths and JSON helpers."""
import json
import os
import threading
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
PROJECTS_DIR = DATA_DIR / "projects"
CACHE_DIR = DATA_DIR / "cache"
TTS_CACHE_DIR = CACHE_DIR / "tts"
PREVIEW_DIR = CACHE_DIR / "preview"
BUILTIN_SFX_DIR = DATA_DIR / "sfx_builtin"
SETTINGS_FILE = DATA_DIR / "settings.json"
BG_HISTORY_FILE = DATA_DIR / "bg_history.json"
WEB_DIR = APP_ROOT / "web"

DEFAULT_WORKSPACE = APP_ROOT / "VideoMaker"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
STICKER_EXTS = {".png", ".webp", ".gif", ".jpg", ".jpeg"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

# Per-video defaults. A content project stores only the keys the user changed;
# everything else falls back to these values (which the settings page edits).
DEFAULT_VIDEO = {
    "voice": "vi-VN-HoaiMyNeural",
    "rate": 0,            # percent, -50..+100
    "pitch": 0,           # Hz, -50..+50
    "pause": 0.4,         # seconds of silence after each comment's voice
    "voice_delay": 0.3,   # seconds between image appearing and voice starting
    "min_duration": 2.0,  # minimum on-screen time for an image without voice
    "effect_in": "pop",
    "effect_out": "fade",
    "emphasis": "none",
    "in_duration": 0.45,
    "out_duration": 0.25,
    "scale": 0.86,        # image width as fraction of frame width
    "pos_x": 0.5,         # image centre, fraction of frame
    "pos_y": 0.5,
    "max_height": 0.75,   # image height cap, fraction of frame height
    "shadow": True,
    "sfx": "random",      # sound when an image appears: "random", file in SoundEffects, or "none"
    "sfx_start": "first", # which images get that sound: "first", "all" or "none"
    "sfx_end": "random",  # sound right after each comment has been read
    "sfx_end_gap": 0.0,   # seconds between the end of speech and that sound (negative = earlier)
    "sticker": "none",    # "none", "random" or file name in Stickers folder
    "sticker_size": 0.16, # sticker width as fraction of frame width
    "sticker_pos": "top_right",
    "gif": "none",        # "none", "random" or file name in GIFs folder (animated GIF/WebP)
    "gif_size": 0.42,
    "gif_pos": "below",
    "overlay_hold": 1.2,  # seconds a GIF/sticker stays on screen before moving to the next comment
    "vfx": "none",        # video clip played after a comment is read: "none", "random" or file in VideoEffects
    "vfx_max": 0.0,       # longest part of a clip to use, seconds (0 = whole clip / trim range)
    "vfx_trim_start": 0.0,
    "vfx_trim_end": 0.0,  # 0 = until the end of the clip
    "vfx_size": 0.75,     # clip width as fraction of frame width
    "vfx_x": 0.5,
    "vfx_y": 0.72,
    "vfx_volume": 100,
    "voice_on": True,
    "sfx_on": True,
    "music_on": True,
    "bg_audio_on": False,
    "voice_volume": 100,
    "sfx_volume": 45,
    "music_volume": 25,   # loudness relative to the voice (always below it, max 80)
    "bg_volume": 30,
    "ducking": True,
    "duck_level": 35,     # music volume % while voice plays
    "music": "random",    # "random", "none" or file name in SoundBackground folder
    "end_padding": 0.4,
}

SETTINGS_VERSION = 2

DEFAULT_SETTINGS = {
    "version": SETTINGS_VERSION,
    "backgrounds_dir": str(DEFAULT_WORKSPACE / "Backgrounds"),
    "contents_dir": str(DEFAULT_WORKSPACE / "Contents"),
    "output_dir": str(DEFAULT_WORKSPACE / "Output"),
    "sfx_dir": str(DEFAULT_WORKSPACE / "SoundEffects"),
    "stickers_dir": str(DEFAULT_WORKSPACE / "Stickers"),
    "gifs_dir": str(DEFAULT_WORKSPACE / "GIFs"),
    "vfx_dir": str(DEFAULT_WORKSPACE / "VideoEffects"),
    "music_dir": str(DEFAULT_WORKSPACE / "SoundBackground"),
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "crf": 20,
    "preset": "medium",
    "audio_bitrate": "192k",
    "preview_scale": 0.5,
    "name_pattern": "{name}",
    "avoid_repeat": 2,     # do not reuse the last N backgrounds when picking randomly
    "tts_provider": "edge",
    "auto_ocr": True,      # read the comment text from the image when no text was entered
    "defaults": dict(DEFAULT_VIDEO),
}

_lock = threading.RLock()


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def ensure_dirs() -> None:
    for d in (DATA_DIR, PROJECTS_DIR, TTS_CACHE_DIR, PREVIEW_DIR, BUILTIN_SFX_DIR):
        d.mkdir(parents=True, exist_ok=True)
    s = load_settings()
    for key in ("backgrounds_dir", "contents_dir", "sfx_dir", "music_dir", "stickers_dir", "gifs_dir", "vfx_dir", "output_dir"):
        try:
            Path(s[key]).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def load_settings() -> dict:
    with _lock:
        stored = read_json(SETTINGS_FILE, {})
        s = dict(DEFAULT_SETTINGS)
        s.update({k: v for k, v in stored.items() if k != "defaults"})
        s["defaults"] = dict(DEFAULT_VIDEO)
        s["defaults"].update(stored.get("defaults", {}))
        if stored and stored.get("version", 1) < SETTINGS_VERSION:
            # v2: appear sound became "random from SoundEffects"; replace the old untouched default
            if s["defaults"].get("sfx") == "pop":
                s["defaults"]["sfx"] = "random"
            s["version"] = SETTINGS_VERSION
            write_json(SETTINGS_FILE, s)
        return s


def save_settings(new: dict) -> dict:
    with _lock:
        s = load_settings()
        for k, v in new.items():
            if k == "defaults" and isinstance(v, dict):
                s["defaults"].update({dk: dv for dk, dv in v.items() if dk in DEFAULT_VIDEO})
            elif k in DEFAULT_SETTINGS:
                s[k] = v
        write_json(SETTINGS_FILE, s)
        ensure_dirs()
        return s
