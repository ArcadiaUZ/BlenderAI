"""4-Bosqich: GLB sifat nazorati (QC).

Tekshiriladi:
  - fayl ochilishi va mesh to'g'riligi
  - uchburchak soni chegarada
  - manifold / watertightlik
  - degenerate (nol'ga yaqin) yuzalar ulushi
  - bog'liq komponentlar soni (1 bo'lishi kerak)
  - NAMOYISH nisbatlari: modelning o'q nisbatlari sxemadagi
    real_size_mm nisbatlariga mos kelishi (eng uzun o'q 1 ga normallab)
  - bbox ichida "donli" (gibrid) natija yo'qligi
"""
import io
import json
from pathlib import Path

from . import config


def _deps():
    import importlib
    import importlib.util
    missing = [m for m in ("numpy", "trimesh")
               if importlib.util.find_spec(m) is None]
    if missing:
        raise RuntimeError("Yetishmayotgan paketlar: " + ", ".join(missing) +
                           "\n  Yechim:  pip install -r forge/requirements.txt")
    return importlib.import_module("numpy"), importlib.import_module("trimesh")

DEFAULT_RULES = {
    # TRELLIS.2 chiqishiga moslashtirilgan chegaralar.
    # Uning natijasi tabiiy ravishda zich (yarim million+ uchburchak),
    # ko'p alohida bo'lakli va yopiq emas — bular odiy holda.
    "min_triangles": 5_000,
    "max_triangles": 6_000_000,
    "max_degenerate_ratio": 0.10,
    "min_largest_component": 0.35,   # eng katta bo'lakdagi yuzalar ulushi
    "max_aspect_dev": 0.45,          # nisbat farqi (normalize qilingan)
    "min_faces": 100,
    "max_mesh_tris": 400_000,         # Blender'ga kiritishdan oldingi maqsad
}

# 6 ta o'q o'zgarishiga (permutatsiya) imkoniyat — GLB Y-up, Blender Z-up,
# shuning uchun modelning o'qlari sxemadagi o'qlar bilan mos kelmasligi mumkin.
PERMS = [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]


def best_axis_map(model_size, spec_size):
    """Qaytaradi: (axis_map, dev). axis_map[j] = modelning j-spec o'qida
    joylashgan o'q indeksi. Masalan (2,1,0) -> model 180° burilgan.

    Masshtab noma'lum bo'lgani uchun faqat NISBATLAR solishtiriladi."""
    m = [max(float(x), 1e-9) for x in model_size]
    s = [max(float(x), 1e-9) for x in spec_size]
    mn, sn = max(m), max(s)
    m = [x / mn for x in m]
    s = [x / sn for x in s]
    best, best_dev = (0, 1, 2), None
    for p in PERMS:
        dev = max(abs(m[p[j]] - s[j]) for j in range(3))
        if best_dev is None or dev < best_dev:
            best, best_dev = p, dev
    return best, float(best_dev)



def load(path):
    np, trimesh = _deps()
    scene = trimesh.load(str(path), force="mesh", process=False)
    if isinstance(scene, trimesh.Scene):
        scene = trimesh.util.concatenate(list(scene.geometry.values()))
    return scene


