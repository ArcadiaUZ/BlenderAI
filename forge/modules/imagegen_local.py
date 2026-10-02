"""Lokal rasm generatsiyasi: ComfyUI + Qwen-Image-2.1 (GGUF).

Nega bu kerak: Google AI Studio'da rasm kvotasi 0 bo'lsa ham
ishlaydi. Umuman API kalitiga bog'liq emas.

ComfyUI API:
  GET  /system_stats            -> serverni tekshirish
  POST /prompt                  -> {"prompt": {...graph...}} -> {"prompt_id": ...}
  GET  /history/{prompt_id}     -> natija ("outputs" -> images)
  GET  /view?filename=&subfolder=&type=output  -> rasm bytes
  POST /free                    -> {"unload_models": true, "free_memory": true}

Muhim: Image-To-3D ham GPU talab qiladi. `images` bosqichidan keyin
`free()` chaqiriladi, aks holda VRAM yetishmaydi.
"""
import json
import os
import random
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

DEFAULTS = {
    "COMFY_URL": "http://127.0.0.1:8188",
    # Nisbatiy yo'l: ComfyUI shu repo yonida bo'lishi kerak
    # (<repo>/ComfyUI). .env da absolyut yo'l bilan almashtirilishi mumkin.
    "FORGE_COMFY_PATH": str(config.WORKSPACE / "ComfyUI"),
    # 12 GB VRAM uchun byudjet: 3.995 + 6.020 + 0.644 = 10.66 GB og'irliklar,
    # qolgan ~1.6 GB aktivatsiyaga. Hammasi GPU'da, CPU offload yo'q.
    "FORGE_GGUF": "qwen_image_2.1_Q4_K_M.gguf",
    "FORGE_COMFY_CLIP": "qwen3vl_8b_w4a8.safetensors",
    "FORGE_COMFY_VAE": "qwen_image_2.1_vae_bf16.safetensors",
    "FORGE_COMFY_STEPS": "30",
    "FORGE_COMFY_RES": "1024",
    "FORGE_COMFY_RESERVE_VRAM": "0.5",
}


def opt(key, default=None):
    v = config.cfg(key, "")
    return (v or DEFAULTS.get(key, default)) if v not in (None,) else default


def url(path):
    return opt("COMFY_URL").rstrip("/") + path


def comfy_dir():
    return Path(opt("FORGE_COMFY_PATH"))


# --------------------------------------------------------------- server

