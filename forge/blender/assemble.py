"""Blender ichida ishlaydi (headless).

Ishlatish:
  blender --background --python blender/assemble.py -- ^
      --spec projects/<slug>/spec.json --proj projects/<slug> --out out.blend

Vazifa:
  - har bir <part>.glb ni import qiladi
  - modelni sxemadagi real_size_mm ga MASSHTABLAYDI
  - placement.location_mm / rotation_deg bo'yicha joylaytiradi
  - symmetry bo'yicha ko'p nusxa yaratadi (porshinlar, klapanlar, boltalar)
  - material, collection va nomlar beradi
  - .blend saqlaydi va render qiladi
"""
import argparse
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

# --------------------------------------------------------------- args

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--spec", required=True)
ap.add_argument("--proj", required=True)
ap.add_argument("--out", default="")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--render", default="")          # qo'shimcha render fayli
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--res", type=int, default=1280)
ap.add_argument("--max-tris", dest="max_tris", type=int, default=200_000,
                help="har bir qism uchun maqsadli uchburchak soni (0 = o'chiriladi)")
ap.add_argument("--only", default="")            # faqat bitta qism (test uchun)
ARGS = ap.parse_args(argv)

PROJ = ARGS.proj
SPEC = json.load(open(ARGS.spec, encoding="utf-8"))
MESH_DIR = os.path.join(PROJ, "meshes")
OUT_DIR = os.path.join(PROJ, "out")
RENDERS = os.path.join(PROJ, "renders")
for d in (OUT_DIR, RENDERS):
    os.makedirs(d, exist_ok=True)

# --------------------------------------------------------------- scene reset

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 0.001      # 1 Blender birligi = 1 mm
scene.unit_settings.length_unit = "MILLIMETERS"


def engine():
    """EEVEE headless rejimda bo'sh render qaytaradi (GPU konteksti yo'q).
    Shuning uchun standart — CYCLES. ENV bilan o'zgartiriladi."""
    forced = os.environ.get("FORGE_RENDER_ENGINE", "").strip().upper()
    order = [forced] if forced else ["CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"]
    for e in order:
        if not e:
            continue
        try:
            scene.render.engine = e
            return e
        except Exception:
            continue
    return scene.render.engine


ENGINE = engine()
if ENGINE == "CYCLES":
    # GPU'da render qilish (OPTIX = NVIDIA). CPU'ga qaytmaydi.
    dev = os.environ.get("FORGE_CYCLES_DEVICE", "GPU").upper()
    backend = os.environ.get("FORGE_CYCLES_BACKEND", "OPTIX").upper()
    try:
        if dev in ("GPU", "OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            prefs = bpy.context.preferences.addons.get("cycles")
            if prefs:
                cp = prefs.preferences
                for attr, val in (("compute_device_type", backend),):
                    try:
                        setattr(cp, attr, val)
                        cp.get_devices()
                    except Exception:
                        pass
                # faqat GPU qurilmalarini yoqish
                for d in cp.devices:
                    try:
                        d.use = (d.type == backend)
                    except Exception:
                        pass
            scene.cycles.device = "GPU"
        else:
            scene.cycles.device = dev
    except Exception as e:
        print(f"   [GPU] sozlanmadi ({e}) -> CPU")
        scene.cycles.device = "CPU"
    scene.cycles.samples = ARGS.samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 4
else:
    try:
        scene.eevee.taa_render_samples = ARGS.samples
    except Exception:
        pass
scene.render.resolution_x = ARGS.res
scene.render.resolution_y = ARGS.res
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False

# View transform: AgX juda quyuq qorong'i chiqaradi va QC uchun
# yomon o'qiladi. 'Standard' — oldindan bashorat qilinadigan natija.
try:
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = float(os.environ.get("FORGE_EXPOSURE", "0.0"))
except Exception:
    pass

# world: o'rtacha kulrang fon — metallik materiallar uchun ham, silhouette
# o'qish uchun ham yaxshi (juda qorong'i fon metallni qora qilib ko'rsatadi)
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.16, 0.17, 0.19, 1.0)
    bg.inputs[1].default_value = float(os.environ.get("FORGE_WORLD_STRENGTH", "1.0"))

