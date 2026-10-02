"""Umumiy sozlamalar: .env o'qish, yo'llar, log."""
import os
import sys
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent   # D:\AI\BlenderAI\forge
WORKSPACE = ROOT.parent                                  # D:\AI\BlenderAI
I2I3D = WORKSPACE / "Image-To-3D"
PROJECTS = ROOT / "projects"

_config_cache = None


def load_env():
    """forge/.env faylini o'qib atrof-muhitga joylaydi (mavjud qiymatni buzmaydi)."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    env_file = ROOT / ".env"
    data = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in data.items():
        os.environ.setdefault(k, v)
    # Kesh papkalarini oldindan yaratamiz - aks holda HF/Torch C: ga
    # qaytib ketishi mumkin (portable talab).
    for k in ("FORGE_CACHE_ROOT", "HF_HOME", "HF_HUB_CACHE", "TORCH_HOME"):
        p = data.get(k)
        if p:
            try:
                pathlib.Path(p).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
    _config_cache = {**os.environ, **data}
    return _config_cache


def cfg(key, default=None):
    env = load_env()
    return env.get(key) or default


def api_key():
    k = cfg("GEMINI_API_KEY") or cfg("GOOGLE_API_KEY")
    if not k or k.strip() == "":
        sys.exit("[XATO] GEMINI_API_KEY yo'q. forge/.env fayliga kalitni yozing.")
    return k.strip()


def blender_exe():
    p = cfg("FORGE_BLENDER", "")
    if p and pathlib.Path(p).exists():
        return p
    # umumiy joylashuvlarni qidirish
    cands = []
    for base in [r"C:\Program Files\Blender Foundation",
                 r"C:\Program Files (x86)\Blender Foundation"]:
        b = pathlib.Path(base)
        if b.exists():
            for d in sorted(b.iterdir(), reverse=True):
                cands.append(d / "blender.exe")
    for c in cands:
        if c.exists():
            return str(c)
    sys.exit("[XATO] Blender topilmadi. FORGE_BLENDER ni .env da ko'rsating.")


def project_dir(name):
    return PROJECTS / slugify(name)


def slugify(name):
    keep = "-_"
    out = "".join(c if (c.isalnum() or c in keep) else "-" for c in name.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-").lower()


def read_json(path, default=None):
    p = pathlib.Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def say(*a):
    print(*a, flush=True)
