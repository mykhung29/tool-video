"""Video renderer.

Pipeline: ffmpeg decodes the background (looped, cropped to 9:16) into raw RGB frames ->
Python composites the animated comment images onto each frame -> a second ffmpeg encodes
the frames together with the pre-mixed audio into MP4. The output is written to a .part
file and only renamed to the final name after ffmpeg exits successfully.
"""
import bisect
import datetime as dt
import os
import random
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from . import audio, ffmpeg
from .effects import overlay_center, overlay_state, state, vfx_state
from .projects import load_project, pick_background, record_bg, set_status
from .settings import PREVIEW_DIR, load_settings
from .timeline import build


class Cancelled(Exception):
    pass


class RenderError(RuntimeError):
    pass


GLOW_COLOR = (255, 214, 64)


class Layer:
    """A comment image prepared at its on-screen size, with shadow/glow baked in."""

    def __init__(self, seg, cfg, W, H):
        try:
            img = Image.open(seg["path"]).convert("RGBA")
        except Exception as e:
            raise RenderError(f"Không mở được ảnh {seg['file']}: {e}") from e
        unit = W / 1080
        tw = max(1, int(W * seg["scale"]))
        th = int(img.height * tw / img.width)
        max_h = int(H * float(cfg["max_height"]))
        if th > max_h:
            th = max_h
            tw = max(1, int(img.width * th / img.height))
        img = img.resize((tw, th), Image.LANCZOS)
        m = int(36 * unit)
        canvas = Image.new("RGBA", (tw + 2 * m, th + 2 * m), (0, 0, 0, 0))
        if cfg["shadow"]:
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            alpha = Image.new("L", canvas.size, 0)
            alpha.paste(img.getchannel("A"), (m, m + int(8 * unit)))
            alpha = alpha.filter(ImageFilter.GaussianBlur(14 * unit)).point(lambda v: int(v * 0.5))
            sh.putalpha(alpha)
            canvas = Image.alpha_composite(canvas, sh)
        canvas.alpha_composite(img, (m, m))
        self.box = (tw, th)
        self.pil = {"image": canvas}
        self.arr = self._prep(canvas)
        self.glow = None
        self.overlays = [(o, Overlay(o, W)) for o in seg.get("overlays", [])]
        if seg.get("emphasis") == "highlight":
            alpha = Image.new("L", canvas.size, 0)
            alpha.paste(img.getchannel("A"), (m, m))
            alpha = alpha.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(10 * unit))
            alpha = alpha.point(lambda v: min(255, int(v * 1.6)))
            g = Image.new("RGBA", canvas.size, GLOW_COLOR + (0,))
            g.putalpha(alpha)
            self.pil["glow"] = g
            self.glow = self._prep(g)
        self._scaled = {}

    @staticmethod
    def _prep(im):
        a = np.asarray(im, dtype=np.float32) / 255.0
        alpha = a[:, :, 3:4]
        return a[:, :, :3] * alpha * 255.0, alpha  # premultiplied rgb, alpha

    def at_scale(self, s, kind="image"):
        if abs(s - 1.0) < 0.003:
            return {"image": self.arr, "glow": self.glow}[kind]
        key = (round(s, 3), kind)
        if key in self._scaled:
            return self._scaled[key]
        src = self.pil[kind]
        w, h = max(1, int(src.width * s)), max(1, int(src.height * s))
        res = self._prep(src.resize((w, h), Image.BILINEAR))
        if len(self._scaled) > 64:
            self._scaled.clear()
        self._scaled[key] = res
        return res


