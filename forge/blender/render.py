"""Blender ichida: turntable render (vizual QC uchun).

  blender --background --python blender/render.py -- --glb part.glb --out renders/piston --views 4
  blender --background --python blender/render.py -- --blend out/engine.blend --out renders/eng --views 4
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--glb", default="")
ap.add_argument("--blend", default="")
ap.add_argument("--spec", default="")
ap.add_argument("--part", default="")
ap.add_argument("--out", required=True)
ap.add_argument("--views", type=int, default=4)
ap.add_argument("--res", type=int, default=512)
ap.add_argument("--samples", type=int, default=24)
ARGS = ap.parse_args(argv)

os.makedirs(ARGS.out, exist_ok=True)

PERMS = [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]


def _bbox(ob):
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(p.x for p in bb), min(p.y for p in bb), min(p.z for p in bb)))
    hi = Vector((max(p.x for p in bb), max(p.y for p in bb), max(p.z for p in bb)))
    return lo, hi, hi - lo


def align_to_spec(ob):
    """Modelni sxemadagi yo'nalish va haqiqiy o'lchamga moslashtiradi —
    QC renderi bilan haqiqiy ko'rinishni taqqoslash uchun zaruriy."""
    if not (ARGS.spec and ARGS.part):
        return
    import json as _json
    try:
        spec = _json.load(open(ARGS.spec, encoding="utf-8"))
    except Exception:
        return
    part = next((p for p in spec.get("parts", []) if p["id"] == ARGS.part), None)
    if not part:
        return
    target = part.get("real_size_mm") or []
    if len(target) != 3 or max(target) <= 0:
        return

    import bmesh
    _, _, size = _bbox(ob)
    m = [max(float(x), 1e-9) for x in (size.x, size.y, size.z)]
    s = [max(float(x), 1e-9) for x in target]
    mn, sn = max(m), max(s)
    m = [x / mn for x in m]
    s = [x / sn for x in s]
    amap = min(PERMS, key=lambda p: max(abs(m[p[j]] - s[j]) for j in range(3)))

    if list(amap) != [0, 1, 2]:
        R = [[0.0] * 3 for _ in range(3)]
        for j in range(3):
            R[j][amap[j]] = 1.0
        det = (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1])
               - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
               + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))
        if det < 0:
            R[0][0] *= -1.0
        ob.data.transform(Matrix(R).to_4x4())

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    _, _, size = _bbox(ob)
    src = max(size.x, size.y, size.z)
    sc = (max(target) / src) if src > 1e-9 else 1.0
    ob.scale = (sc, sc, sc)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _, _, size = _bbox(ob)
    ctr = (sum((ob.matrix_world @ Vector(c) for c in ob.bound_box), Vector())
           / 8.0)
    ob.data.transform(Matrix.Translation(-ctr))
    print(f"[ALIGN] {ARGS.part} axis={amap} scale={sc:.4f} "
          f"bbox={[round(v,2) for v in size]} target={target}")

if ARGS.blend:
    bpy.ops.wm.open_mainfile(filepath=ARGS.blend)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    for op in ("import_scene.gltf", "wm.gltf_import"):
        try:
            fn = bpy.ops
            for seg in op.split("."):
                fn = getattr(fn, seg)
        except AttributeError:
            continue
        try:
            fn(filepath=ARGS.glb)
            break
        except Exception as e:
            print(f"[import] {op}: {e}")
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not new:
        print("[XATO] mesh import qilinmadi")
        sys.exit(1)
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    align_to_spec(bpy.context.view_layer.objects.active)

scene = bpy.context.scene
forced = os.environ.get("FORGE_RENDER_ENGINE", "").strip().upper()
for e in ([forced] if forced else ["CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"]):
    if not e:
        continue
    try:
        scene.render.engine = e
        break
    except Exception:
        continue
