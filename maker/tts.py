"""Text-to-speech with an on-disk cache.

The default provider is Microsoft Edge neural TTS (package `edge-tts`): free, natural
Vietnamese voices, but it needs an Internet connection. Providers are looked up by name
so another engine can be added by implementing `synthesize(text, voice, rate, pitch, out_path)`.
"""
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
import wave
from pathlib import Path

import numpy as np

from . import ffmpeg
from .settings import DATA_DIR, TTS_CACHE_DIR, read_json, write_json

VOICES_FILE = DATA_DIR / "voices.json"

FALLBACK_VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "label": "Hoài My (Nữ, Tiếng Việt)", "locale": "vi-VN"},
    {"id": "vi-VN-NamMinhNeural", "label": "Nam Minh (Nam, Tiếng Việt)", "locale": "vi-VN"},
    {"id": "en-US-AriaNeural", "label": "Aria (Female, English US)", "locale": "en-US"},
    {"id": "en-US-GuyNeural", "label": "Guy (Male, English US)", "locale": "en-US"},
]


class TTSError(RuntimeError):
    pass


def _signed(v, unit):
    v = int(round(float(v or 0)))
    return f"{'+' if v >= 0 else '-'}{abs(v)}{unit}"


class EdgeProvider:
    name = "edge"

    def synthesize(self, text, voice, rate, pitch, out_path: Path):
        try:
            import edge_tts
        except ImportError as e:
            raise TTSError("Chưa cài gói edge-tts (pip install edge-tts).") from e

        async def go(volume):
            comm = edge_tts.Communicate(text, voice, rate=_signed(rate, "%"), pitch=_signed(pitch, "Hz"),
                                        volume=volume)
            await comm.save(str(out_path))

        # The Edge service intermittently answers a request with no audio (or drops the
        # connection). Retry with a short back-off; an inaudible 1-2 % volume change also
        # makes each attempt a distinct request.
        last = None
        volumes = ("+0%", "+1%", "-1%", "+2%", "-2%", "+0%", "+1%", "-1%")
        for attempt, volume in enumerate(volumes):
            try:
                asyncio.run(go(volume))
                last = None
                break
            except Exception as e:
                last = e
                if "NoAudioReceived" not in e.__class__.__name__ and attempt >= 2:
                    break  # network problems will not fix themselves within seconds
                time.sleep(0.6 * (attempt + 1))
        if last is not None:
            e = last
            msg = str(e) or e.__class__.__name__
            if "NoAudioReceived" in e.__class__.__name__:
                msg = ("dịch vụ không trả về âm thanh sau nhiều lần thử (máy chủ đang quá tải, giọng đọc "
                       "không hợp lệ hoặc văn bản chỉ có ký tự đặc biệt) — hãy thử lại sau ít phút")
            elif any(s in msg.lower() for s in ("cannot connect", "getaddrinfo", "timeout", "ssl", "connection")):
                msg = "không kết nối được máy chủ Edge TTS — kiểm tra kết nối Internet"
            raise TTSError(f"Lỗi tạo giọng đọc (Edge TTS, giọng {voice}): {msg}") from e
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise TTSError(f"Edge TTS không tạo được âm thanh cho giọng {voice}.")

    def voices(self):
        import edge_tts
        raw = asyncio.run(edge_tts.list_voices())
        out = []
        for v in raw:
            gender = {"Female": "Nữ", "Male": "Nam"}.get(v.get("Gender"), v.get("Gender", ""))
            short = v["ShortName"]
            name = short.split("-")[-1].replace("Neural", "").replace("Multilingual", " Multi")
            name = re.sub(r"(?<!^)(?=[A-Z])", " ", name).strip()
            out.append({"id": short, "label": f"{name} ({gender}, {v['Locale']})", "locale": v["Locale"]})
        out.sort(key=lambda x: (not x["locale"].startswith("vi"), x["locale"], x["label"]))
        return out


PROVIDERS = {"edge": EdgeProvider()}


def provider(name="edge"):
    p = PROVIDERS.get(name)
    if not p:
        raise TTSError(f"Dịch vụ TTS '{name}' chưa được hỗ trợ.")
    return p


def list_voices(provider_name="edge", refresh=False):
    cached = read_json(VOICES_FILE, None)
    if cached and not refresh:
        return cached
    try:
        voices = provider(provider_name).voices()
        write_json(VOICES_FILE, voices)
        return voices
    except Exception:
        return cached or FALLBACK_VOICES


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def cache_key(text, voice, rate, pitch, provider_name="edge") -> str:
    raw = json.dumps([provider_name, voice, int(rate or 0), int(pitch or 0), normalize_text(text)], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


SILENCE = 0.01   # amplitude below this counts as silence when trimming
EDGE_PAD = 0.03  # seconds kept before/after the speech so consonants are not clipped


def _trim_to_wav(src: Path, dst: Path) -> float:
    """Decode a synthesised clip, cut the silence Edge TTS adds at both ends (~0.2 s at
    the start, ~0.8 s at the end) and store it as WAV. Returns the trimmed duration, so
    the timeline knows exactly when the speech stops."""
    x = ffmpeg.decode_audio(src)
    loud = np.nonzero(np.abs(x).max(axis=1) > SILENCE)[0] if len(x) else []
    if not len(loud):
        raise TTSError("Giọng đọc tạo ra không có âm thanh.")
    pad = int(EDGE_PAD * ffmpeg.SAMPLE_RATE)
    x = x[max(0, loud[0] - pad):loud[-1] + pad]
    tmp = dst.with_name(dst.stem + f".{uuid.uuid4().hex[:8]}.part.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(ffmpeg.SAMPLE_RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    os.replace(tmp, dst)
    return len(x) / ffmpeg.SAMPLE_RATE


def get_clip(text, voice, rate=0, pitch=0, provider_name="edge"):
    """Return (path, duration_seconds) of the trimmed voice clip, synthesising only when not cached."""
    text = normalize_text(text)
    if not text:
        raise TTSError("Nội dung đọc trống.")
    key = cache_key(text, voice, rate, pitch, provider_name)
    mp3 = TTS_CACHE_DIR / f"{key}.mp3"
    wav = TTS_CACHE_DIR / f"{key}.wav"
    meta_path = TTS_CACHE_DIR / f"{key}.json"
    meta = read_json(meta_path, None)
    if wav.exists() and meta and meta.get("trimmed") and meta.get("duration", 0) > 0:
        return wav, float(meta["duration"])
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not mp3.exists():
        tmp = TTS_CACHE_DIR / f"{key}.{uuid.uuid4().hex[:8]}.part.mp3"
        try:
            provider(provider_name).synthesize(text, voice, rate, pitch, tmp)
            os.replace(tmp, mp3)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    duration = _trim_to_wav(mp3, wav)   # clips cached before trimming existed are reused, not re-synthesised
    write_json(meta_path, {"duration": duration, "trimmed": True, "text": text, "voice": voice})
    return wav, duration