def decimate(ob, max_tris):
    """TRELLIS.2 ~1M uchburchak beradi; 20 ta qism yig'ilса Blender
    juda sekinlashadi. Maqsadli songech siqib qo'yamiz.

    DIQQAT: bo'laklarni filtrlamaymiz — TRELLIS.2 chiqishida ko'p
    alohida bo'lak bo'ladi va ulardan "keraksiz" deb hisoblanishi
    noto'g'ri (masalan boltdan ajratilgan shayba). Faqat siqish."""
    if max_tris <= 0:
        return 0, 0
    me = ob.data
    me.calc_loop_triangles()
    before = len(me.loop_triangles)
    if before <= max_tris:
        return before, before

    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    mod = ob.modifiers.new(name="ForgeDecimate", type="DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = max(max_tris / max(before, 1), 1e-4)
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)

    ob.data.update()
    ob.data.calc_loop_triangles()
    return before, len(ob.data.loop_triangles)


# --------------------------------------------------------------- import

IMPORT_OPS = ("import_scene.gltf", "wm.gltf_import", "import_scene.gltf2")


def import_glb(path):
    before = set(bpy.data.objects)
    for op in IMPORT_OPS:
        fn = bpy.ops
        try:
            for seg in op.split("."):
                fn = getattr(fn, seg)
        except AttributeError:
            continue
        try:
            fn(filepath=path)
            new = [o for o in bpy.data.objects if o not in before]
            if new:
                return new
        except Exception as e:
            print(f"   [import] {op} ishlamadi: {e}")
    return []


def collect_meshes(objects):
    """Import natijasini bitta mesh obyektga jamlaydi."""
    meshes = [o for o in objects if o.type == "MESH"]
    empties = [o for o in objects if o.type == "EMPTY"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0] if meshes else None
    if meshes:
        if len(meshes) > 1:
            bpy.ops.object.join()
        ob = bpy.context.view_layer.objects.active
        ob.name = "PART"
        ob.data.name = "PART_mesh"
    else:
        ob = None
    for e in empties:
        bpy.data.objects.remove(e, do_unlink=True)
    return ob


def mesh_stats(ob):
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(p.x for p in bb), min(p.y for p in bb), min(p.z for p in bb)))
    hi = Vector((max(p.x for p in bb), max(p.y for p in bb), max(p.z for p in bb)))
    return lo, hi, hi - lo


# --------------------------------------------------------------- materials

