"""Thin wrappers around the ffmpeg binary (bundled via imageio-ffmpeg)."""
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
SAMPLE_RATE = 48000


class FFmpegError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise FFmpegError("Không tìm thấy ffmpeg. Hãy cài ffmpeg hoặc gói imageio-ffmpeg.") from e


def run(args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([ffmpeg_exe(), "-hide_banner", *args], capture_output=True,
                          creationflags=CREATE_NO_WINDOW, **kw)


def popen(args, **kw) -> subprocess.Popen:
    return subprocess.Popen([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *args],
                            creationflags=CREATE_NO_WINDOW, **kw)


_probe_cache = {}


def probe(path) -> dict:
    """Return {'duration': float, 'width': int, 'height': int, 'has_audio': bool}."""
    p = Path(path)
    key = (str(p), p.stat().st_mtime, p.stat().st_size)
    if key in _probe_cache:
        return _probe_cache[key]
    out = run(["-i", str(p)]).stderr.decode("utf-8", "replace")
    info = {"duration": 0.0, "width": 0, "height": 0, "has_audio": False}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Stream #.*?Video:.*?, (\d{2,5})x(\d{2,5})", out)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    info["has_audio"] = bool(re.search(r"Stream #.*?Audio:", out))
    if not m and info["duration"] == 0:
        raise FFmpegError(f"Không đọc được file media: {p.name}")
    _probe_cache[key] = info
    return info


def decode_audio(path, loop: bool = False, start: float = 0.0, duration: float = 0.0) -> np.ndarray:
    """Decode any audio (or video's audio track) to float32 stereo array (n, 2) at 48 kHz."""
    args = []
    if loop:
        args += ["-stream_loop", "-1"]
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration > 0:
        args += ["-t", f"{duration:.3f}"]
    args += ["-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    res = run(["-loglevel", "error", *args])
    if res.returncode != 0:
        raise FFmpegError(f"Lỗi giải mã âm thanh {Path(path).name}: "
                          f"{res.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    data = np.frombuffer(res.stdout, dtype=np.float32)
    return data[: len(data) // 2 * 2].reshape(-1, 2).copy()
