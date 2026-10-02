#!/usr/bin/env python3
"""FORGE - obyektdan detalli 3D model yasash pipeline'i.

Bosqichlar:
  plan      Google AI Studio'dan qismlar + 3D sxema (spec.json)
  images    har bir qism uchun referens rasm (Nano Banana)
  model     rasmdan 3D GLB (Image-To-3D, ko'p seed + IoU tanlash)
  qc        GLB sifat nazorati
  assemble  Blender headless: import, masshtab, joylashtirish, .blend, render
  run       hammasi ketma-ket (avtomatik qayta urinish bilan)

Misol:
  python forge/forge.py run "LS V8 engine" --detail high
  python forge/forge.py run "LS V8 engine" --from model     --resume
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules import (config, gemini, i2i3d, imagegen, imagegen_local,  # noqa: E402
                      planner, qc)

BLENDER = Path(__file__).resolve().parent / "blender"
MAX_ATTEMPTS = 3


def run_blender(script, *args, timeout=1800):
    exe = config.blender_exe()
    cmd = [exe, "--background", "--factory-startup", "--python",
           str(BLENDER / script), "--"] + [str(a) for a in args]
    config.say(f"  $ blender --background --python {script} " + " ".join(str(a) for a in args))
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    for line in (p.stdout or "").splitlines():
        if any(k in line for k in ("[OK]", "[MISS]", "[BLEND]", "[RENDER]", "[DONE]",
                                   "[XATO]", "Error", "Traceback", "  File ", "import]")):
            config.say("   " + line)
    if p.returncode != 0:
        config.say(f"   [XATO] blender chiqish kodi {p.returncode}")
        tail = "\n".join((p.stderr or "").splitlines()[-25:])
        if tail.strip():
            config.say("   " + tail.replace("\n", "\n   "))
    return p.returncode == 0


def hr(title):
    config.say("")
    config.say("=" * 66)
    config.say(f"  {title}")
    config.say("=" * 66)


# --------------------------------------------------------------- stages

def stage_plan(obj, proj, detail, extra, force):
    spec_path = proj / "spec.json"
    if spec_path.exists() and not force:
        spec = config.read_json(spec_path)
        config.say(f"  [1/5] spec mavjud ({len(spec['parts'])} qism) - qayta o'tkazilmadi")
        return spec
    return planner.generate_and_save(obj, proj, detail=detail, extra=extra)


def stage_images(spec, proj, views, force, only=None):
    parts = spec["parts"] if not only else [p for p in spec["parts"] if p["id"] in only]
    imgdir = Path(proj) / "images"
    imgdir.mkdir(parents=True, exist_ok=True)

    # Avval qo'lda qo'yilgan rasmlarni hurmat qilamiz
    have = [p for p in parts if (imgdir / f"{p['id']}.hero.png").exists()]
    todo = [p for p in parts if p not in have]
    if have and not force:
        config.say(f"  [2/5] {len(have)} ta rasm mavjud — qayta o'tkazilmadi")
    if not todo:
        return {}

    config.say(f"  [2/5] {len(todo)} ta rasm yaratilmoqda (backend: {imagegen.backend()})")
    if imagegen.backend() == "local" and not imagegen_local.ensure_server():
        config.say(f"  [XATO] ComfyUI ishlamadi. Yo'llar: {imagegen_local.comfy_dir()}")

    try:
        res = imagegen.generate_all({"parts": todo}, proj, views=views, force=force)
    except Exception as e:
        config.say(f"  [2/5] [XATO] {str(e)[:500]}")
        res = {}

    # siluet tekshiruvi
    bad = []
    for p in todo:
        path = imgdir / f"{p['id']}.hero.png"
        if not path.exists():
            continue
        ok, msg, _ = imagegen.validate_alpha(path)
        if not ok:
            bad.append((p, msg))
    for p, msg in bad:
        config.say(f"      [siluet] {p['id']}: {msg} - qayta generatsiya...")
        try:
            imagegen.regenerate_with_feedback(p, path_img := imgdir / f"{p['id']}.hero.png", msg)
        except Exception as e:
            config.say(f"      [XATO] {p['id']}: {str(e)[:160]}")

    # natijani xabar berish
    still = [p["id"] for p in parts if not (imgdir / f"{p['id']}.hero.png").exists()]
    if still:
        config.say("")
        config.say(f"  [2/5] {len(still)} ta rasm yo'q - ularni qo'lda qo'ying:")
        for pid in still:
            config.say(f"        {imgdir / (pid + '.hero.png')}")
        config.say("     Talab: PNG/JPG, oq fon, qism to'liq va markazda bo'lsin.")
    return res


def stage_model(spec, proj, seeds, steps, tsteps, only=None, force=False):
    if not i2i3d.alive():
        config.say("  [XATO] Image-To-3D server ishlamayapti. Ishga tushiring:")
        config.say(f"        {config.I2I3D / 'start_server.bat'}")
        return {}
    ids = [p["id"] for p in spec["parts"]] if not only else only
    out = {}
    for pid in ids:
        img = proj / "images" / f"{pid}.hero.png"
        if not img.exists():
            config.say(f"  [3/5] {pid}: rasm yo'q - o'tkazildi")
            continue
        meta = i2i3d.pick(pid, proj, img, n_seeds=seeds, steps=steps,
                           texture_steps=tsteps, force=force)
        if meta:
            out[pid] = meta
    return out


def stage_qc(spec, proj, retry=True, seeds=4, steps=20, tsteps=20):
    report = qc.check_all(proj, spec)
    if not retry:
        return report
    failed = [r["part"] for r in report if not r["ok"]]
    if not failed:
        return report
    config.say(f"  [4/5] {len(failed)} ta qism sifatsiz - qayta urinish...")
    for attempt in range(1, MAX_ATTEMPTS):
        config.say(f"       urinish {attempt}/{MAX_ATTEMPTS - 1}")
        for pid in list(failed):
            meta_p = proj / "meshes" / f"{pid}.meta.json"
            meta = config.read_json(meta_p, {}) or {}
            if meta.get("next_seed", 0) > 400:
                continue
            img = proj / "images" / f"{pid}.hero.png"
            m = i2i3d.pick(pid, proj, img, n_seeds=seeds, steps=steps,
                           texture_steps=tsteps, min_iou=0.0, force=True)
            if m:
                meta["next_seed"] = m["next_seed"]
                config.write_json(meta_p, meta)
        report = qc.check_all(proj, spec)
        failed = [r["part"] for r in report if not r["ok"]]
        if not failed:
            break
    if failed:
        config.say(f"  [4/5] baribir sifatsiz: {', '.join(failed)}")
        config.say("       (agent: rasmni qayta generatsiya qilib prompt'ni tuzatishni ko'ring)")
    return report


def stage_assemble(spec, proj, res=1280, samples=48, only="", max_tris=200000):
    return run_blender("assemble.py", "--spec", proj / "spec.json", "--proj", proj,
                       "--res", res, "--samples", samples, "--only", only,
                       "--max-tris", max_tris)


def stage_review(spec, proj, views=4, res=512):
    """Har bir qism uchun turntable render - agent ko'rib tekshiradi."""
    out = {}
    for p in spec["parts"]:
        glb = proj / "meshes" / f"{p['id']}.glb"
        if not glb.exists():
            continue
        d = proj / "renders" / p["id"]
        if (d / "v00.png").exists():
            out[p["id"]] = str(d)
            continue
        run_blender("render.py", "--glb", glb, "--out", d, "--views", views,
                    "--res", res, "--spec", Path(proj) / "spec.json",
                    "--part", p["id"])
        out[p["id"]] = str(d)
    return out