if scene.render.engine == "CYCLES":
    dev = os.environ.get("FORGE_CYCLES_DEVICE", "GPU").upper()
    backend = os.environ.get("FORGE_CYCLES_BACKEND", "OPTIX").upper()
    if dev in ("GPU", "OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            cp = bpy.context.preferences.addons["cycles"].preferences
            cp.compute_device_type = backend
            cp.get_devices()
            for d in cp.devices:
                d.use = (d.type == backend)
            scene.cycles.device = "GPU"
        except Exception as e:
            print(f"[GPU] sozlanmadi ({e}) -> CPU")
            scene.cycles.device = "CPU"
    else:
        scene.cycles.device = dev
    scene.cycles.samples = ARGS.samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
else:
    try:
        scene.eevee.taa_render_samples = ARGS.samples
    except Exception:
        pass
scene.render.resolution_x = scene.render.resolution_y = ARGS.res
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
try:
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = float(os.environ.get("FORGE_EXPOSURE", "0.0"))
except Exception:
    pass

w = bpy.data.worlds.new("W")
scene.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.16, 0.17, 0.19, 1)
    bg.inputs[1].default_value = 1.0


def bounds():
    lo = Vector((1e18,) * 3)
    hi = Vector((-1e18,) * 3)
    n = 0
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        n += 1
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            lo = Vector((min(lo.x, p.x), min(lo.y, p.y), min(lo.z, p.z)))
            hi = Vector((max(hi.x, p.x), max(hi.y, p.y), max(hi.z, p.z)))
    return (lo, hi) if n else (Vector((-50, -50, 0)), Vector((50, 50, 50)))


lo, hi = bounds()
ctr = (lo + hi) / 2.0
diag = max((hi - lo).length, 1e-3)

cd = bpy.data.cameras.new("C")
cd.lens = 50
cd.sensor_width = 36
cd.clip_start = 0.01
cd.clip_end = max(1000.0, diag * 20.0)   # mm-birlikli sahna uchun muhim
cam = bpy.data.objects.new("C", cd)
scene.collection.objects.link(cam)
scene.camera = cam


def place(angle_deg, elev=0.42, margin=1.18):
    half_fov = math.atan((cam.data.sensor_width / 2.0) / cam.data.lens)
    r = (hi - lo).length / 2.0
    dist = max(r / max(math.tan(half_fov), 1e-3) * margin, 1e-3)
    a = math.radians(angle_deg)
    d = Vector((math.cos(a), math.sin(a), elev))
    pos = ctr + d.normalized() * dist
    cam.location = pos
    cam.rotation_euler = (ctr - pos).to_track_quat("-Z", "Y").to_euler()


def add_sun(name, direction, strength):
    d = Vector(direction).normalized()
    ld = bpy.data.lights.new(name, type="SUN")
    ld.energy = strength
    ld.angle = math.radians(5.0)
    o = bpy.data.objects.new(name, ld)
    o.location = ctr + d * diag * 3
    o.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(o)


def area(name, direction, irradiance, size_frac):
    pos = ctr + Vector(direction).normalized() * diag * 1.5
    d = max((pos - ctr).length, 1e-6)
    ld = bpy.data.lights.new(name, type="AREA")
    ld.energy = irradiance * 4.0 * math.pi * d * d
    ld.size = max(diag * size_frac, 1e-3)
    o = bpy.data.objects.new(name, ld)
    o.location = pos
    o.rotation_euler = (ctr - pos).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(o)


add_sun("Sun", (0.5, -0.8, 1.0), 3.5)
area("Fill", (-1.3, -0.8, 0.3), 1.0, 0.9)

files = []
n = max(1, ARGS.views)
for i in range(n):
    place(360.0 * i / n + 35)
    f = os.path.join(ARGS.out, f"v{i:02d}.png")
    scene.render.filepath = f
    bpy.ops.render.render(write_still=True)
    files.append(f)
    print(f"[RENDER] {f}")

print("[DONE] " + ";".join(files))
