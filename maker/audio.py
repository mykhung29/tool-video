"""Mix voice, sound effects, music (with ducking) and background audio into one WAV."""
import random
import wave
from pathlib import Path

import numpy as np

from . import ffmpeg
from .ffmpeg import SAMPLE_RATE as SR
from .projects import list_music
from .settings import load_settings
from .sfx import resolve_sfx


def _place(track, clip, start_s, gain):
    if clip is None or len(clip) == 0 or gain <= 0:
        return
    i = int(round(start_s * SR))
    if i >= len(track):
        return
    n = min(len(clip), len(track) - i)
    track[i:i + n] += clip[:n] * gain


MAX_MUSIC_REL = 80     # sound background never louder than 80 % of the voice
REFERENCE_RMS = 0.1    # about -20 dBFS, used when a video has no voice


def _rms(x):
    if x is None:
        return REFERENCE_RMS
    active = x[np.abs(x).max(axis=1) > 1e-4]  # ignore silence between clips
    return float(np.sqrt(np.mean(active ** 2))) if len(active) else REFERENCE_RMS


def load_sfx(path):
    """Decode a sound effect, drop leading silence (downloaded clips often start 0.1-0.4 s
    late) and peak-normalise so the SFX volume slider means the same for every file."""
    x = ffmpeg.decode_audio(path)
    amp = np.abs(x).max(axis=1) if len(x) else np.zeros(0)
    loud = np.nonzero(amp > 0.02)[0]
    if not len(loud):
        return x
    x = x[max(0, loud[0] - int(0.01 * SR)):]
    return x * (0.9 / float(amp.max()))


def _duck_curve(n, windows, level, ramp=0.18):
    """Gain curve that dips to `level` inside voice windows with smooth ramps."""
    target = np.ones(n, dtype=np.float32)
    for a, b in windows:
        ia, ib = max(0, int((a - 0.12) * SR)), min(n, int((b + 0.25) * SR))
        target[ia:ib] = level
    # smooth with a moving average (ramp seconds) via cumulative sum
    k = max(1, int(ramp * SR))
    c = np.cumsum(np.concatenate([np.full(k, target[0]), target]), dtype=np.float64)
    smooth = (c[k:] - c[:-k]) / k
    return smooth.astype(np.float32)[:, None]


def choose_music(cfg):
    if not cfg.get("music_on") or cfg.get("music") in (None, "", "none"):
        return None
    folder = Path(load_settings()["music_dir"])
    if cfg["music"] == "random":
        tracks = list_music()
        return folder / random.choice(tracks) if tracks else None
    p = folder / cfg["music"]
    if not p.is_file():
        raise RuntimeError(f"Không tìm thấy file nhạc nền '{cfg['music']}' trong thư mục SoundBackground.")
    return p


def mix(timeline, out_path: Path, background=None, bg_offset=0.0, music_path=None) -> dict:
    cfg = timeline["settings"]
    total = timeline["total"]
    n = int(np.ceil(total * SR))
    voice = np.zeros((n, 2), dtype=np.float32)
    fx = np.zeros((n, 2), dtype=np.float32)
    out = np.zeros((n, 2), dtype=np.float32)
    sfx_dir = load_settings()["sfx_dir"]
    sfx_cache = {}
    windows = []

    for seg in timeline["segments"]:
        if seg["voice_path"] and cfg["voice_on"]:
            clip = ffmpeg.decode_audio(seg["voice_path"])
            _place(voice, clip, seg["voice_start"], cfg["voice_volume"] / 100)
            windows.append((seg["voice_start"], seg["voice_start"] + seg["voice_dur"]))
        vfx = seg.get("vfx")
        if vfx and vfx["volume"] > 0 and ffmpeg.probe(vfx["path"])["has_audio"]:
            clip = ffmpeg.decode_audio(vfx["path"], start=vfx["trim_start"], duration=vfx["dur"])
            f = min(len(clip), int(0.04 * SR))  # tiny fades so cut points don't click
            if f > 1:
                clip[:f] *= np.linspace(0, 1, f, dtype=np.float32)[:, None]
                clip[-f:] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
            _place(voice, clip, vfx["at"], vfx["volume"] / 100)
            windows.append((vfx["at"], vfx["at"] + vfx["dur"]))
        if cfg["sfx_on"]:
            for ev in seg.get("sfx_events", []):
                p = resolve_sfx(ev["sfx"], sfx_dir)
                if p is None:
                    continue
                if p not in sfx_cache:
                    sfx_cache[p] = load_sfx(p)
                _place(fx, sfx_cache[p], ev["time"], cfg["sfx_volume"] / 100)

    out += voice + fx
    if music_path:
        music = ffmpeg.decode_audio(music_path, loop=True, duration=total)
        music = np.pad(music, ((0, max(0, n - len(music))), (0, 0)))[:n]
        # Sound background is levelled against the voice's actual loudness, so it stays
        # quieter than the narration whatever the source file's own level is.
        rel = min(float(cfg["music_volume"]), MAX_MUSIC_REL) / 100
        music *= rel * _rms(voice if windows else None) / max(_rms(music), 1e-5)
        if cfg["ducking"] and windows:
            music *= _duck_curve(n, windows, cfg["duck_level"] / 100)
        # gentle fade in/out so looping tracks don't start or stop abruptly
        f = min(int(0.8 * SR), n // 4)
        if f > 0:
            ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
            music[:f] *= ramp
            music[-f:] *= ramp[::-1]
        out += music
    if background and cfg["bg_audio_on"] and ffmpeg.probe(background)["has_audio"]:
        bg = ffmpeg.decode_audio(background, loop=True, start=bg_offset, duration=total)
        bg = np.pad(bg, ((0, max(0, n - len(bg))), (0, 0)))[:n] * (cfg["bg_volume"] / 100)
        if cfg["ducking"] and windows:
            bg *= _duck_curve(n, windows, cfg["duck_level"] / 100)
        out += bg

    peak = float(np.abs(out).max()) if n else 0.0
    if peak > 0.98:
        out *= 0.98 / peak
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return {"music": music_path.name if music_path else None}
