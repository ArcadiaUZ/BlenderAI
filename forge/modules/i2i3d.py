"""3-Bosqich: Image-To-3D serveriga rasm yuborish, ko'p seed variant, IoU tanlash.

Server: http://127.0.0.1:8742  (Image-To-3D/start_server.bat)
API:  POST /api/generate  -> {"job": "..."}
      GET  /api/job/{job} -> {"state": "running|done|error", "stage":..., "step":...}
      GET  /api/glb/{job}?texture=2048 -> GLB bytes
"""
import io
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import config

GRID = 192


def _deps():
    """numpy/trimesh/scipy/PIL — faqat kerak bo'lganda yuklanadi."""
    import importlib
    missing = [m for m in ("numpy", "trimesh", "scipy", "PIL")
               if not _has(m)]
    if missing:
        raise RuntimeError(
            "Yetishmayotgan paketlar: " + ", ".join(missing) +
            "\n  Yechim:  pip install -r forge/requirements.txt"
        )
    return (importlib.import_module("numpy"),
            importlib.import_module("trimesh"),
            importlib.import_module("scipy.ndimage"),
            importlib.import_module("PIL.Image"))


def _has(mod):
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _url(path):
    base = config.cfg("FORGE_I2I3D_URL", "http://127.0.0.1:8742").rstrip("/")
    return f"{base}{path}"


