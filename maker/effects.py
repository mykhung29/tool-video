"""Animation curves for comment images.

state() returns the transform of an image at local time t (seconds since it appeared).
The browser preview (web/effects.js) implements the same maths, keep both in sync.
dx/dy are fractions of the frame width/height.
"""
import math

EFFECTS_IN = {
    "none": "Không", "fade": "Fade-in", "pop": "Pop-in", "zoom_in": "Zoom-in",
    "slide_up": "Trượt lên", "slide_down": "Trượt xuống", "slide_left": "Trượt từ phải",
    "slide_right": "Trượt từ trái", "bounce": "Spring / Bounce", "drop": "Rơi nảy",
}
EFFECTS_OUT = {
    "none": "Không (cắt)", "fade": "Fade-out", "slide_up": "Trượt lên", "slide_left": "Trượt sang trái",
    "zoom_out": "Zoom-out", "pop_out": "Thu nhỏ",
}
EMPHASIS = {
    "none": "Không", "highlight": "Viền sáng (highlight)", "pulse": "Nhịp nhẹ (pulse)",
    "shake": "Rung nhẹ", "kenburns": "Phóng chậm",
}


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_in_cubic(p):
    return p ** 3


def ease_out_back(p, s=1.70158):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def spring(p):
    return 1 - math.exp(-6.5 * p) * math.cos(13.0 * p)


def bounce_out(p):
    n, d = 7.5625, 2.75
    if p < 1 / d:
        return n * p * p
    if p < 2 / d:
        p -= 1.5 / d
        return n * p * p + 0.75
    if p < 2.5 / d:
        p -= 2.25 / d
        return n * p * p + 0.9375
    p -= 2.625 / d
    return n * p * p + 0.984375


def state(seg, t):
    dur = seg["duration"]
    tin = max(seg["in_duration"], 0.01)
    tout = max(seg["out_duration"], 0.01)
    s, o, dx, dy, glow = 1.0, 1.0, 0.0, 0.0, 0.0
    p = clamp(t / tin)
    e = seg["effect_in"]
    if e == "fade":
        o = ease_out_cubic(p)
    elif e == "pop":
        s = 0.55 + 0.45 * ease_out_back(p)
        o = clamp(p * 3)
    elif e == "zoom_in":
        s = 0.82 + 0.18 * ease_out_cubic(p)
        o = ease_out_cubic(p)
    elif e == "slide_up":
        dy = (1 - ease_out_cubic(p)) * 0.35
        o = clamp(p * 2)
    elif e == "slide_down":
        dy = -(1 - ease_out_cubic(p)) * 0.35
        o = clamp(p * 2)
    elif e == "slide_left":
        dx = (1 - ease_out_cubic(p)) * 1.0
    elif e == "slide_right":
        dx = -(1 - ease_out_cubic(p)) * 1.0
    elif e == "bounce":
        s = max(0.01, spring(p))
        o = clamp(p * 4)
    elif e == "drop":
        dy = -(1 - bounce_out(p)) * 0.4
        o = clamp(p * 3)

    after = t - tin
    m = seg.get("emphasis", "none")
    if after > 0:
        if m == "pulse":
            s *= 1 + 0.022 * math.sin(2 * math.pi * after / 1.6)
        elif m == "highlight":
            glow = ease_out_cubic(clamp(after / 0.35)) * (0.8 + 0.2 * math.sin(2 * math.pi * after / 1.4))
        elif m == "shake" and after < 0.45:
            dx += 0.008 * math.sin(after * 70) * (1 - after / 0.45)
        elif m == "kenburns":
            s *= 1 + 0.05 * clamp(after / max(dur - tin, 0.1))

    q = clamp((t - (dur - tout)) / tout)
    if q > 0:
        x = seg["effect_out"]
        if x == "fade":
            o *= 1 - q
        elif x == "slide_up":
            dy -= ease_in_cubic(q) * 0.4
            o *= 1 - q
        elif x == "slide_left":
            dx -= ease_in_cubic(q) * 1.0
        elif x == "zoom_out":
            s *= 1 + 0.25 * ease_in_cubic(q)
            o *= 1 - q
        elif x == "pop_out":
            s *= 1 - 0.6 * ease_in_cubic(q)
            o *= 1 - q
        elif x == "none" and t >= dur:
            o = 0.0
    return {"scale": s, "opacity": clamp(o), "dx": dx, "dy": dy, "glow": glow}


OVERLAY_POS = {"top_right": "Góc trên phải", "top_left": "Góc trên trái",
               "bottom_right": "Góc dưới phải", "bottom_left": "Góc dưới trái",
               "above": "Phía trên bình luận", "below": "Phía dưới bình luận"}
_CORNERS = {"top_right": (1, -1), "top_left": (-1, -1), "bottom_right": (1, 1), "bottom_left": (-1, 1)}


def overlay_state(delay, t):
    """Stickers/GIFs pop in `delay` s after their comment, then bob gently. None while hidden."""
    ts = t - delay
    if ts < 0:
        return None
    p = clamp(ts / 0.35)
    s = max(0.01, ease_out_back(p, 2.2)) if p < 1 else 1.0
    dy = 0.004 * math.sin(2 * math.pi * (ts - 0.35) / 1.3) if p >= 1 else 0.0
    return {"scale": s, "opacity": clamp(p * 3), "dy": dy}


def overlay_center(pos, cx, cy, box_w, box_h, w, h):
    """Centre of a sticker/GIF of size (w, h) anchored on the transformed comment box."""
    if pos == "above":
        return cx, cy - box_h / 2 - h * 0.45
    if pos == "below":
        return cx, cy + box_h / 2 + h * 0.45
    sx, sy = _CORNERS.get(pos, (1, -1))
    return cx + sx * (box_w / 2 - 0.15 * w), cy + sy * box_h / 2


def vfx_state(t, dur):
    """Video effect clip: quick pop-in, short fade at the end. t is seconds since it started."""
    p = clamp(t / 0.25)
    q = clamp((t - (dur - 0.15)) / 0.15)
    return {"scale": 0.85 + 0.15 * ease_out_back(p), "opacity": clamp(p * 2) * (1 - q)}