# --------------------------------------------------------------- commands

def cmd_plan(a):
    proj = config.project_dir(a.object)
    proj.mkdir(parents=True, exist_ok=True)
    spec = stage_plan(a.object, proj, a.detail, a.extra, a.force)
    config.say(f"  qismlar: {len(spec['parts'])}")
    for p in spec["parts"]:
        config.say(f"    - {p['id']:<24} x{p['count']:<2} {p['real_size_mm']}  {p['name']}")
    return 0


def cmd_images(a):
    proj = config.project_dir(a.object)
    spec = config.read_json(proj / "spec.json")
    if not spec:
        config.say("[XATO] spec.json yo'q. Avval `plan` ni ishga tushiring.")
        return 1
    stage_images(spec, proj, tuple(a.image_views), a.force, a.only or None)
    return 0


def cmd_model(a):
    proj = config.project_dir(a.object)
    spec = config.read_json(proj / "spec.json")
    if not spec:
        config.say("[XATO] spec.json yo'q. Avval `plan` ni ishga tushiring.")
        return 1
    stage_model(spec, proj, a.seeds, a.steps, a.texture_steps, a.only or None, a.force)
    return 0


def cmd_qc(a):
    proj = config.project_dir(a.object)
    spec = config.read_json(proj / "spec.json")
    if not spec:
        config.say("[XATO] spec.json yo'q.")
        return 1
    stage_qc(spec, proj, retry=not a.no_retry, seeds=a.seeds, steps=a.steps,
             tsteps=a.texture_steps)
    return 0