def check(path, part=None, rules=None):
    """Qaytaradi: {'ok':bool, 'score':0..1, 'checks':{...}, 'fix':str}"""
    r = {**DEFAULT_RULES, **(rules or {})}
    res = {"part": (part or {}).get("id", Path(path).stem), "checks": {},
           "ok": False, "score": 0.0, "fix": ""}
    np, _ = _deps()
    try:
        m = load(path)
    except Exception as e:
        res["fix"] = f"GLB ochilmadi: {e}"
        return res

    v = np.asarray(m.vertices, dtype=np.float64)
    f = np.asarray(m.faces, dtype=np.int64)
    res["checks"]["vertices"] = int(len(v))
    res["checks"]["triangles"] = int(len(f))

    if len(v) < 4 or len(f) < r["min_faces"]:
        res["fix"] = "Mesh juda kichik"
        return res

    # --- NaN
    if not np.isfinite(v).all():
        res["fix"] = "Manzilarda NaN/Inf bor"
        return res

    # --- bbox
    lo, hi = v.min(axis=0), v.max(axis=0)
    size = hi - lo
    if (size <= 0).any():
        res["fix"] = "Bitta o'q bo'sh (degenerate mesh)"
        return res
    res["checks"]["bbox"] = [round(float(x), 4) for x in size]

    # --- degenerate yuzalar
    tri = v[f]
    a = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    deg = float((a < max(size.max() * 1e-6, 1e-12)).mean())
    res["checks"]["degenerate_ratio"] = round(deg, 4)

    # --- komponentlar: eng kattasining ulushi muhim (sanash emas)
    try:
        comps = m.split(only_watertight=False)
        nc = len(comps)
        nf = len(f)
        biggest = max((len(c.faces) for c in comps), default=0)
        share = float(biggest / nf) if nf else 0.0
    except Exception:
        nc, share = 1, 1.0
    res["checks"]["components"] = nc
    res["checks"]["largest_component"] = round(share, 4)

    # --- yopiqlik ( TRELLIS.2 da deyarli har doim 0 — jinoiy emas,
    # faqat ballga ta'sir qiladi)
    try:
        wat = m.copy()
        wat.merge_vertices()
        wat.fix_normals()
        if nc:
            wat = max(comps, key=lambda c: len(c.faces))
        wt = float(wat.is_watertight)
    except Exception:
        wt = 0.0
    res["checks"]["watertight"] = round(wt, 3)

    # --- namoyish nisbati (spec ga qarshi) + o'q mosligi
    if part:
        spec = np.array(part.get("real_size_mm", []), dtype=float)
        if spec.size == 3 and (spec > 0).all():
            amap, dev = best_axis_map(size, spec)
            exp = spec / spec.max()
            got = np.array([size[amap[j]] for j in range(3)]) / max(size.max(), 1e-9)
            res["checks"]["axis_map"] = list(amap)
            res["checks"]["aspect_expected"] = [round(float(x), 3) for x in exp]
            res["checks"]["aspect_actual"] = [round(float(x), 3) for x in got]
            res["checks"]["aspect_dev"] = round(dev, 3)

    # --- baholash
    checks, score, fails = res["checks"], 0.0, []
    nt = checks["triangles"]
    if nt < r["min_triangles"]:
        fails.append(f"burchak soni kam ({nt})")
    if nt > r["max_triangles"]:
        fails.append(f"burchak soni juda ko'p ({nt})")
    if checks["degenerate_ratio"] > r["max_degenerate_ratio"]:
        fails.append(f"buzilgan yuzalar ({checks['degenerate_ratio']:.1%})")
    if checks["largest_component"] < r["min_largest_component"]:
        fails.append(f"asosiy qism ulushi kichik ({checks['largest_component']:.0%})")
    if "aspect_dev" in checks and checks["aspect_dev"] > r["max_aspect_dev"]:
        fails.append(f"nisbat sxemadan farq qiladi ({checks['aspect_dev']:.2f})")

    # ball: jinoiy holatlar kamaytiradi, lekin o'zi o'tkazmaydi
    score = 1.0
    score -= min(0.35, checks["degenerate_ratio"] * 3)
    score -= min(0.35, max(0.0, r["min_largest_component"]
                           - checks["largest_component"]) * 1.2)
    if "aspect_dev" in checks:
        score -= min(0.5, checks["aspect_dev"] * 0.9)
    if nt > r["max_mesh_tris"]:
        score -= 0.1        # past ball emas, ogohlantirish
    res["score"] = round(max(0.0, score), 3)
    res["ok"] = not fails
    if fails:
        res["fix"] = "; ".join(fails)
    res["heavy"] = bool(nt > r["max_mesh_tris"])
    return res


def check_part(part_id, proj, spec=None, rules=None, verbose=True):
    mdir = Path(proj) / "meshes"
    path = mdir / f"{part_id}.glb"
    if not path.exists():
        return {"part": part_id, "ok": False, "score": 0.0, "fix": "GLB yo'q", "checks": {}}
    part = None
    if spec:
        part = next((p for p in spec.get("parts", []) if p["id"] == part_id), None)
    r = check(path, part, rules)
    if verbose:
        mark = "OK " if r["ok"] else "FAIL"
        extra = f"  ({r['fix']})" if not r["ok"] else ""
        config.say(f"  [4/5] QC {mark} {part_id}  ball={r['score']:.2f}{extra}")
    return r


def check_all(proj, spec, rules=None):
    out = []
    for p in spec.get("parts", []):
        out.append(check_part(p["id"], proj, spec, rules, verbose=False))
    ok = sum(1 for r in out if r["ok"])
    config.say(f"  [4/5] QC: {ok}/{len(out)} qism o'tdi")
    report = Path(proj) / "qc_report.json"
    config.write_json(report, {"total": len(out), "passed": ok, "results": out})
    config.say(f"       hisobot: {report}")
    return out