def make_material(name, hexcolor, metallic=0.35, rough=0.45):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    s = (hexcolor or "#9aa0a6").lstrip("#")
    try:
        rgb = [int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except Exception:
        rgb = [0.6, 0.6, 0.62]
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metallic
    return m


MAT_FOR = {
    "steel": ("#8a9099", 0.55, 0.38), "stainless": ("#a8aeb6", 0.6, 0.28),
    "aluminium": ("#b7bcc2", 0.5, 0.42), "aluminum": ("#b7bcc2", 0.5, 0.42),
    "cast aluminium": ("#8e9298", 0.35, 0.6), "cast iron": ("#5b5f65", 0.3, 0.68),
    "iron": ("#5b5f65", 0.3, 0.68), "rubber": ("#1e2024", 0.0, 0.85),
    "plastic": ("#c9ccd1", 0.0, 0.5), "glass": ("#cfd8dc", 0.1, 0.15),
    "carbon": ("#22252a", 0.15, 0.5), "chrome": ("#d6dae0", 0.7, 0.12),
}

# Metallik 1.0 va 0.9 kabi qiymatlar renderda deyarli qora chiqadi
# (atrofdagi muhitni aks ettiradi, muhit esa minimal). Preview uchun
# pastroq qiymat kerak; faylda haqiqiy PBR keyin qo'yiladi.
MAX_METALLIC = 0.6


def mat_for(part):
    key = str(part.get("material", "")).lower().strip()
    hexc, met, rough = MAT_FOR.get(key, (part.get("color") or "#9aa0a6", 0.3, 0.5))
    return make_material(f"M_{part['id']}", hexc, min(met, MAX_METALLIC), rough)


# --------------------------------------------------------------- symmetry

def instances_for(part):
    """(location, rotation) ro'yxati. Asosiy placement guruh markazi deb hisoblanadi."""
    p = part["placement"]
    loc = Vector(p["location_mm"])
    rot = Vector(p["rotation_deg"])
    sym = (p.get("symmetry") or "none").lower()
    count = int(part.get("count") or 1)
    size = part["real_size_mm"]

    if count <= 1 or sym in ("none", "", "single"):
        return [(loc, rot)]

    out = []

    if sym in ("x", "y", "z"):
        ai = {"x": 0, "y": 1, "z": 2}[sym]
        step = size[ai] * 1.15
        n = count
        for i in range(n):
            off = (i - (n - 1) / 2.0) * step
            l = loc.copy()
            l[ai] += off
            out.append((l, rot))
        return out

    if sym in ("bore", "cyl", "row"):
        step = size[0] * 1.35
        for i in range(count):
            l = loc.copy()
            l.x += (i - (count - 1) / 2.0) * step
            out.append((l, rot))
        return out

    if sym == "corner":
        stepx, stepy = size[0] * 1.2, size[1] * 1.2
        nx = max(1, int(round(math.sqrt(count))))
        ny = max(1, int(round(count / nx)))
        k = 0
        for ix in range(nx):
            for iy in range(ny):
                if k >= count:
                    break
                l = loc.copy()
                l.x += (ix - (nx - 1) / 2.0) * stepx
                l.y += (iy - (ny - 1) / 2.0) * stepy
                out.append((l, rot))
                k += 1
        return out

    if sym in ("radial", "radial4"):
        r = max(size[0], size[1]) * 1.6
        for i in range(count):
            a = 2 * math.pi * i / count
            l = loc + Vector((r * math.cos(a), r * math.sin(a), 0.0))
            out.append((l, rot))
        return out

    # noma'lum -> qator
    for i in range(count):
        l = loc.copy()
        l.x += (i - (count - 1) / 2.0) * size[0] * 1.2
        out.append((l, rot))
    return out


# --------------------------------------------------------------- build

root_coll = bpy.data.collections.new(SPEC.get("object", "Assembly"))
scene.collection.children.link(root_coll)
root = bpy.data.objects.new(SPEC.get("object", "Assembly"), None)
root.empty_display_type = "PLAIN_AXES"
root.empty_display_size = 60.0
root_coll.objects.link(root)

# --------------------------------------------------------------- axes

PERMS = [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]


def best_axis_map(model_size, spec_size):
    """Qaytaradi: (axis_map, dev). axis_map[j] = modelning j-spec o'qida
    joylashgan o'q. GLB Y-up, Blender Z-up — import konvensiyasi
    noma'lum bo'lgani uchun shu yerda, Blender koordinatlarida hisoblanadi.

    Masshtab noma'lum (import birlik masshtabda), shuning uchun
    faqat NISBATLAR (har biri o'z eng katta o'qiga bo'lingan) solishtiriladi.
    """
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


def apply_axis_map(ob, amap):
    """new[j] = old[amap[j]] — mesh o'qlarini sxemadagi tartibga keltiradi."""
    R = [[0.0] * 3 for _ in range(3)]
    for j in range(3):
        R[j][amap[j]] = 1.0
    det = (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1])
           - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
           + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))
    if det < 0:                       # mirror bo'lmasligi uchun
        R[0][0] *= -1.0
    from mathutils import Matrix
    ob.data.transform(Matrix(R).to_4x4())
    fix_normals(ob)


