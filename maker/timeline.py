"""Turn a project into a concrete timeline: when each image shows and when each voice line plays."""
from pathlib import Path

from . import ffmpeg, ocr, sfx, tts
from .projects import (content_dir, effective_settings, list_gifs, list_stickers, list_vfx, resolve_overlay,
                       set_image_text)
from .settings import load_settings

PER_IMAGE = ("effect_in", "effect_out", "emphasis", "in_duration", "out_duration", "scale",
             "pos_x", "pos_y", "voice")
OVERLAYS = ("gif", "sticker")   # draw order: GIF first, sticker on top


class TimelineError(RuntimeError):
    pass


def build(proj: dict, progress=None, only_index=None, auto_ocr=True) -> dict:
    """Synthesise (or reuse cached) voice clips and lay out segments back to back.

    progress(fraction, message) is called while TTS clips are produced.
    only_index limits the timeline to a single image (used for per-image preview).
    """
    cfg = effective_settings(proj)
    app = load_settings()
    folder = content_dir(proj["name"])
    images = proj["images"]
    if not images:
        raise TimelineError("Content này không có ảnh nào (.png, .jpg, .webp).")
    indices = [only_index] if only_index is not None else range(len(images))

    overlay_files = {"sticker": (list_stickers(), Path(app["stickers_dir"])),
                     "gif": (list_gifs(), Path(app["gifs_dir"]))}
    sounds = sfx.folder_sounds(app["sfx_dir"])
    vfx_files = list_vfx()
    segments = []
    t = 0.0
    total_n = len(indices)
    for n, i in enumerate(indices):
        img = images[i]
        ov = img.get("overrides") or {}
        seg = {k: ov.get(k, cfg[k]) for k in PER_IMAGE}
        for k in ("in_duration", "out_duration", "scale", "pos_x", "pos_y"):
            seg[k] = float(seg[k])
        seg.update({
            "index": i,
            "file": img["file"],
            "path": str(folder / img["file"]),
            "text": img.get("text", ""),
            "voice_path": None,
            "voice_dur": 0.0,
            "voice_start": None,
        })
        seg["overlays"] = []
        for kind in OVERLAYS:
            files, base = overlay_files[kind]
            name = resolve_overlay(ov.get(kind, cfg[kind]), proj["name"], img["file"], files, kind)
            if name:
                seg["overlays"].append({
                    "kind": kind, "file": name, "path": str(base / name),
                    "pos": ov.get(f"{kind}_pos", cfg[f"{kind}_pos"]),
                    "size": float(ov.get(f"{kind}_size", cfg[f"{kind}_size"])),
                })
        # no text typed: read it from the image (batch renders of contents never opened)
        if auto_ocr and app.get("auto_ocr", True) and not img.get("text", "").strip() \
                and not img.get("skip") and not img.get("ocr"):
            if progress:
                progress(n / total_n, f"Đọc chữ từ ảnh {n + 1}/{total_n}")
            try:
                img["text"] = ocr.extract_text(folder / img["file"])
            except ocr.OCRError as e:
                raise TimelineError(f"Ảnh {img['file']}: {e}") from e
            img["ocr"] = True
            set_image_text(proj["name"], img["file"], img["text"])
        text = tts.normalize_text(img.get("text", ""))
        voiced = cfg["voice_on"] and text and not img.get("skip")
        if voiced:
            if progress:
                progress(n / total_n, f"Tạo giọng đọc ảnh {n + 1}/{total_n}")
            try:
                path, dur = tts.get_clip(text, seg["voice"], cfg["rate"], cfg["pitch"], app["tts_provider"])
            except tts.TTSError as e:
                raise TimelineError(f"Ảnh {img['file']}: {e}") from e
            seg["voice_path"] = str(path)
            seg["voice_dur"] = dur
            delay = min(float(cfg["voice_delay"]), seg["in_duration"] + 0.2)
            hold = delay + dur + float(cfg["pause"])
            seg["voice_start"] = t + delay
        else:
            hold = float(cfg["min_duration"])
        # the moment the comment has been read: end sound, stickers/GIFs and video effect start here
        react_at = seg["voice_start"] + seg["voice_dur"] + float(cfg["sfx_end_gap"]) if voiced else t + hold
        react_at = max(t, react_at)
        seg["overlay_delay"] = react_at - t
        for o in seg["overlays"]:
            o["delay"] = react_at - t
        # video effect: plays right after the comment is read; the comment stays on
        # screen while it plays and both disappear together
        seg["vfx"] = None
        vfx_name = resolve_overlay(ov.get("vfx", cfg["vfx"]), proj["name"], img["file"], vfx_files, "vfx")
        if vfx_name:
            vpath = Path(app["vfx_dir"]) / vfx_name
            try:
                clip_len = ffmpeg.probe(vpath)["duration"]
            except Exception as e:
                raise TimelineError(f"Ảnh {img['file']}: không đọc được video effect {vfx_name}: {e}") from e
            a = min(max(0.0, float(ov.get("vfx_trim_start", cfg["vfx_trim_start"]))), max(0.0, clip_len - 0.1))
            b = float(ov.get("vfx_trim_end", cfg["vfx_trim_end"]) or 0)
            b = clip_len if b <= 0 or b > clip_len else b
            if float(cfg["vfx_max"]) > 0:
                b = min(b, a + float(cfg["vfx_max"]))
            if b - a >= 0.1:
                at = max(t + 0.05, react_at)
                seg["vfx"] = {
                    "file": vfx_name, "path": str(vpath), "at": at, "dur": b - a, "trim_start": a,
                    "clip_len": clip_len,
                    "size": float(ov.get("vfx_size", cfg["vfx_size"])),
                    "x": float(ov.get("vfx_x", cfg["vfx_x"])), "y": float(ov.get("vfx_y", cfg["vfx_y"])),
                    "volume": float(ov.get("vfx_volume", cfg["vfx_volume"])),
                }
                # the comment's exit animation ends exactly when the clip ends
                spoken = (seg["voice_start"] - t + seg["voice_dur"]) if voiced else 0.0
                hold = max(spoken, (at - t) + (b - a) - seg["out_duration"])
        if seg["overlays"] and not seg["vfx"]:
            # GIF/sticker pops in when the voice ends; keep it up a moment before moving on
            hold = max(hold, seg["overlay_delay"] + float(ov.get("overlay_hold", cfg["overlay_hold"])))
        dur = hold + seg["out_duration"]
        fixed = float(ov.get("duration") or 0)
        if fixed > dur:
            dur = fixed  # user asked for longer; never shorter than the voice needs
        dur += float(ov.get("extra_hold") or 0)
        dur = max(dur, seg["in_duration"] + seg["out_duration"] + 0.2)
        seg["start"] = t
        seg["duration"] = dur
        # sound effects: when the image appears (first comment only by default) and
        # right after its comment has been read (end of hold for images without voice)
        events = []
        # a sound chosen for this comment specifically always plays; otherwise the
        # video-wide rule decides (first comment only / every comment / never)
        if "sfx" in ov or cfg["sfx_start"] == "all" or (cfg["sfx_start"] == "first" and i == 0):
            sid = sfx.pick(ov.get("sfx", cfg["sfx"]), app["sfx_dir"], f"{proj['name']}/{img['file']}/start", sounds)
            if sid:
                events.append({"time": t, "sfx": sid, "kind": "start"})
        end_at = react_at
        sid = sfx.pick(ov.get("sfx_end", cfg["sfx_end"]), app["sfx_dir"], f"{proj['name']}/{img['file']}/end", sounds)
        if sid:
            events.append({"time": end_at, "sfx": sid, "kind": "end"})
        seg["sfx_events"] = events
        segments.append(seg)
        t += dur

    total = t + float(cfg["end_padding"])
    if progress:
        progress(1.0, "Đã chuẩn bị giọng đọc")
    return {"segments": segments, "total": total, "settings": cfg}


def segment_media_url(seg: dict) -> dict:
    """Public (JSON-safe) view of a segment for the browser preview."""
    out = {k: v for k, v in seg.items() if k not in ("path", "voice_path", "overlays")}
    out["overlays"] = [{k: v for k, v in o.items() if k != "path"} for o in seg["overlays"]]
    out["vfx"] = {k: v for k, v in seg["vfx"].items() if k != "path"} if seg.get("vfx") else None
    out["voice_file"] = Path(seg["voice_path"]).name if seg["voice_path"] else None
    return out
