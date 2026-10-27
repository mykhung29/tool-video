"""Local HTTP API + static web UI."""
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import audio, ffmpeg, ocr, projects, sfx, tts
from .effects import EFFECTS_IN, EFFECTS_OUT, EMPHASIS, OVERLAY_POS
from .jobs import get_queue
from .settings import (PREVIEW_DIR, PROJECTS_DIR, TTS_CACHE_DIR, WEB_DIR, ensure_dirs, load_settings,
                       read_json, save_settings, write_json)
from .timeline import TimelineError, build, segment_media_url

app = FastAPI(title="Video Maker")


@app.on_event("startup")
def startup():
    ensure_dirs()
    sfx.ensure_builtin()
    sfx.seed_folder(load_settings()["sfx_dir"])
    # jobs do not survive a restart: anything left mid-render is reported as interrupted
    for f in PROJECTS_DIR.glob("*.json"):
        p = read_json(f, None)
        if p and p.get("status") in ("queued", "rendering"):
            p["status"] = "error" if p["status"] == "rendering" else "new"
            if p["status"] == "error":
                p["error"] = "Bị gián đoạn do ứng dụng đã tắt khi đang dựng."
            write_json(f, p)
    for f in PREVIEW_DIR.glob("*.part.mp4"):
        f.unlink(missing_ok=True)
    get_queue()


@app.exception_handler(Exception)
async def on_error(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc) or exc.__class__.__name__})


def _err(e, code=400):
    raise HTTPException(status_code=code, detail=str(e))


# ---- settings & metadata --------------------------------------------------

@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def post_settings(data: dict = Body(...)):
    return save_settings(data)


def _duration(path):
    try:
        return ffmpeg.probe(path)["duration"]
    except Exception:
        return 0


@app.get("/api/meta")
def meta():
    s = load_settings()
    bgs = []
    for b in projects.list_backgrounds():
        try:
            d = ffmpeg.probe(Path(s["backgrounds_dir"]) / b)["duration"]
        except Exception:
            d = 0
        bgs.append({"name": b, "duration": d})
    return {
        "voices": tts.list_voices(s["tts_provider"]),
        "effects_in": EFFECTS_IN, "effects_out": EFFECTS_OUT, "emphasis": EMPHASIS,
        "sfx": sfx.list_sfx(s["sfx_dir"]),
        "stickers": projects.list_stickers(),
        "gifs": projects.list_gifs(),
        "vfx": [{"name": v, "duration": _duration(Path(s["vfx_dir"]) / v)} for v in projects.list_vfx()],
        "overlay_pos": OVERLAY_POS,
        "backgrounds": bgs,
        "music": projects.list_music(),
        "bg_history": projects.bg_history()[-30:][::-1],
    }


@app.post("/api/voices/refresh")
def refresh_voices():
    return tts.list_voices(load_settings()["tts_provider"], refresh=True)


# ---- contents --------------------------------------------------------------

@app.get("/api/contents")
def contents():
    s = load_settings()
    if not Path(s["contents_dir"]).is_dir():
        _err(f"Thư mục Contents không tồn tại: {s['contents_dir']}", 404)
    return projects.scan_contents()


@app.get("/api/contents/{name}")
def get_content(name: str):
    try:
        proj = projects.load_project(name)
    except FileNotFoundError as e:
        _err(e, 404)
    return {"project": proj, "effective": projects.effective_settings(proj)}


@app.put("/api/contents/{name}")
def put_content(name: str, data: dict = Body(...)):
    try:
        proj = projects.save_project(name, data)
    except FileNotFoundError as e:
        _err(e, 404)
    return {"project": proj, "effective": projects.effective_settings(proj)}


def _safe(name):
    return re.sub(r"[^0-9A-Za-z_-]+", "_", name)


@app.post("/api/contents/{name}/timeline")
def content_timeline(name: str, data: dict = Body(default={})):
    """Build the timeline (synthesising voices) and a mixed audio track for the browser preview."""
    try:
        proj = projects.load_project(name)
    except FileNotFoundError as e:
        _err(e, 404)
    s = load_settings()
    try:
        tl = build(proj, auto_ocr=False)   # the editor runs OCR itself (/ocr) so it can show progress
    except TimelineError as e:
        _err(e)
    bgs = projects.list_backgrounds()
    bg = proj.get("background") or data.get("background")
    if bg not in bgs:
        bg = proj.get("last_background") if proj.get("last_background") in bgs else (random.choice(bgs) if bgs else None)
    offset = 0.0
    bg_path = Path(s["backgrounds_dir"]) / bg if bg else None
    if bg_path:
        dur = ffmpeg.probe(bg_path)["duration"]
        if dur > tl["total"] + 1:
            offset = random.uniform(0, dur - tl["total"] - 0.5)
    wav = PREVIEW_DIR / f"{_safe(name)}_mix.wav"
    try:
        music = audio.choose_music(tl["settings"])
        info = audio.mix(tl, wav, background=bg_path, bg_offset=offset, music_path=music)
    except Exception as e:
        _err(f"Lỗi trộn âm thanh: {e}")
    return {
        "segments": [segment_media_url(sg) for sg in tl["segments"]],
        "total": tl["total"],
        "audio": f"/media/preview/{wav.name}?v={int(time.time() * 1000)}",
        "background": bg, "bg_offset": offset, "music": info["music"],
    }