class Overlay:
    """A sticker or GIF. Animated GIF/WebP keep every frame with its own duration and loop."""

    MAX_FRAMES = 400

    def __init__(self, spec, W):
        label = "GIF" if spec["kind"] == "gif" else "sticker"
        try:
            im = Image.open(spec["path"])
            n = min(getattr(im, "n_frames", 1), self.MAX_FRAMES)
            first = None
            self.frames, starts, t = [], [], 0.0
            for i in range(n):
                im.seek(i)
                f = im.convert("RGBA")
                if first is None:
                    w = max(1, int(W * spec["size"]))
                    h = max(1, int(f.height * w / f.width))
                    if h > w * 1.4:
                        h = int(w * 1.4)
                        w = max(1, int(f.width * h / f.height))
                    first = (w, h)
                self.frames.append(f.resize(first, Image.LANCZOS))
                starts.append(t)
                t += max(0.02, (im.info.get("duration") or 100) / 1000)
        except Exception as e:
            raise RenderError(f"Không mở được {label} {spec['file']}: {e}") from e
        self.w, self.h = first
        self.starts, self.total = starts, t
        self._cache = {}

    def at(self, t, s):
        idx = 0
        if len(self.frames) > 1:
            idx = bisect.bisect_right(self.starts, t % self.total) - 1
        key = (idx, round(s, 3))
        if key not in self._cache:
            f = self.frames[idx]
            if abs(s - 1.0) >= 0.003:
                f = f.resize((max(1, int(f.width * s)), max(1, int(f.height * s))), Image.BILINEAR)
            if len(self._cache) > 24:
                self._cache.clear()
            self._cache[key] = Layer._prep(f)
        return self._cache[key]