def fix_normals(ob):
    """O'q o'zgarishi yoki importdan keyin normalar ichkariga qaragan
    bo'lishi mumkin — bu yorug'likni butunlay buzadi."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()


report = {"object": SPEC.get("object"), "parts": [], "missing": []}

for part in SPEC.get("parts", []):
    pid = part["id"]
    if ARGS.only and ARGS.only != pid:
        continue
    glb = os.path.join(MESH_DIR, f"{pid}.glb")
    if not os.path.exists(glb):
        print(f"  [MISS] {pid}: GLB yo'q")
        report["missing"].append(pid)
        continue

    objs = import_glb(glb)
    if not objs:
        print(f"  [MISS] {pid}: import bo'lmadi")
        report["missing"].append(pid)
        continue
    ob = collect_meshes(objs)
    if ob is None:
        print(f"  [MISS] {pid}: mesh yo'q")
        report["missing"].append(pid)
        continue

    lo, hi, size = mesh_stats(ob)
    fix_normals(ob)

    # --- o'q mosligi: GLB Y-up / Blender Z-up chalkashuvini tuzatish
    target = part["real_size_mm"]
    amap, adev = best_axis_map([size.x, size.y, size.z], target)
    if list(amap) != [0, 1, 2]:
        apply_axis_map(ob, amap)

    # --- sxemadagi haqiqiy o'lchamga masshtab
    lo, hi, size = mesh_stats(ob)
    src = max(size.x, size.y, size.z)
    dst = max(target) if max(target) > 0 else src
    scale = dst / src if src > 1e-9 else 1.0
    ob.scale = (scale, scale, scale)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # markazni 0 ga keltirish
    lo, hi, size = mesh_stats(ob)
    center = (lo + hi) / 2.0
    from mathutils import Matrix as _M
    ob.data.transform(_M.Translation(-center))

    ob.data.materials.clear()
    ob.data.materials.append(mat_for(part))

    ob.data.calc_loop_triangles()
    tri_before, tri_after = decimate(ob, ARGS.max_tris)
    if tri_after and tri_before and tri_after < tri_before:
        fix_normals(ob)

    coll = bpy.data.collections.get(f"PART_{pid}")
    if coll is None:
        coll = bpy.data.collections.new(f"PART_{pid}")
        root_coll.children.link(coll)
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)

    insts = instances_for(part)
    for k, (loc, rot) in enumerate(insts):
        if k == 0:
            o = ob
        else:
            o = ob.copy()
            o.data = ob.data          # mesh ulashiladi (tez)
            coll.objects.link(o)
        o.name = f"{pid}" if len(insts) == 1 else f"{pid}.{k:02d}"
        o.location = (loc.x, loc.y, loc.z)
        o.rotation_euler = tuple(math.radians(a) for a in rot)
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()

    report["parts"].append({
        "id": pid, "scale": round(scale, 6), "instances": len(insts),
        "axis_map": list(amap), "axis_dev": round(adev, 4),
        "target_mm": target, "model_bbox_mm": [round(v, 2) for v in size],
        "tris_before": tri_before, "tris_after": tri_after,
    })
    print(f"  [OK] {pid}: scale={scale:.3f} x{len(insts)} axis={amap} dev={adev:.2f} "
          f"tris={tri_before}->{tri_after}  "
          f"model={[round(v,1) for v in size]} -> target={target}")

# --------------------------------------------------------------- camera/lights

def all_bounds():
    lo = Vector((1e18, 1e18, 1e18))
    hi = Vector((-1e18, -1e18, -1e18))
    found = False
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        found = True
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return (lo, hi) if found else (Vector((-50, -50, 0)), Vector((50, 50, 50)))


lo, hi = all_bounds()
ctr = (lo + hi) / 2.0
diag = max((hi - lo).length, 1.0)

cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50
cam_data.sensor_width = 36
# Muhim: sahnaning birligi mm, obyektlar kameradan minglab BU masofada.
# Blender standart clip_end = 100 -> geometriya butunlay kesilib ketadi.
cam_data.clip_start = 0.01
cam_data.clip_end = max(1000.0, diag * 20.0)
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def fit_camera(cam_obj, center, radius, direction, margin=1.18):
    """Objekt kadrga sig'sin (FOV hisobga olinadi)."""
    half_fov = math.atan((cam_obj.data.sensor_width / 2.0) / cam_obj.data.lens)
    dist = max(radius / max(math.tan(half_fov), 1e-3) * margin, 1e-3)
    pos = center + Vector(direction).normalized() * dist
    cam_obj.location = pos
    cam_obj.rotation_euler = (center - pos).to_track_quat("-Z", "Y").to_euler()
    return dist