def cmd_assemble(a):
    proj = config.project_dir(a.object)
    if not (proj / "spec.json").exists():
        config.say("[XATO] spec.json yo'q.")
        return 1
    return 0 if stage_assemble(spec := config.read_json(proj / "spec.json"), proj,
                              a.res, a.samples, a.only or "", a.max_tris) else 1


def cmd_review(a):
    proj = config.project_dir(a.object)
    spec = config.read_json(proj / "spec.json")
    if not spec:
        config.say("[XATO] spec.json yo'q.")
        return 1
    stage_review(spec, proj, a.review_views, a.res)
    return 0


def cmd_run(a):
    t0 = time.time()
    proj = config.project_dir(a.object)
    proj.mkdir(parents=True, exist_ok=True)
    hr(f"FORGE: {a.object}   ({proj})")

    spec = stage_plan(a.object, proj, a.detail, a.extra, a.force)
    config.say(f"  qismlar: {len(spec['parts'])}")

    hr("2/6  Referens rasmlar")
    stage_images(spec, proj, tuple(a.image_views), False, a.only or None)

    imgdir = Path(proj) / "images"
    ready = [p for p in spec["parts"] if (imgdir / f"{p['id']}.hero.png").exists()]
    if imagegen.backend() == "local" and imagegen_local.alive():
        config.say("  ComfyUI modellari VRAM dan tushirilmoqda...")
        imagegen_local.free()
    if not ready:
        hr("TUSHDI")
        config.say("  Birorta ham rasm tayyor emas - 3D bosqichini o'tkazib bo'lmaydi.")
        config.say(f"  Rasmlarni shu papkaga qo'ying: {imgdir}")
        config.say(f'  Keyin:  .\\forge\\forge.bat images "{a.object}"   (yoki model)')
        config.say("  Har bir rasm uchun: <part>.hero.png  (oq fon, qism markazda to'liq)")
        return 1
    if len(ready) < len(spec["parts"]):
        config.say(f"  ({len(ready)}/{len(spec['parts'])} rasm tayyor - qolganlari o'tkaziladi)")

    hr("3/6  Rasmdan 3D (Image-To-3D)")
    if a.from_ == "plan":
        config.say("  [--from plan] keyingi bosqichga o'tkazildi")
    else:
        # ComfyUI va Image-To-3D ikkalasi ham GPU oladi — xotirani bo'shatamiz
        if imagegen.backend() == "local" and imagegen_local.alive():
            config.say("  ComfyUI modellari VRAM dan tushirilmoqda...")
            imagegen_local.free()
            time.sleep(3)
        stage_model(spec, proj, a.seeds, a.steps, a.texture_steps, a.only or None)

        hr("4/6  Sifat nazorati (QC)")
        stage_qc(spec, proj, retry=True, seeds=a.seeds, steps=a.steps,
                 tsteps=a.texture_steps)

        hr("5/6  Vizual QC render")
        if not a.no_review:
            stage_review(spec, proj, a.review_views, 512)

        hr("6/6  Blender yig'ish")
        ok = stage_assemble(spec, proj, a.res, a.samples, a.only or "", a.max_tris)
    hr(f"Tayyor: {(time.time() - t0) / 60:.1f} daqiqa")
    config.say(f"  spec    : {proj / 'spec.json'}")
    config.say(f"  blend   : {proj / 'out'}")
    config.say(f"  renders : {proj / 'renders'}")
    return 0