@app.post("/api/contents/{name}/ocr")
def content_ocr(name: str, data: dict = Body(...)):
    """Read the comment text from one image. The editor stores the result itself."""
    try:
        path = projects.content_dir(name) / data.get("file", "")
    except FileNotFoundError as e:
        _err(e, 404)
    if not path.is_file():
        _err("Không tìm thấy ảnh", 404)
    try:
        return {"text": ocr.extract_text(path)}
    except ocr.OCRError as e:
        _err(e)


@app.post("/api/contents/{name}/random_bg")
def random_bg(name: str):
    try:
        proj = projects.load_project(name)
        proj = dict(proj, background=None)
        return {"background": projects.pick_background(proj)}
    except Exception as e:
        _err(e)


@app.post("/api/tts/test")
def tts_test(data: dict = Body(...)):
    s = load_settings()
    d = s["defaults"]
    try:
        path, dur = tts.get_clip(data.get("text", ""), data.get("voice") or d["voice"],
                                 data.get("rate", d["rate"]), data.get("pitch", d["pitch"]), s["tts_provider"])
    except tts.TTSError as e:
        _err(e)
    return {"url": f"/media/tts/{path.name}", "duration": dur}


# ---- queue -----------------------------------------------------------------

@app.get("/api/queue")
def queue_state():
    return get_queue().snapshot()


@app.post("/api/queue/add")
def queue_add(data: dict = Body(...)):
    names = [n for n in data.get("names", []) if isinstance(n, str)]
    if not names:
        _err("Chưa chọn content nào.")
    return {"added": get_queue().add(names, preview=bool(data.get("preview")))}


@app.post("/api/queue/stop")
def queue_stop():
    get_queue().stop()
    return get_queue().snapshot()


@app.post("/api/queue/resume")
def queue_resume():
    get_queue().resume()
    return get_queue().snapshot()


@app.post("/api/queue/retry")
def queue_retry():
    return {"retried": get_queue().retry_failed()}


@app.post("/api/queue/retry_errors")
def queue_retry_content_errors():
    """Queue every content whose last render failed (also after an app restart)."""
    names = [c["name"] for c in projects.scan_contents() if c["status"] == "error"]
    get_queue().resume()
    return {"added": get_queue().add(names)}


@app.post("/api/queue/clear")
def queue_clear():
    get_queue().clear_finished()
    return get_queue().snapshot()


@app.delete("/api/queue/{job_id}")
def queue_remove(job_id: str):
    return {"ok": get_queue().remove(job_id)}


# ---- local helpers ----------------------------------------------------------

PICK_SCRIPT = (
    "import sys, tkinter as tk\nfrom tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "p = filedialog.askdirectory(initialdir=sys.argv[1] if len(sys.argv) > 1 else None, title='Chọn thư mục')\n"
    "sys.stdout.write(p or '')\n"
)


@app.post("/api/pick_folder")
def pick_folder(data: dict = Body(default={})):
    init = data.get("initial") or ""
    res = subprocess.run([sys.executable, "-c", PICK_SCRIPT, init], capture_output=True, text=True,
                         encoding="utf-8")
    path = res.stdout.strip()
    return {"path": str(Path(path)) if path else None}


@app.post("/api/open")
def open_path(data: dict = Body(...)):
    p = Path(data.get("path", ""))
    if not p.exists():
        _err(f"Không tồn tại: {p}", 404)
    if data.get("select") and p.is_file() and os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        os.startfile(str(p))  # noqa: windows only
    return {"ok": True}


# ---- media -------------------------------------------------------------------

def _serve(base, name):
    base = Path(base).resolve()
    p = (base / name).resolve()
    if base not in p.parents or not p.is_file():
        raise HTTPException(404, "Không tìm thấy file")
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@app.get("/media/bg/{name}")
def media_bg(name: str):
    return _serve(load_settings()["backgrounds_dir"], name)


@app.get("/media/sticker/{name}")
def media_sticker(name: str):
    return _serve(load_settings()["stickers_dir"], name)


@app.get("/media/vfx/{name}")
def media_vfx(name: str):
    return _serve(load_settings()["vfx_dir"], name)


@app.get("/media/gif/{name}")
def media_gif(name: str):
    return _serve(load_settings()["gifs_dir"], name)


@app.get("/media/music/{name}")
def media_music(name: str):
    return _serve(load_settings()["music_dir"], name)


@app.get("/media/content/{content}/{name}")
def media_content(content: str, name: str):
    try:
        return _serve(projects.content_dir(content), name)
    except FileNotFoundError:
        raise HTTPException(404, "Không tìm thấy content")


@app.get("/media/tts/{name}")
def media_tts(name: str):
    return _serve(TTS_CACHE_DIR, name)


@app.get("/media/preview/{name}")
def media_preview(name: str):
    return _serve(PREVIEW_DIR, name)


@app.get("/media/sfx/{name}")
def media_sfx(name: str):
    p = sfx.resolve_sfx(name, load_settings()["sfx_dir"])
    if not p:
        raise HTTPException(404, "Không có hiệu ứng âm thanh")
    return FileResponse(p)


@app.get("/media/output")
def media_output(path: str):
    p = Path(path).resolve()
    base = Path(load_settings()["output_dir"]).resolve()
    if p.suffix.lower() != ".mp4" or not p.is_file() or (base not in p.parents and PREVIEW_DIR.resolve() not in p.parents):
        raise HTTPException(404, "Không tìm thấy video")
    return FileResponse(p)


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