fit_camera(cam, ctr, (hi - lo).length / 2.0, (1.0, -1.35, 0.75))
print(f"[CAM] center={[round(v,1) for v in ctr]} radius={round((hi-lo).length/2.0,1)} "
      f"engine={ENGINE}")


def add_sun(name, direction, strength, angle_deg=6.0):
    """`direction` — markazdan yorug'lik tomonga qaragan yo'nalish.
    Quyosh yorug'ligi o'z -Z yo'nalishida tarqaladi."""
    d = Vector(direction).normalized()
    ld = bpy.data.lights.new(name, type="SUN")
    ld.energy = strength
    ld.angle = math.radians(angle_deg)
    o = bpy.data.objects.new(name, ld)
    o.location = ctr + d * diag * 3
    o.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(o)
    return o


def add_area(name, direction, irradiance, size_frac=0.7):
    """Irradiansiya beriladi (W/m^2) va masofaga moslanadi — sahnaning
    birligi mm bo'lgani uchun oddiy 'energy = const' ishlamaydi."""
    pos = ctr + Vector(direction).normalized() * diag * 1.5
    d = max((pos - ctr).length, 1e-6)
    ld = bpy.data.lights.new(name, type="AREA")
    ld.energy = irradiance * 4.0 * math.pi * d * d
    ld.size = max(diag * size_frac, 1e-3)
    o = bpy.data.objects.new(name, ld)
    o.location = pos
    o.rotation_euler = (ctr - pos).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(o)
    return o


# primary = SUN (masofaga bog'liq emas — har doim to'g'ri yoritadi)
add_sun("Sun", (0.5, -0.8, 1.0), 4.0, 4.0)
add_area("Fill", (-1.4, -0.7, 0.35), 1.2, 0.9)
add_area("Rim", (0.2, 1.5, 0.9), 1.8, 0.5)

# --------------------------------------------------------------- save + render

blend_path = ARGS.out or os.path.join(OUT_DIR, f"{SPEC.get('object','assembly').lower().replace(' ','_')}.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[BLEND] {blend_path}")

report["bbox_mm"] = [round(v, 2) for v in (hi - lo)]
report["tris"] = sum(len(o.data.loop_triangles) if o.data.loop_triangles else 0
                     for o in bpy.data.objects if o.type == "MESH")
for o in bpy.data.objects:
    if o.type == "MESH":
        o.data.calc_loop_triangles()
report["tris"] = sum(len(o.data.loop_triangles)
                     for o in bpy.data.objects if o.type == "MESH")
json.dump(report, open(os.path.join(OUT_DIR, "assembly_report.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=2)

if not ARGS.no_render:
    targets = []
    if ARGS.render:
        targets.append(ARGS.render)
    else:
        targets.append(os.path.join(RENDERS, "preview.png"))
    for t in targets:
        scene.render.filepath = t
        bpy.ops.render.render(write_still=True)
        print(f"[RENDER] {t}")

print("[DONE]")
