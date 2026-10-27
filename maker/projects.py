"""Content folders, per-content projects (saved script/config) and background selection."""
import hashlib
import random
import re
import threading
import time
from pathlib import Path

from .settings import (AUDIO_EXTS, BG_HISTORY_FILE, DEFAULT_VIDEO, IMAGE_EXTS, PROJECTS_DIR,
                       STICKER_EXTS, VIDEO_EXTS, load_settings, read_json, write_json)

_lock = threading.RLock()

IMAGE_KEYS = {"effect_in", "effect_out", "emphasis", "in_duration", "out_duration", "scale",
              "pos_x", "pos_y", "sfx", "extra_hold", "duration", "voice", "sticker", "sticker_pos", "sticker_size", "sfx_end",
              "gif", "gif_pos", "gif_size", "overlay_hold",
              "vfx", "vfx_trim_start", "vfx_trim_end", "vfx_size", "vfx_x", "vfx_y", "vfx_volume"}


def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_files(folder, exts):
    d = Path(folder)
    if not d.is_dir():
        return []
    return sorted((f.name for f in d.iterdir() if f.is_file() and f.suffix.lower() in exts), key=natural_key)


def list_backgrounds():
    return list_files(load_settings()["backgrounds_dir"], VIDEO_EXTS)


def list_music():
    return list_files(load_settings()["music_dir"], AUDIO_EXTS)


def list_stickers():
    return list_files(load_settings()["stickers_dir"], STICKER_EXTS)


def list_vfx():
    return list_files(load_settings()["vfx_dir"], VIDEO_EXTS)


def list_gifs():
    return list_files(load_settings()["gifs_dir"], STICKER_EXTS)


def resolve_overlay(choice, content: str, image_file: str, files, salt="sticker"):
    """Map a sticker/GIF setting to a file name. "random" is stable per image so the
    preview and the rendered video show the same file."""
    if not choice or choice == "none":
        return None
    if choice == "random":
        if not files:
            return None
        h = int(hashlib.md5(f"{content}/{image_file}/{salt}".encode("utf-8")).hexdigest(), 16)
        return files[h % len(files)]
    return choice if choice in files else None


def content_dir(name: str) -> Path:
    base = Path(load_settings()["contents_dir"]).resolve()
    p = (base / name).resolve()
    if p.parent != base or not p.is_dir():
        raise FileNotFoundError(f"Không tìm thấy content '{name}'")
    return p


def _project_path(name: str) -> Path:
    return PROJECTS_DIR / f"{name}.json"


def _initial_texts(folder: Path, files):
    texts = {}
    for f in files:
        txt = folder / (Path(f).stem + ".txt")
        if txt.is_file():
            texts[f] = txt.read_text(encoding="utf-8", errors="replace").strip()
    script = folder / "script.txt"
    if script.is_file() and not texts:
        raw = script.read_text(encoding="utf-8", errors="replace").strip()
        parts = re.split(r"\n\s*\n", raw) if re.search(r"\n\s*\n", raw) else raw.splitlines()
        for f, part in zip(files, parts):
            texts[f] = part.strip()
    return texts


def load_project(name: str) -> dict:
    """Load the saved project and reconcile it with the images currently in the folder."""
    with _lock:
        folder = content_dir(name)
        files = list_files(folder, IMAGE_EXTS)
        proj = read_json(_project_path(name), None) or {
            "name": name, "settings": {}, "background": None, "images": [],
            "status": "new", "output": None, "error": None, "last_background": None,
        }
        proj["name"] = name
        known = {img["file"]: img for img in proj["images"]}
        texts = _initial_texts(folder, files) if not proj["images"] else {}
        images = [known[f] for f in (img["file"] for img in proj["images"]) if f in files]
        for f in files:
            if f not in known:
                images.append({"file": f, "text": texts.get(f, ""), "skip": False, "overrides": {}})
        for img in images:
            img.setdefault("overrides", {})
            img.setdefault("skip", False)
            img.setdefault("text", "")
            img.setdefault("ocr", False)
        proj["images"] = images
        return proj