def alive(timeout=4):
    try:
        with urllib.request.urlopen(url("/system_stats"), timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


_proc = None


def ensure_server(timeout=180, autostart=True):
    """ComfyUI ishlayotganini ta'minlaydi. Qaytaradi: True/False."""
    global _proc
    if alive():
        return True
    if not autostart:
        return False
    root = comfy_dir()
    py = root / "venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path("python")
    if not (root / "main.py").exists():
        config.say(f"  [XATO] ComfyUI topilmadi: {root}")
        return False
    port = opt("COMFY_URL").rstrip("/").rsplit(":", 1)[-1]
    # --highvram BIRINCHI ISHLATILMAYDI: 12 GB GPU'da u barcha modellarni
    # bir vaqtda ushlab olib, RAM'ga suradi va "access violation" bilan
    # crash bo'ladi. Standart "smart memory" rejimi hisobni GPU'da olib
    # boradi (VRAM peak ~11.9/12.3 GB), faqat boshidan fayl kesh sifatida
    # xotirada ushlab turadi - bu bo'sha evriladigan mmap, RAM to'lmaydi.
    cmd = [str(py), "main.py", "--port", str(port), "--listen", "127.0.0.1",
           "--reserve-vram", opt("FORGE_COMFY_RESERVE_VRAM"),
           "--disable-pinned-memory",     # 15.8 GB RAM da pinned kerak emas
           "--disable-auto-launch"]
    log = open(root / "comfyui.log", "ab")
    config.say(f"  ComfyUI ishga tushirilmoqda ({root}\\venv\\...) ...")
    _proc = subprocess.Popen(cmd, cwd=str(root), stdout=log, stderr=log,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if alive(timeout=2):
            config.say("  ComfyUI tayyor.")
            return True
        if _proc.poll() is not None:
            break
        time.sleep(3)
    config.say(f"  [XATO] ComfyUI ishga tushmadi. Jurnal: {root / 'comfyui.log'}")
    return False


def _post_json(path, payload, timeout=60):
    req = urllib.request.Request(
        url(path), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _trim_comfy_working_set():
    """ComfyUI jarayonining resident RAM'ini bo'shatadi (bo'sha evriladigan
    mmap sahifalarini Windows'ga qaytaradi). Model fayllari saqlanib qoladi,
    faqat xotira to'silmaydi. Xato bo'lsa ahamiyatsiz."""
    try:
        import ctypes
        import subprocess
        # ComfyUI portini eshlab turgan PID ni topamiz
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True,
            text=True, timeout=20).stdout
        port = opt("COMFY_URL").rsplit(":", 1)[-1].strip("/")
        pid = None
        for line in out.splitlines():
            if f":{port} " in line and "LISTENING" in line.upper():
                parts = line.split()
                if len(parts) >= 5:
                    pid = int(parts[-1])
                    break
        if not pid:
            return False
        PROCESS_SET_QUOTA = 0x0100
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_SET_QUOTA, False, pid)
        if not h:
            return False
        try:
            k32.SetProcessWorkingSetSize(h, ctypes.c_size_t(-1),
                                         ctypes.c_size_t(-1))
        finally:
            k32.CloseHandle(h)
        return True
    except Exception:
        return False


def free():
    """Modellarni VRAM/RAM dan tushiradi — keyingi ishdan oldin va
    Image-To-3D boshlashidan oldin chaqiriladi."""
    ok = False
    try:
        _post_json("/free", {"unload_models": True, "free_memory": True}, timeout=60)
        ok = True
    except Exception:
        pass
    time.sleep(1.0)
    if _trim_comfy_working_set():
        ok = True
    return ok


# --------------------------------------------------------------- monitoring

def _nvidia_smi(fields):
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return None
        first = out.stdout.strip().split("\n")[0]
        return [int(x.strip()) for x in first.split(",")]
    except Exception:
        return None


def gpu_state():
    """(VRAM ishlatilgan MB, jami MB, RAM ishlatilgan MB) yoki None."""
    v = _nvidia_smi("memory.used,memory.total")
    r = None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        r = (st.ullTotalPhys - st.ullAvailPhys) // (1024 * 1024)
    except Exception:
        pass
    return (v[0], v[1], r) if v else None


class _Watch:
    """Generatsiya davomida VRAM/RAM oqimini kuzatadi."""

    def __init__(self, label=""):
        self.label = label
        self.peak_vram = 0
        self.peak_ram = 0
        self._stop = False
        self._t = None

    def __enter__(self):
        import threading

        def loop():
            while not self._stop:
                s = gpu_state()
                if s:
                    self.peak_vram = max(self.peak_vram, s[0])
                    if s[2]:
                        self.peak_ram = max(self.peak_ram, s[2])
                time.sleep(1.5)

        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop = True
        if self._t:
            self._t.join(timeout=3)
        return False

    def line(self, seconds=None):
        t = f" ({seconds:.0f}s)" if seconds else ""
        return (f"VRAM peak {self.peak_vram} MB, "
                f"RAM peak {self.peak_ram} MB{t}")


# --------------------------------------------------------------- workflow

def build_graph(prompt, seed, steps, res, negative="", filename_prefix="forge"):
    unet_name = opt("FORGE_GGUF")
    clip_name = opt("FORGE_COMFY_CLIP")
    vae_name = opt("FORGE_COMFY_VAE")
    # .gguf text encoder -> ComfyUI-GGUF loader, aks holda standart CLIPLoader
    clip_node = "CLIPLoaderGGUF" if clip_name.lower().endswith(".gguf") else "CLIPLoader"
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet_name}},
        "2": {"class_type": clip_node, "inputs": {
            "clip_name": clip_name, "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "prompt": prompt,
            "negative_prompt": negative, "resolution": int(res)}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {
            "width": int(res), "height": int(res), "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1],
            "latent_image": ["5", 0], "seed": int(seed), "steps": int(steps),
            "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
            "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {
            "images": ["7", 0], "filename_prefix": filename_prefix}},
    }


# --------------------------------------------------------------- generate

def _get(path, timeout=120):
    with urllib.request.urlopen(url(path), timeout=timeout) as r:
        return r.read()


def _get_json(path, timeout=120):
    return json.loads(_get(path, timeout).decode())


def check_nodes():
    """Kerakli node'lar ComfyUI'da bormi tekshiradi. Qaytaradi: (ok, xabar)."""
    try:
        obj = _get_json("/object_info", timeout=60)
    except Exception as e:
        return False, f"ComfyUI javob bermiyapti: {str(e)[:120]}"
    need = ["UnetLoaderGGUF", "VAELoader", "TextEncodeQwenImage21",
            "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"]
    clip = opt("FORGE_COMFY_CLIP")
    need.append("CLIPLoaderGGUF" if clip.lower().endswith(".gguf") else "CLIPLoader")
    missing = [n for n in need if n not in obj]
    if missing:
        return False, "yo'q node'lar: " + ", ".join(missing)
    return True, "barcha node'lar mavjud"