def cmd_doctor(a):
    hr("FORGE doctor")
    ok = True

    config.say("[1] Gemini matn (sxema uchun)")
    r, msg = gemini.test_key()
    config.say(f"    {'OK  ' if r else 'FAIL'} {msg}")
    ok = ok and r

    config.say("[2] Rasm backendi")
    b = imagegen.backend()
    if b == "local":
        config.say("    (ComfyUI + Qwen-Image-2.1 GGUF — lokal)")
        if not imagegen_local.ensure_server():
            ok = False
        else:
            n_ok, n_msg = imagegen_local.check_nodes()
            config.say(f"    {'OK  ' if n_ok else 'FAIL'} node'lar: {n_msg}")
            ok = ok and n_ok
            m_ok, m_msg = imagegen_local.check_models()
            config.say(f"    {'OK  ' if m_ok else 'FAIL'} modellar: {m_msg}")
            ok = ok and m_ok
    else:
        config.say("    (Google AI Studio — Nano Banana)")
        r, msg = gemini.test_image()
        config.say(f"    {'OK  ' if r else 'FAIL'} {msg.splitlines()[0] if msg else ''}")
        ok = ok and r
        if not r:
            for ln in (msg or "").splitlines()[1:]:
                config.say(f"         {ln}")

    config.say("[3] Image-To-3D server")
    al = i2i3d.alive()
    config.say(f"    {'OK  ' if al else 'FAIL'} "
               f"{config.cfg('FORGE_I2I3D_URL')} {'javob bermoqda' if al else 'javob bermayapti'}")
    if not al:
        config.say(f"         -> {config.I2I3D / 'start_server.bat'}")
    ok = ok and al

    config.say("[4] Blender")
    try:
        b = config.blender_exe()
        config.say(f"    OK   {b}")
    except SystemExit as e:
        config.say(f"    FAIL {e}")
        ok = False

    config.say("[5] Python modullari")
    deps_ok = True
    for m in ("numpy", "trimesh", "scipy", "PIL"):
        try:
            __import__(m)
            config.say(f"    OK   {m}")
        except ImportError:
            config.say(f"    FAIL {m} - pip install -r requirements.txt")
            deps_ok = False
    ok = ok and deps_ok

    config.say("")
    if ok:
        config.say(f"  Hammasi tayyor. Backend: {b} (rasm), Gemini (matn).")
        config.say(f'  Ishga tushiring:  .\\forge\\forge.bat run "LS V8 engine"')
    else:
        config.say("  Yuqoridagi FAIL qatorlarini bartaring.")
    return 0 if ok else 1


# --------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(prog="forge", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("object", help="obyekt nomi, masalan 'LS V8 engine'")
        p.add_argument("--detail", default="high",
                       choices=["draft", "normal", "high", "ultra"])
        p.add_argument("--extra", default="", help="qo'shimcha talab")
        p.add_argument("--only", nargs="*", default=[], help="faqat berilgan qismlar")
        p.add_argument("--seeds", type=int, default=4)
        p.add_argument("--steps", type=int, default=20)
        p.add_argument("--texture-steps", dest="texture_steps", type=int, default=20)
        p.add_argument("--res", type=int, default=1280)
        p.add_argument("--samples", type=int, default=48)
        p.add_argument("--max-tris", dest="max_tris", type=int, default=200_000,
                       help="har bir qism uchun maqsadli uchburchak soni (0 = siqmaydi)")
        p.add_argument("--image-views", dest="image_views", nargs="*",
                       default=["hero"], choices=["hero", "front", "side", "top"],
                       help="rasm bosqichi uchun burchaklar (3D ga faqat hero yuboriladi)")
        p.add_argument("--review-views", dest="review_views", type=int, default=4,
                       help="QC turntable renderidagi burchaklar soni")
        p.add_argument("--force", action="store_true")
        return p

    common(sub.add_parser("plan", help="spec.json yaratish")).set_defaults(func=cmd_plan)
    common(sub.add_parser("images", help="referens rasmlar")).set_defaults(func=cmd_images)
    common(sub.add_parser("model", help="rasmdan 3D")).set_defaults(func=cmd_model)

    p = common(sub.add_parser("qc", help="sifat nazorati"))
    p.add_argument("--no-retry", action="store_true")
    p.set_defaults(func=cmd_qc)

    common(sub.add_parser("assemble", help="Blender yig'ish")).set_defaults(func=cmd_assemble)
    common(sub.add_parser("review", help="turntable render")).set_defaults(func=cmd_review)

    p = common(sub.add_parser("run", help="to'liq pipeline"))
    p.add_argument("--from", dest="from_", default="start",
                   choices=["start", "plan", "images", "model", "qc", "assemble"])
    p.add_argument("--no-review", action="store_true")
    p.set_defaults(func=cmd_run)

    sub.add_parser("doctor", help="muhitni tekshirish").set_defaults(func=cmd_doctor)

    a = ap.parse_args()
    config.load_env()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
