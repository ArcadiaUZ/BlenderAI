"""1-Bosqich: obyektni qismlarga bo'lish + 3D sxema.

Gemini matn modelidan so'raydi:
  - qismlar ro'yxati (ism, tavsif, material)
  - har bir qismning haqiqiy o'lchamlari (mm) va proporsiyasi
  - har bir qismning image-generation prompt'i (3/4 ko'rinish, oq fon)
  - har bir qismning joylashuvi (location_mm, rotation_deg) va materiali

Natija: projects/<slug>/spec.json
"""
from . import config, gemini

SYSTEM = (
    "Siz tajribali 3D muhandis va texnik illyustrator ekzaspert ekasiz. "
    "Siz aniq raqamli o'lchamlar va real fizikadagi nisbatlarga qattiq rioya qilasiz. "
    "Javoblarni faqat JSON ko'rinishida berasiz."
)

SCHEMA_HINT = """
Qaytariladigan JSON tuzilmasi:
{
  "object": "<obyekt nomi>",
  "units": "mm",
  "overall_size_mm": [L, W, H],
  "summary": "<1-2 jumla>",
  "parts": [
    {
      "id": "engine_block",              // ascii, lower_snake_case, unique
      "name": "Engine Block",
      "description": "<qismni 1-2 cümleda aniq tasvirlash>",
      "material": "cast aluminium / steel / plastic / rubber / glass",
      "color": "#8a8f96",
      "count": 1,                        // >1 bo'lsa ko'p nusxa
      "real_size_mm": [L, W, H],         // eng uzun o'q X, keyin Y, keyin Z
      "complexity": "simple|medium|complex",
      "image_prompt": "<English prompt for photoreal 3/4 view render, single part, isolated, white background>",
      "placement": {
        "location_mm": [x, y, z],        // markaz nuqtasi, butun obyekt koordinatalari
        "rotation_deg": [rx, ry, rz],   // Euler XYZ
        "symmetry": "none|x|corner|bore" // ko'p nusxa uchun: bo'sh = faqat 1 ta
      }
    }
  ]
}
"""

RULES = """
Qoidalar:
1. Har bir qism ALOHIDA va MODELLANADIGAN bo'lsin. "chiroyli dizayn", "majmua",
   "kompleks" kabi yagona bo'lakli qismlarni BERMA — ular 3D ga aylantirilmaydi.
2. Bir-biriga yopishib ketadigan yoki ko'rinmaydigan ichki mexanizmlar
   (masalan valv ichidagi pru-shina) alohida qism qilinmasin.
3. real_size_mm — real dunyo qiymatlari bo'lsin. Masalan porshin Ø86 mm,
   porshin balandligi ~55 mm, krankvali ~ 400-500 mm, blok ~ 500x500x400.
4. image_prompt INGLIZ tilida bo'lsin va majburiy ravishda shu jumlalarni o'z ichiga
   olsin: "single isolated part", "three-quarter view", "clean pure white
   background", "studio product photography", "no other objects", "no text",
   "sharp focus", "matte PBR-ish surface".
5. Symmetrik qismlar (porshin, klapan, cilindr) uchun count > 1 va
   symmetry mos qiling. Asosiy qism count=1.
6. Qismlar soni 8 dan 28 oriqida bo'lsin (chunonchi juda uzoq).
7. placement koordinatalari butun obyektning o'z markaziga nisbatan,
   millimetrlarda. Obyekt Z o'qi bo'ylab tik (yuqoriga) qaragan bo'lsin,
   pastki yuz Z=0 da.
8. Ranglar `#rrggbb` ko'rinishida.
9. description va image_prompt boshqa qismlarga qaramay DIQATLI bo'lsin:
   har bir qist o'ziga xos bo'sin (8 ta porshin bir xil emas, balki 8 xil
   "piston" deb atalmasin).
"""


def build(object_name, detail="high", extra="", language="en"):
    """spec dict qaytaradi (yozmaydi)."""
    dmap = {
        "draft": "6-10 qism, sodda, tez",
        "normal": "12-18 qism",
        "high": "18-28 qism, maksimal detallar, har bir mexanik qism alohida",
        "ultra": "24-40 qism, ichki mexanizmlar bilan",
    }
    lvl = dmap.get(detail, detail)
    prompt = (
        f"Obyekt: {object_name}\n"
        f"Detallik darajasi: {lvl}\n"
        + (f"Qo'shimcha talablar: {extra}\n" if extra else "")
        + f"\nBu obyektning real 3D modelini yasash uchun qismlar ro'yxatini, "
          f"har bir qismning aniq 3D o'lchamlarini va kerakli render prompt'larini tuz.\n"
          f"{RULES}"
    )
    data = gemini.json_text(
        prompt,
        schema_hint=SCHEMA_HINT,
        system=SYSTEM,
        temperature=0.5,
    )
    if isinstance(data, list):
        data = {"parts": data}
    if "parts" not in data or not isinstance(data["parts"], list) or not data["parts"]:
        raise RuntimeError("Gemini qismlar ro'yxatini qaytarmadi")

    # --- normalizatsiya va tekshiruv
    seen = set()
    cleaned = []
    for i, p in enumerate(data["parts"]):
        pid = str(p.get("id") or f"part_{i}").strip().lower()
        pid = "".join(c if (c.isalnum() or c == "_") else "_" for c in pid)
        while pid in seen:
            pid = f"{pid}_{i}"
        seen.add(pid)
        size = _vec3(p.get("real_size_mm"), 50.0)
        count = max(1, int(p.get("count") or 1))
        pl = p.get("placement") or {}
        cleaned.append({
            "id": pid,
            "name": p.get("name") or pid,
            "description": p.get("description") or "",
            "material": p.get("material") or "steel",
            "color": _hex(p.get("color"), "#9aa0a6"),
            "count": count,
            "real_size_mm": [round(x, 2) for x in size],
            "complexity": p.get("complexity") or "medium",
            "image_prompt": (p.get("image_prompt") or p.get("description") or pid).strip(),
            "placement": {
                "location_mm": [round(x, 2) for x in _vec3(pl.get("location_mm"), 0.0)],
                "rotation_deg": [round(x, 2) for x in _vec3(pl.get("rotation_deg"), 0.0)],
                "symmetry": (pl.get("symmetry") or "none"),
            },
        })

    data["parts"] = cleaned
    data["object"] = data.get("object") or object_name
    data["units"] = "mm"
    data["detail"] = detail
    return data


def _vec3(v, default):
    try:
        a = [float(x) for x in list(v)[:3]]
    except Exception:
        a = []
    while len(a) < 3:
        a.append(default)
    return [abs(x) if default > 0 else x for x in a]


def _hex(v, default):
    s = str(v or "").strip()
    if s.startswith("#") and len(s) in (7, 9):
        return s[:7].upper()
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return "#" + s.upper()
    return default


def generate_and_save(object_name, proj, detail="high", extra=""):
    spec = build(object_name, detail=detail, extra=extra)
    path = proj / "spec.json"
    config.write_json(path, spec)
    config.say(f"  [1/5] spec tayyor -> {path}  ({len(spec['parts'])} qism)")
    return spec