def check_models():
    """Model fayllari joyida va ComfyUI ularni ko'rayotganini tekshiradi."""
    try:
        obj = _get_json("/object_info", timeout=60)
    except Exception as e:
        return False, str(e)[:120]
    want_unet = opt("FORGE_GGUF")
    want_clip = opt("FORGE_COMFY_CLIP")
    want_vae = opt("FORGE_COMFY_VAE")

    def opts(node, key):
        try:
            return (obj[node]["input"]["required"][key][0])
        except Exception:
            return []

    clip = want_clip
    clip_node = "CLIPLoaderGGUF" if clip.lower().endswith(".gguf") else "CLIPLoader"
    u = opts("UnetLoaderGGUF", "unet_name")
    c = opts(clip_node, "clip_name")
    v = opts("VAELoader", "vae_name")
    miss = []
    if want_unet not in u:
        miss.append(f"unet: {want_unet} (topildi: {u or 'yoq'})")
    if want_clip not in c:
        miss.append(f"clip: {want_clip} (topildi: {c or 'yoq'})")
    if want_vae not in v:
        miss.append(f"vae: {want_vae} (topildi: {v or 'yoq'})")
    if miss:
        return False, "; ".join(miss)
    return True, f"{want_unet} + {want_clip} + {want_vae}"


def generate(prompt, out_path, seed=None, steps=None, res=None, negative="",
             filename_prefix="forge", timeout=900, progress=True, pre_free=True):
    """Rasmlarni PNG fayliga saqlaydi. Qaytaradi: out_path

    `pre_free`: har generatsiyadan oldin modellarni bo'shatadi. Bu shart —
    aks holda oldingi ishning model keshi RAM'da qoladi va keyingi
    ish "not enough memory" bilan yiqiladi.
    """
    if not ensure_server():
        raise RuntimeError("ComfyUI ishlamadi")
    if pre_free:
        free()
        time.sleep(1.5)
    seed = random.randrange(0, 2 ** 31 - 1) if seed is None else int(seed)
    steps = int(steps or opt("FORGE_COMFY_STEPS"))
    res = int(res or opt("FORGE_COMFY_RES"))

    graph = build_graph(prompt, seed, steps, res, negative, filename_prefix)
    try:
        res_json = _post_json("/prompt", {"prompt": graph}, timeout=120)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"ComfyUI promptni qabul qilmadi: {body[:600]}")
    if "error" in res_json:
        raise RuntimeError(f"ComfyUI xatosi: {json.dumps(res_json['error'])[:600]}")
    pid = res_json.get("prompt_id")
    if not pid:
        raise RuntimeError(f"ComfyUI prompt_id bermadi: {res_json}")

    t0 = time.time()
    with _Watch() as watch:
        while time.time() - t0 < timeout:
            ok, err = _await(pid, out_path, t0, timeout, progress)
            if ok:
                if progress:
                    config.say(f"      tayyor ({time.time() - t0:.0f}s, seed={seed})")
                    config.say(f"      {watch.line(time.time() - t0)}")
                return ok
            if err:
                raise RuntimeError(err)
            time.sleep(2)
    raise RuntimeError(f"ComfyUI vaqtida tayyor bo'lmadi ({timeout}s)")


def _await(pid, out_path, t0, timeout, progress):
    """(tayyor_bool, xato_str) — tayyor bo'lmasa (False, None)."""
    hist = _get_json(f"/history/{pid}", timeout=60)
    entry = hist.get(pid)
    if not entry:
        return False, None
    status = entry.get("status", {})
    if status.get("status_str") == "error":
        return False, "ComfyUI generatsiya xatosi: " + json.dumps(status)[:500]
    for out in (entry.get("outputs") or {}).values():
        for im in (out.get("images") or []):
            q = (f"/view?filename={urllib.parse.quote(im['filename'])}"
                 f"&subfolder={urllib.parse.quote(im.get('subfolder', ''))}"
                 f"&type={im.get('type', 'output')}")
            data = _get(q, timeout=300)
            out_path = os.fspath(out_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(data)
            return True, None
    if status.get("completed"):
        return False, "ComfyUI rasm qaytarmadi: " + json.dumps(status)[:300]
    return False, None


def test():
    """Tez sinov: kichik rasm yaratib ko'radi."""
    try:
        if not ensure_server():
            return False, "ComfyUI ishga tushmadi"
        ok, msg = check_nodes()
        if not ok:
            return False, msg
        ok, msg = check_models()
        if not ok:
            return False, "model: " + msg
        p = config.PROJECTS / "_comfy_test.png"
        generate("a simple grey cube on a pure white background, "
                 "studio product photo, no text",
                 p, seed=1, steps=4, res=512, progress=False)
        return True, f"sinov rasmi: {p}"
    except Exception as e:
        return False, str(e)[:500]