class VfxClip:
    """A video effect: the trimmed part of a clip, decoded by its own ffmpeg process
    frame by frame (the render loop asks for frames in order)."""

    def __init__(self, spec, W, H, fps):
        self.spec, self.fps = spec, fps
        info = ffmpeg.probe(spec["path"])
        if not info["width"]:
            raise RenderError(f"Video effect {spec['file']} không có hình.")
        w = max(2, int(W * spec["size"]) // 2 * 2)
        h = max(2, int(info["height"] * w / info["width"]) // 2 * 2)
        if h > H * 0.8:
            h = int(H * 0.8) // 2 * 2
            w = max(2, int(info["width"] * h / info["height"]) // 2 * 2)
        self.w, self.h = w, h
        self.mask = np.ones((h, w, 1), dtype=np.float32)  # square corners, fully opaque
        self.proc = None
        self.index = -1
        self.last = None

    def _start(self):
        s = self.spec
        self.proc = ffmpeg.popen(["-ss", f"{s['trim_start']:.3f}", "-i", s["path"], "-t", f"{s['dur']:.3f}", "-an",
                                  "-vf", f"scale={self.w}:{self.h},fps={self.fps},format=rgb24",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 stdout=ffmpeg.subprocess.PIPE, stderr=ffmpeg.subprocess.DEVNULL)

    def frame(self, k):
        """RGB frame number k of the trimmed clip (holds the last frame if the clip runs short)."""
        if self.proc is None:
            self._start()
        size = self.w * self.h * 3
        while self.index < k:
            buf = self.proc.stdout.read(size)
            if len(buf) < size:
                break
            self.last = np.frombuffer(buf, dtype=np.uint8).reshape(self.h, self.w, 3)
            self.index += 1
        return self.last

    def layer(self, k, scale):
        rgb = self.frame(k)
        if rgb is None:
            return None
        if abs(scale - 1.0) < 0.003:
            return rgb.astype(np.float32) * self.mask, self.mask
        im = Image.fromarray(rgb).convert("RGBA")
        im.putalpha(Image.fromarray((self.mask[:, :, 0] * 255).astype(np.uint8)))
        im = im.resize((max(1, int(self.w * scale)), max(1, int(self.h * scale))), Image.BILINEAR)
        return Layer._prep(im)

    def close(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait()
            self.proc.stdout.close()
            self.proc = None


def blend(frame, layer, cx, cy, opacity):
    pre, alpha = layer
    h, w = alpha.shape[:2]
    H, W = frame.shape[:2]
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    sx0, sy0 = fx0 - x0, fy0 - y0
    sl = (slice(sy0, sy0 + fy1 - fy0), slice(sx0, sx0 + fx1 - fx0))
    region = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    a = alpha[sl] * opacity
    region = pre[sl] * opacity + region * (1.0 - a)
    frame[fy0:fy1, fx0:fx1] = np.clip(region, 0, 255).astype(np.uint8)


def output_path(name, settings) -> Path:
    out_dir = Path(settings["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    stem = (settings.get("name_pattern") or "{name}").format(
        name=name, date=now.strftime("%Y%m%d"), time=now.strftime("%H%M%S"))
    stem = re.sub(r'[<>:"/\\|?*]', "_", stem).strip() or name
    p = out_dir / f"{stem}.mp4"
    i = 2
    while p.exists() or p.with_name(p.stem + ".part.mp4").exists():
        p = out_dir / f"{stem} ({i}).mp4"
        i += 1
    return p


def render(name, preview=False, progress=None, cancel=None, only_index=None) -> dict:
    """Render one content. Returns {'output', 'background', ...}. Raises on failure."""
    def report(frac, msg):
        if progress:
            progress(max(0.0, min(1.0, frac)), msg)

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    settings = load_settings()
    proj = load_project(name)
    if not proj["images"]:
        raise RenderError("Content không có ảnh nào.")
    report(0.0, "Chuẩn bị")
    tl = build(proj, progress=lambda f, m: (check(), report(0.15 * f, m)), only_index=only_index)
    cfg = tl["settings"]
    check()

    bg_name = pick_background(proj)
    bg_path = Path(settings["backgrounds_dir"]) / bg_name
    info = ffmpeg.probe(bg_path)
    total = tl["total"]
    offset = random.uniform(0, info["duration"] - total - 0.5) if info["duration"] > total + 1 else 0.0

    scale = float(settings["preview_scale"]) if preview else 1.0
    W = int(settings["width"] * scale) // 2 * 2
    H = int(settings["height"] * scale) // 2 * 2
    fps = int(settings["fps"])

    work = Path(tempfile.mkdtemp(prefix="vm_", dir=PREVIEW_DIR))
    wav = work / "audio.wav"
    report(0.16, "Trộn âm thanh")
    music = audio.choose_music(cfg)
    mix_info = audio.mix(tl, wav, background=bg_path, bg_offset=offset, music_path=music)
    check()

    report(0.2, "Chuẩn bị hình ảnh")
    layers = [Layer(seg, cfg, W, H) for seg in tl["segments"]]
    clips = [VfxClip(seg["vfx"], W, H, fps) if seg.get("vfx") else None for seg in tl["segments"]]

    if preview:
        final = PREVIEW_DIR / f"{re.sub(r'[^0-9A-Za-z_-]+', '_', name)}_preview.mp4"
        part = final.with_name(final.stem + ".part.mp4")
        vargs = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
    else:
        final = output_path(name, settings)
        part = final.with_name(final.stem + ".part.mp4")
        vargs = ["-c:v", "libx264", "-preset", settings["preset"], "-crf", str(settings["crf"])]

    n_frames = int(np.ceil(total * fps))
    frame_bytes = W * H * 3
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},format=rgb24"
    dec_log = open(work / "decode.log", "wb")
    enc_log = open(work / "encode.log", "wb")
    dec = ffmpeg.popen(["-stream_loop", "-1", "-ss", f"{offset:.3f}", "-i", str(bg_path),
                        "-t", f"{total + 1:.3f}", "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       stdout=ffmpeg.subprocess.PIPE, stderr=dec_log, bufsize=frame_bytes * 2)
    enc = ffmpeg.popen(["-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                        "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a", *vargs,
                        "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", settings["audio_bitrate"],
                        "-t", f"{total:.3f}", "-movflags", "+faststart", str(part)],
                       stdin=ffmpeg.subprocess.PIPE, stderr=enc_log)
    ok = False
    try:
        buf = bytearray(frame_bytes)
        last = None
        segs = tl["segments"]
        for fi in range(n_frames):
            if fi % 15 == 0:
                check()
                report(0.2 + 0.78 * fi / n_frames, f"Dựng khung hình {fi}/{n_frames}")
            got = dec.stdout.readinto(buf) if dec.stdout else 0
            while got and got < frame_bytes:
                more = dec.stdout.readinto(memoryview(buf)[got:])
                if not more:
                    break
                got += more
            if got == frame_bytes:
                frame = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 3).copy()
                last = frame
            elif last is not None:
                frame = last.copy()  # background ended early: hold the last frame
            else:
                raise RenderError("Không đọc được khung hình từ video nền " + bg_name + ". "
                                  + (work / "decode.log").read_text("utf-8", "replace")[-300:])
            t = fi / fps
            for seg, layer in zip(segs, layers):
                lt = t - seg["start"]
                if lt < 0 or lt >= seg["duration"]:
                    continue
                st = state(seg, lt)
                if st["opacity"] <= 0.004 or st["scale"] <= 0.02:
                    continue
                cx = (seg["pos_x"] + st["dx"]) * W
                cy = (seg["pos_y"] + st["dy"]) * H
                if layer.glow is not None and st["glow"] > 0.01:
                    blend(frame, layer.at_scale(st["scale"], "glow"), cx, cy, st["opacity"] * st["glow"])
                blend(frame, layer.at_scale(st["scale"]), cx, cy, st["opacity"])
                bw, bh = layer.box[0] * st["scale"], layer.box[1] * st["scale"]
                for spec, ov in layer.overlays:
                    ks = overlay_state(spec["delay"], lt)
                    if not ks or ks["opacity"] <= 0.004:
                        continue
                    ocx, ocy = overlay_center(spec["pos"], cx, cy, bw, bh, ov.w * st["scale"], ov.h * st["scale"])
                    blend(frame, ov.at(lt - spec["delay"], st["scale"] * ks["scale"]),
                          ocx, ocy + ks["dy"] * H, st["opacity"] * ks["opacity"])
            # video effects are drawn last, above the comments
            for seg, clip in zip(segs, clips):
                if clip is None:
                    continue
                vt = t - clip.spec["at"]
                if vt < 0 or vt >= clip.spec["dur"]:
                    if vt >= clip.spec["dur"]:
                        clip.close()
                    continue
                vs = vfx_state(vt, clip.spec["dur"])
                if vs["opacity"] <= 0.004:
                    continue
                lay = clip.layer(int(vt * fps), vs["scale"])
                if lay is not None:
                    blend(frame, lay, clip.spec["x"] * W, clip.spec["y"] * H, vs["opacity"])
            try:
                enc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError):
                break
        enc.stdin.close()
        report(0.99, "Hoàn tất mã hoá")
        code = enc.wait()
        if code != 0:
            raise RenderError("FFmpeg mã hoá thất bại: "
                              + (work / "encode.log").read_text("utf-8", "replace").strip()[-400:])
        if not part.exists() or part.stat().st_size < 1024:
            raise RenderError("FFmpeg không tạo ra file video hợp lệ.")
        os.replace(part, final)
        ok = True
    finally:
        for c in clips:
            if c is not None:
                c.close()
        for p in (dec, enc):
            if p.poll() is None:
                p.kill()
            p.wait()
        if dec.stdout:
            dec.stdout.close()
        dec_log.close()
        enc_log.close()
        if not ok and part.exists():
            part.unlink(missing_ok=True)
        for f in work.iterdir():
            f.unlink(missing_ok=True)
        work.rmdir()

    if not preview and only_index is None:
        record_bg(bg_name, name)
        set_status(name, status="done", output=str(final), error=None, last_background=bg_name)
    report(1.0, "Hoàn thành")
    return {"output": str(final), "background": bg_name, "duration": total, "music": mix_info["music"]}
