"""Read the comment text out of a screenshot (EasyOCR, Vietnamese + English, runs offline).

Facebook/TikTok/YouTube comment screenshots carry more than the comment: a header line
with the name and age ("Redley Dao · 22h"), an action row ("Like  Reply  😆 2") and often a
sliver of the previous comment. extract_text() keeps only the comment body; images that do
not look like a comment (a post, a caption) keep all their text.
"""
import re
import threading
import warnings

import numpy as np
from PIL import Image

_reader = None
_lock = threading.Lock()


class OCRError(RuntimeError):
    pass


def _get_reader():
    global _reader
    with _lock:
        if _reader is None:
            try:
                import easyocr
            except ImportError as e:
                raise OCRError("Chưa cài EasyOCR. Chạy: .venv\\Scripts\\pip install easyocr") from e
            try:
                # first use downloads the detection/recognition models (~100 MB) into ~/.EasyOCR
                warnings.filterwarnings("ignore", module="torch")  # noisy CPU-only warnings
                _reader = easyocr.Reader(["vi", "en"], gpu=False, verbose=False)
            except Exception as e:
                raise OCRError(f"Không khởi tạo được EasyOCR (lần đầu cần Internet để tải model): {e}") from e
        return _reader


# "· 22h", "1 giờ", "3 ngày", "2w", "Vừa xong", "Just now", "Edited" ...
TIME_RE = re.compile(
    r"(^|[\s·•.])(\d{1,3}\s?(h|m|d|w|y|g|giờ|phút|ngày|tuần|tháng|năm|hr|hrs|min|mins|wk|wks)"
    r"|vừa xong|just now|yesterday|hôm qua)\s*$", re.I)
ACTION_WORDS = {"reply", "trả lời", "phản hồi", "like", "thích", "share", "chia sẻ", "xem bản dịch",
                "see translation", "hide", "ẩn", "edited", "đã chỉnh sửa", "author", "tác giả",
                "top fan", "fan cứng", "xem thêm", "see more", "view more replies", "xem thêm phản hồi"}


def _is_action_row(text: str) -> bool:
    t = re.sub(r"[^\w\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return True
    if any(t == w or t.startswith(w + " ") or t.endswith(" " + w) for w in ACTION_WORDS):
        return True
    words = t.split()
    return len(words) <= 4 and any(w in ("reply", "like", "share") for w in words)


def _lines(results):
    """Group EasyOCR word boxes into text lines, top to bottom."""
    items = []
    for box, text, conf in results:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append({"y0": min(ys), "y1": max(ys), "x": min(xs), "text": text.strip(), "conf": conf})
    items.sort(key=lambda i: (i["y0"] + i["y1"]) / 2)
    lines = []
    for it in items:
        mid = (it["y0"] + it["y1"]) / 2
        if lines and abs(mid - lines[-1]["mid"]) < 0.5 * (it["y1"] - it["y0"]):
            lines[-1]["items"].append(it)
        else:
            lines.append({"mid": mid, "items": [it]})
    out = []
    for ln in lines:
        words = sorted(ln["items"], key=lambda i: i["x"])
        out.append(" ".join(w["text"] for w in words if w["text"]))
    return [l for l in out if l.strip()]


def comment_body(lines):
    """Pick the comment text out of OCR lines (see module docstring)."""
    # the name/time header is short ("Hải Phạm · 1h") and near the top; a sentence that
    # merely ends in "… 2 năm" is not one
    header = next((i for i, l in enumerate(lines[:3])
                   if TIME_RE.search(l) and ("·" in l or "•" in l or len(l.split()) <= 5)), None)
    actions = [i for i, l in enumerate(lines) if _is_action_row(l)]
    if header is None and not actions:
        return lines  # not a comment screenshot: keep everything
    start = header + 1 if header is not None else 0
    if header is None and actions and actions[0] > 0:
        start = 1  # no visible time: the first line is the name
    while start < len(lines) and _is_action_row(lines[start]):
        start += 1  # leftovers of the comment above
    end = next((i for i in actions if i >= start), len(lines))
    return lines[start:end]


def _fix_case(word: str) -> str:
    """'vỎ' -> 'vỏ', 'sƠn' -> 'sơn': an uppercase letter after a lowercase one is an OCR slip."""
    chars = list(word)
    for i in range(1, len(chars)):
        if chars[i].isupper() and chars[i - 1].islower():
            chars[i] = chars[i].lower()
    return "".join(chars)


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = " ".join(_fix_case(w) for w in text.split(" "))
    text = re.sub(r"(?<=\d)[Oo](?=\d|[kK]\b|\b)", "0", text)        # 12Ok -> 120k
    text = re.sub(r"(?<=\d)[Oo](?=\d|[kK]\b|\b)", "0", text)        # second O in 1OO
    text = re.sub(r"\b[Il](?=(tr|k|m|tỷ|củ)\b)", "1", text)          # Itr -> 1tr
    text = re.sub(r"[\"“”]{2,}", " ", text)                          # emoji read as ""
    text = re.sub(r"(?<=\w)[\"“”](?=[!?])", "", text)                # lạnh"! -> lạnh!
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?;:%)])", r"\1", text)
    return text


def extract_text(path) -> str:
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        raise OCRError(f"Không mở được ảnh: {e}") from e
    # small screenshots read noticeably better when enlarged
    if img.height < 400:
        k = min(3.0, 400 / img.height)
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
    reader = _get_reader()
    try:
        results = reader.readtext(np.asarray(img), paragraph=False)
    except Exception as e:
        raise OCRError(f"Lỗi khi đọc chữ: {e}") from e
    return clean(" ".join(comment_body(_lines(results))))
