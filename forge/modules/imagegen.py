"""2-Bosqich: har bir qism uchun referens rasm (Gemini Nano Banana).

MUHIM: Image-To-3D faqat bitta rasmni oladi (single-view). Shuning uchun
har bir qismga KANONIK 3/4 ko'rinish generatsiya qilinadi — orqa tomon
taxmin qilinadi, shuning uchun burchak to'g'ri bo'lishi kritik.

Rasm foni toza oq bo'lishi kerak (siluet ajratish uchun). Gemini ba'zan
fon beradi -> `cutout()` orqali oq fonni alpha'ga aylantiramiz.
"""
import os
from pathlib import Path

from . import config, gemini, imagegen_local

# Siluet uchun qo'shimcha ko'rsatma: har doim bir xil burchak
ANGLE_SUFFIX = (
    "\n\nCamera: fixed three-quarter front view, camera slightly above the "
    "object center, long focal length (no perspective distortion), the whole "
    "part fully visible and centered, ~10% margin around it."
)

BG_SUFFIX = (
    "\n\nBackground: perfectly uniform pure white (#FFFFFF), no gradient, "
    "no shadow on the background, no floor plane, no vignette."
)


def prompt_for(part, view="hero"):
    base = part.get("image_prompt") or part.get("description") or part["name"]
    p = base
    if part.get("material"):
        p += f". Material: {part['material']}"
    if part.get("color"):
        p += f", base color {part['color']}"
    p += ". Single isolated part, one object only, no other objects, no text, no labels, no watermark, no frame"
    p += BG_SUFFIX
    if view == "hero":
        p += ANGLE_SUFFIX
    elif view == "front":
        p += "\n\nCamera: orthographic front view, camera at object center height."
    elif view == "side":
        p += "\n\nCamera: orthographic right side view, camera at object center height."
    elif view == "top":
        p += "\n\nCamera: orthographic top view, looking straight down."
    return p


def backend():
    """Qaysi rasm backendi ishlatilishi: 'local' (ComfyUI) yoki 'gemini'."""
    b = (config.cfg("FORGE_IMAGE_BACKEND", "local") or "local").strip().lower()
    return b if b in ("local", "gemini") else "local"


def _generate(prompt, dest, view, seed=None):
    """Tanlangan backend orqali rasm yaratadi."""
    if backend() == "gemini":
        gemini.image(prompt, dest, aspect="1:1")
    else:
        imagegen_local.generate(prompt, dest, seed=seed,
                                filename_prefix="forge")
    cutout(dest)


def generate_all(spec, proj, views=("hero",), force=False):
    """spec['parts'] uchun rasm yaratadi. Qaytaradi: {part_id: [path,...]}"""
    imgdir = Path(proj) / "images"
    imgdir.mkdir(parents=True, exist_ok=True)
    out = {}
    parts = spec["parts"]
    for idx, part in enumerate(parts, 1):
        paths = []
        for view in views:
            dest = imgdir / f"{part['id']}.{view}.png"
            if dest.exists() and not force:
                paths.append(dest)
                continue
            config.say(f"  [2/5] rasm {idx}/{len(parts)}  {part['id']} [{view}]"
                       f"  ({backend()})")
            try:
                _generate(prompt_for(part, view), dest, view)
            except Exception as e:
                config.say(f"      [XATO] {part['id']}: {str(e)[:200]}")
                paths.append(None)
                continue
            paths.append(dest)
        out[part["id"]] = paths
    return out


def cutout(path, thresh=238):
    """Oq fonni alpha kanalga aylantiradi (siluet ajratish uchun zaruriy)."""
    from PIL import Image
    p = Path(path)
    im = Image.open(p).convert("RGBA")
    px = im.load()
    w, h = im.size
    # 4-burchakdan rasm chegarasi rangi
    corners = [px[0, 0][:3], px[w - 1, 0][:3], px[0, h - 1][:3], px[w - 1, h - 1][:3]]
    br = sum(c[0] for c in corners) // 4
    bg = sum(c[1] for c in corners) // 4
    bb = sum(c[2] for c in corners) // 4
    changed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > thresh and g > thresh and b > thresh:
                px[x, y] = (r, g, b, 0)
                changed += 1
            elif abs(r - br) < 14 and abs(g - bg) < 14 and abs(b - bb) < 14:
                px[x, y] = (r, g, b, 0)
                changed += 1
    if changed < 0.02 * w * h:
        return False  # fon topilmadi — rasm butunlay boshqa bo'lishi mumkin
    im.save(p)
    return True


def validate_alpha(path, min_foreground=0.05, max_foreground=0.93):
    """Siluet ajratilishi mumkinligini tekshiradi. Qaytaradi: (ok, xabar, ulush)."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    px = list(a.getdata())
    n = len(px)
    fg = sum(1 for v in px if v > 8) / n
    if fg < min_foreground:
        return False, f"foreground juda kichik ({fg:.1%})", fg
    if fg > max_foreground:
        return False, f"foreground juda katta ({fg:.1%}) — fon ajratilmagan", fg
    return True, "ok", fg


def regenerate_with_feedback(part, path, problem, view="hero"):
    """QC muammosini prompt'ga qaytarib, yangi rasm yasash."""
    p = prompt_for(part, view)
    p += (f"\n\nIMPORTANT FIX: previous render failed because {problem}. "
          f"Make sure the object is clearly separated from a completely "
          f"white background and occupies the center of the frame.")
    dest = Path(path)
    if dest.exists():
        dest.unlink()
    _generate(p, dest, view)
    return dest