def alive(timeout=3):
    try:
        with urllib.request.urlopen(_url("/api/jobs"), timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _get(path, timeout=900):
    with urllib.request.urlopen(_url(path), timeout=timeout) as r:
        return r.read()


def _post_multipart(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    sep = f"--{boundary}\r\n".encode()
    parts = []
    for k, v in fields.items():
        parts.append(sep + f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    with open(file_path, "rb") as f:
        parts.append(
            sep
            + f'Content-Disposition: form-data; name="{file_field}"; '
              f'filename="{Path(file_path).name}"\r\n'.encode()
            + b"Content-Type: application/octet-stream\r\n\r\n"
            + f.read()
            + b"\r\n"
        )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        _url("/api/generate"), data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


# --------------------------------------------------------------- silhouette

def _normalize_to_grid(mask, grid=GRID):
    np, trimesh, ndimage, Image = _deps()
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return np.zeros((grid, grid), bool)
    sub = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape
    yi = (np.arange(grid) * (h / grid)).astype(np.int32).clip(0, h - 1)
    xi = (np.arange(grid) * (w / grid)).astype(np.int32).clip(0, w - 1)
    return sub[yi][:, xi]


def image_silhouette(path):
    np, trimesh, ndimage, Image = _deps()
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        alpha = np.array(im)[:, :, 3]
        if alpha.min() < 250:
            return alpha > 8
    rgb = np.array(im.convert("RGB")).astype(np.int16)
    h, w, _ = rgb.shape
    bgish = (rgb.min(axis=2) > 238) | (rgb.max(axis=2) < 17)
    border = np.zeros_like(bgish)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    lab, _ = ndimage.label(bgish)
    keep = set(np.unique(lab[bgish & border])) - {0}
    bg = np.isin(lab, list(keep)) if keep else np.zeros_like(bgish)
    fg = ~bg
    if fg.sum() < 0.02 * h * w:
        fg = np.ones((h, w), bool)
    return fg


def mesh_silhouettes(glb_bytes):
    np, trimesh, ndimage, Image = _deps()
    scene = trimesh.load(io.BytesIO(glb_bytes), file_type="glb",
                         force="mesh", process=False)
    v = np.asarray(scene.vertices, dtype=np.float64)
    if v.ndim != 2 or len(v) == 0:
        return []
    out = []
    for axis in range(3):
        other = [a for a in range(3) if a != axis]
        for flip in (1, -1):
            uv = v[:, other] * flip
            lo, hi = uv.min(axis=0), uv.max(axis=0)
            span = np.maximum(hi - lo, 1e-9)
            g = ((uv - lo) / span * (GRID - 1)).astype(np.int32)
            np.clip(g, 0, GRID - 1, out=g)
            splat = np.zeros(GRID * GRID, bool)
            splat[(g[:, 0] * GRID + g[:, 1])] = True
            splat = splat.reshape(GRID, GRID)
            # vertices zich, lekin teshiklar qolishi mumkin
            splat = ndimage.binary_closing(splat, np.ones((3, 3)))
            out.append(splat)
    return out


def iou(a, b):
    u = (a | b).sum() if hasattr(a, "sum") else 0
    n = (a & b).sum() if hasattr(a, "sum") else 0
    return float(n / u) if u else 0.0


# --------------------------------------------------------------- generation

def one(image_path, seed=0, steps=20, texture_steps=20, guidance=7.5,
        timeout=1800, progress=True):
    """Bitta variant. Qaytaradi: (job_id, glb_bytes, seconds) yoki (None, None, secs)."""
    fields = {
        "source": "512", "background": "0", "seed": str(seed),
        "steps": str(steps), "guidance": str(guidance),
        "texture_steps": str(texture_steps),
    }
    t0 = time.time()
    job = _post_multipart(fields, "image", image_path)["job"]
    last_stage = ""
    while True:
        info = json.loads(_get(f"/api/job/{job}").decode())
        st = info.get("state")
        if st == "error":
            if progress:
                config.say(f"      [XATO seed={seed}] {info.get('error')}")
            return None, None, time.time() - t0
        if st == "done":
            return job, _get(f"/api/glb/{job}?texture=2048"), time.time() - t0
        if progress and info.get("stage") and info["stage"] != last_stage:
            last_stage = info["stage"]
            config.say(f"      · {info['stage']} ({info.get('step',0)}/{info.get('total',0)})")
        if time.time() - t0 > timeout:
            if progress:
                config.say(f"      [TIMEOUT seed={seed}]")
            return None, None, time.time() - t0
        time.sleep(4)


def variants(image_path, n_seeds=4, steps=20, texture_steps=20, base_seed=0):
    """n_seeds ta variant yaratadi, har birining IoU bahosi bilan.
    Qaytaradi: [{'seed','job','iou','glb','seconds'}, ...]"""
    ref = _normalize_to_grid(image_silhouette(image_path))
    out = []
    for i in range(n_seeds):
        seed = base_seed + i
        config.say(f"  [3/5] variant {i + 1}/{n_seeds} (seed={seed})")
        job, glb, secs = one(image_path, seed=seed, steps=steps,
                             texture_steps=texture_steps)
        if job is None or not glb:
            continue
        score = max((iou(ref, s) for s in mesh_silhouettes(glb)), default=0.0)
        out.append({"seed": seed, "job": job, "iou": score, "glb": glb, "seconds": secs})
        config.say(f"      -> IoU {score:.3f}  ({secs / 60:.1f} min)")
    return out


def pick(part_id, proj, image_path, n_seeds=4, steps=20, texture_steps=20,
         keep_alts=2, min_iou=0.55, force=False):
    """Variantlar yaratib, eng yaxshisini saqlaydi. Qaytaradi: dict yoki None."""
    mdir = Path(proj) / "meshes"
    mdir.mkdir(parents=True, exist_ok=True)
    main = mdir / f"{part_id}.glb"
    meta_p = mdir / f"{part_id}.meta.json"
    meta = config.read_json(meta_p, None) or {}

    if main.exists() and not force and meta.get("iou", 0) >= min_iou:
        config.say(f"  [3/5] {part_id}: mavjud model (IoU {meta['iou']:.3f}) — qayta o'tkazilmadi")
        return meta

    res = variants(image_path, n_seeds=n_seeds, steps=steps,
                   texture_steps=texture_steps, base_seed=meta.get("next_seed", 0))
    if not res:
        config.say(f"  [3/5] {part_id}: HECH BIR VARIANT yaratilmadi")
        return None

    res.sort(key=lambda r: -r["iou"])
    best = res[0]
    main.write_bytes(best["glb"])

    for k, r in enumerate(res[1:1 + keep_alts]):
        (mdir / f"{part_id}.alt{k}_{r['iou']:.2f}_s{r['seed']}.glb").write_bytes(r["glb"])

    out = {
        "part": part_id, "job": best["job"], "seed": best["seed"],
        "iou": round(best["iou"], 4), "candidates": [
            {"seed": r["seed"], "iou": round(r["iou"], 4)} for r in res
        ],
        "glb": str(main), "next_seed": max(r["seed"] for r in res) + 1,
        "seconds": round(best["seconds"], 1),
    }
    config.write_json(meta_p, out)
    config.say(f"  [3/5] {part_id}: ENG YAXSHI IoU={best['iou']:.3f} seed={best['seed']} -> {main.name}")
    return out
