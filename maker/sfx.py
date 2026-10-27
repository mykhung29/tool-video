"""Built-in sound effects, synthesised once into data/sfx_builtin so no assets ship with the app."""
import hashlib
import shutil
import wave
from pathlib import Path

import numpy as np

from .settings import AUDIO_EXTS, BUILTIN_SFX_DIR

SR = 48000
BUILTIN = {
    "pop": "Pop",
    "click": "Click",
    "whoosh": "Whoosh",
    "ding": "Ding",
    "bubble": "Bubble",
}


def _env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _synth(name: str) -> np.ndarray:
    rng = np.random.default_rng(7)
    if name == "pop":
        n = int(SR * 0.12)
        t = np.arange(n) / SR
        f = 900 * np.exp(-t * 28) + 220
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.03)
    elif name == "click":
        n = int(SR * 0.05)
        t = np.arange(n) / SR
        x = (np.sin(2 * np.pi * 2200 * t) * 0.6 + rng.normal(0, 0.3, n)) * _env(n, 0.0005, 0.006)
    elif name == "whoosh":
        n = int(SR * 0.45)
        noise = rng.normal(0, 1, n)
        # sweep a one-pole low-pass cutoff up then down
        t = np.arange(n) / n
        cutoff = 0.02 + 0.25 * np.sin(np.pi * t) ** 2
        y = np.zeros(n)
        acc = 0.0
        for i in range(n):
            acc += cutoff[i] * (noise[i] - acc)
            y[i] = acc
        x = y / (np.abs(y).max() + 1e-9) * np.sin(np.pi * t) ** 1.5
    elif name == "ding":
        n = int(SR * 0.9)
        t = np.arange(n) / SR
        x = (np.sin(2 * np.pi * 1318.5 * t) + 0.4 * np.sin(2 * np.pi * 2637 * t)) * _env(n, 0.002, 0.25)
    elif name == "bubble":
        n = int(SR * 0.16)
        t = np.arange(n) / SR
        f = 300 + 1400 * (t / t[-1]) ** 0.6
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.003, 0.05)
    else:
        raise KeyError(name)
    x = x / (np.abs(x).max() + 1e-9) * 0.8
    return x.astype(np.float32)


def ensure_builtin() -> None:
    BUILTIN_SFX_DIR.mkdir(parents=True, exist_ok=True)
    for name in BUILTIN:
        path = BUILTIN_SFX_DIR / f"{name}.wav"
        if path.exists():
            continue
        x = _synth(name)
        pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())


def seed_folder(sfx_dir: str) -> None:
    """Copy the built-in sounds into an empty SoundEffects folder so "random" has material."""
    d = Path(sfx_dir)
    if not d.is_dir() or any(f.suffix.lower() in AUDIO_EXTS for f in d.iterdir()):
        return
    ensure_builtin()
    for name in BUILTIN:
        shutil.copyfile(BUILTIN_SFX_DIR / f"{name}.wav", d / f"{name}.wav")


def folder_sounds(sfx_dir: str) -> list:
    d = Path(sfx_dir)
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS)


def list_sfx(sfx_dir: str) -> list:
    return [{"id": n, "label": n} for n in folder_sounds(sfx_dir)]


def pick(choice: str, sfx_dir: str, key: str, sounds=None):
    """Turn a setting ("none", "random" or a file name) into a sound id.
    "random" draws from the SoundEffects folder, seeded by `key` so the preview and
    the rendered video play the same sound."""
    if not choice or choice == "none":
        return None
    if choice != "random":
        return choice
    sounds = folder_sounds(sfx_dir) if sounds is None else sounds
    if not sounds:
        return None
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return sounds[h % len(sounds)]


def resolve_sfx(sfx_id: str, sfx_dir: str):
    """Return the path for a sound effect id, or None when disabled/missing."""
    if not sfx_id or sfx_id == "none":
        return None
    p = Path(sfx_dir) / sfx_id
    if p.is_file():
        return p
    if sfx_id in BUILTIN:  # projects saved before sounds lived in the folder
        ensure_builtin()
        return BUILTIN_SFX_DIR / f"{sfx_id}.wav"
    return None