def save_project(name: str, data: dict) -> dict:
    with _lock:
        proj = load_project(name)
        if "settings" in data:
            proj["settings"] = {k: v for k, v in data["settings"].items() if k in DEFAULT_VIDEO}
        if "background" in data:
            proj["background"] = data["background"] or None
        if "images" in data:
            files = {img["file"] for img in proj["images"]}
            new = []
            for img in data["images"]:
                if img.get("file") in files:
                    new.append({
                        "file": img["file"],
                        "text": str(img.get("text", "")),
                        "skip": bool(img.get("skip", False)),
                        "ocr": bool(img.get("ocr", False)),   # text was already read from the image once
                        "overrides": {k: v for k, v in (img.get("overrides") or {}).items()
                                      if k in IMAGE_KEYS and v not in (None, "")},
                    })
            seen = {i["file"] for i in new}
            new += [i for i in proj["images"] if i["file"] not in seen]
            proj["images"] = new
        for k in ("status", "output", "error", "last_background"):
            if k in data:
                proj[k] = data[k]
        proj["updated"] = time.time()
        write_json(_project_path(name), proj)
        return proj


def set_status(name: str, **fields):
    with _lock:
        path = _project_path(name)
        proj = read_json(path, None)
        if proj is None:
            proj = load_project(name)
        proj.update(fields)
        write_json(path, proj)


def set_image_text(name: str, file: str, text: str):
    """Store text read from an image (OCR) without touching the rest of the project."""
    with _lock:
        proj = load_project(name)
        for img in proj["images"]:
            if img["file"] == file:
                img["text"] = text
                img["ocr"] = True
        write_json(_project_path(name), proj)


def effective_settings(proj: dict) -> dict:
    s = dict(load_settings()["defaults"])
    s.update(proj.get("settings") or {})
    return s


def scan_contents() -> list:
    base = Path(load_settings()["contents_dir"])
    if not base.is_dir():
        return []
    out = []
    for d in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: natural_key(p.name)):
        files = list_files(d, IMAGE_EXTS)
        proj = read_json(_project_path(d.name), {}) or {}
        output = proj.get("output")
        status = proj.get("status", "new")
        if status == "done" and (not output or not Path(output).is_file()):
            status = "missing"   # rendered earlier but the file was moved/deleted
        texts = sum(1 for i in proj.get("images", []) if i.get("text", "").strip() and not i.get("skip"))
        out.append({
            "name": d.name,
            "image_count": len(files),
            "voiced_count": texts,
            "status": status,
            "error": proj.get("error"),
            "output": output,
            "background": proj.get("background"),
            "last_background": proj.get("last_background"),
            "has_project": bool(proj),
        })
    return out


# ---- background selection -------------------------------------------------

def bg_history() -> list:
    return read_json(BG_HISTORY_FILE, [])


def record_bg(name: str, content: str):
    with _lock:
        hist = bg_history()
        hist.append({"background": name, "content": content, "time": time.time()})
        write_json(BG_HISTORY_FILE, hist[-500:])


def pick_background(proj: dict) -> str:
    """Use the content's fixed background if set, otherwise pick randomly avoiding recent ones."""
    bgs = list_backgrounds()
    if not bgs:
        raise RuntimeError("Thư mục Backgrounds chưa có video nền nào (.mp4, .mov, .mkv, .webm...).")
    fixed = proj.get("background")
    if fixed:
        if fixed not in bgs:
            raise RuntimeError(f"Không tìm thấy background đã chọn '{fixed}' trong thư mục Backgrounds.")
        return fixed
    avoid_n = int(load_settings().get("avoid_repeat", 0))
    recent = [h["background"] for h in bg_history()][::-1]
    avoid = []
    for b in recent:
        if len(avoid) >= min(avoid_n, len(bgs) - 1):
            break
        if b not in avoid:
            avoid.append(b)
    choices = [b for b in bgs if b not in avoid] or bgs
    return random.choice(choices)
