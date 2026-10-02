---
name: forge
description: Obyektdan (masalan "LS V8 engine", "NASA rover", "qahva qurilma") detalli 3D model yasash. Google AI Studio'dan 3D sxema oladi, rasmlarni lokal ComfyUI + Qwen-Image-2.1 (GPU) da yaratadi, Image-To-3D (TRELLIS.2) bilan har bir qismni alohida 3D ga aylantiradi, sifatini tekshiradi va Blender'da GPU da yig'adi. Ishlatish: user "3D model yasab ber", "V8 engine yarat", "bu narsani 3D qil", "forge ishga tushir" desa.
---

# FORGE — obyektdan 3D model pipeline'i

## Nima qiladi

Bitta so'z bilan aytilsa, `forge/forge.py` **butta pipeline**'ni boshqaradi:

```
plan  ->  images  ->  model  ->  qc  ->  review  ->  assemble
          |           |         |                  |
     Google AI    ComfyUI    Image-To-3D        Blender
     Studio:      Qwen-Image (rasm -> GLB)      headless
     sxema        2.1 GGUF   TRELLIS.2         + Cycles
     (matn)       (lokal,GPU)                  (GPU/OPTIX)
```

Lekin **sening vazifang pipeline'ni boshqarish emas — sifatni boshqarish.**
Har bir bosqichdan keyin natijani ko'rib chiq, muammo bo'lsa tuzat.

##Muhit

| Nima | Qayerda |
|---|---|
| Pipeline | `<repo>\forge\forge.py` |
| Launcher | `forge\forge.bat` (Python'ni avtomatik topadi) |
| Serverlar | `forge\start_servers.bat` (ComfyUI + Image-To-3D) |
| Kalit | `forge\.env` → `GEMINI_API_KEY=` (faqat matn uchun) |
| ComfyUI | `<repo>\ComfyUI` (modellar `ComfyUI\models\`) |
| Image-To-3D | `<repo>\Image-To-3D` (modellar `Image-To-3D\models\`) |
| Blender | `<blender.exe>` |
| Loyihalar | `forge\projects\<slug>\` |
| **Joriy holat** | **`<repo>\HOLDOFF.md`** |

> **Rasm manbai Gemini emas** - AI Studio rasm kvotasi 0. Rasm lokal
> ComfyUI + Qwen-Image-2.1 da yaratiladi. Gemini faqat matn (sxema) uchun.

**Har bir ishni boshlashdan oldin:**

```powershell
cd <repo>
.\forge\start_servers.bat      # serverlar o'chgan bo'lsa
.\forge\forge.bat doctor       # hammasi OK bo'lishi kerak
```

> Serverlar OpenCode qayta ishga tushganda o'chib qoladi.
> Ikkala server **bir vaqtda ishlamaydi** (VRAM faqat 12 GB).

## Asosiy ish tartibi

```powershell
cd <repo>

# 0) muhitni tekshir
.\forge\forge.bat doctor

# 1) to'liq pipeline
.\forge\forge.bat run "LS V8 engine" --detail high

# ... yoki bosqichma-bosqich (uzun ish uchun shunday qil)
.\forge\forge.bat plan     "LS V8 engine" --detail high
.\forge\forge.bat images   "LS V8 engine"
.\forge\forge.bat model    "LS V8 engine" --seeds 4
.\forge\forge.bat qc       "LS V8 engine"
.\forge\forge.bat review   "LS V8 engine"
.\forge\forge.bat assemble "LS V8 engine"
```

`run` uzun (V8 engine uchun 40-90 daqiqa). Shuning uchun **`background: true`
bilan ishga tushir** va natijani ogohlantirishni kut.

## Natija fayllari

```
forge\projects\ls-v8-engine\
  spec.json                  ← qismlar, o'lchamlar, joylashuv, prompt'lar
  images\<part>.hero.png     ← referens rasm (silueti kesilgan, alpha bilan)
  meshes\<part>.glb          ← yakuniy 3D model
  meshes\<part>.alt1_0.78_s1.glb  ← qo'ng'iroq variantlar
  meshes\<part>.meta.json    ← IoU balli, ishlatilgan seed
  qc_report.json             ← sifat hisoboti
  renders\<part>\v00..v03.png ← turntable (vizual QC)
  out\<object>.blend         ← yig'ilgan Blender fayli
  out\assembly_report.json   ← nima qanday masshtablandi
  renders\preview.png
```

## Sifat nazorati — bu sening vazifang

`qc` bosqichi avtomatik ishlaydi, lekin **ikki tekshiruv qo'lda qoladi.**

### 1. QC balllarini o'qi

`qc_report.json` har bir qism uchun `ok`, `score`, `fix` beradi.

- `ok: true` — qabul
- `ok: false` — `fix` satrini o'q, sababni tushun, keyin **ikki variantdan birini** qo'lla:
  - **Geometriya muammosi** (buzilgan yuzalar, bo'laklar, nisbat noto'g'ri)
    → `model --only <part> --seeds 6 --force` (boshqa seed'lar bilan)
  - **Rasmdagi muammo** (fon ajratilmagan, burchak noto'g'ri, qism chalkash)
    → rasmni qayta generatsiya qil, `images --only <part> --force`,
      keyin `model --only <part> --force`
  - **`aspect_dev` katta, lekin rasm to'g'ri** → muammo sxemada:
    `spec.json` dagi `real_size_mm` ni tekshir va tuzat, so'ng `assemble`.

### 2. Renderlarni KUR

`renders\<part>\v00.png` ... `v03.png` — har bir qismning 4 burchakli ko'rinishi.

**Har bir render'ni `read` tool bilan ochib ko'r.** Render bo'lmasa model ishlamagan
degani — bu shart emas, pipeline buni o'zi hal qiladi.

Quyidagilarni tekshir:
- **geometriya buzilmaganmi** (chakka-chakkak, g'adorbud, "eritilgan" yuzalar)
- **qism tanilib turibdimi** (ikkita porshinning ko'rinishi bir xil bo'lsa —
  bu normal, lekin 8 ta porshin "koptok" bo'lib chiqsa — muammo)
- **fon va chegara** (model to'liq joylashgan, kesilmagan)
- **yo'nalish** (ko'rinish kerakli tomondan bo'lyapti)

Renderda muammo bo'lsa, eng tez tuzatish — **prompt'ni aniqlashtirish**:

`forge\projects\<slug>\spec.json` da `<part>` ning `image_prompt` va `description`
maydonlarini tahrirlab, keyin:

```powershell
.\forge\forge.bat images "LS V8 engine" --only <part> --force
.\forge\forge.bat model  "LS V8 engine" --only <part> --force
```

Prompt uchun foydali qo'shimchalar: `"clearly visible machining details"`,
`"distinct X features"`, `"orthographic-ish three-quarter view"`.

## Muhim cheklovlar (bularni bilish shart)

1. **Single-view.** TRELLIS.2 bu portda faqat **bitta** rasmni oladi. Shuning
   uchun har bir qismga **kanonik 3/4 burchak** generatsiya qilinadi
   (`--image-views hero`). Agar burchak noto'g'ri bo'lsa, orqa tomon
   taxmin qilinadi va model buziladi.
2. **Ko'p seed + IoU.** Bir seed bilan yon tomon noto'g'ri taxmin qilinishi
   mumkin. `model` shu sababli `--seeds` ta variant yaratib, rasmdagi
   siluet bilan IoU solishtirib eng yaxshisini tanlaydi. Default 4, muhim
   qismlar uchun 6-8. **IoU 0.75+ yaxshi natija.**
3. **Masshtab yo'q.** TRELLIS.2 haqiqiy o'lchamni bermaydi. Shu sababli
   `spec.json` dagi `real_size_mm` — yagona haqiqat manbai. `assemble` shu
   o'lchamga **teng masshtab** bilan sig'izadi (o'q bo'yicha cho'zmaydi,
   aks holda shakl buziladi). **Sxema noto'g'ri bo'lsa, model ham noto'g'ri.**
4. **Model yopiq emas.** TRELLIS.2 chiqishi ko'p bo'lakli (1000+),
   teshikli, ~1M uchburchakli — bu **normal**, QC buni jinoiy deb
   hisoblamaydi. `assemble` har bir qismni `--max-tris` (default 200 000)
   gacha siqadi, aks holda Blender juda sekinlashadi.
5. **Serverlar bir vaqtda ishlamaydi.** VRAM faqat 12 GB. ComfyUI
   generatsiyadan keyin VRAMni bo'shatmay turadi, shuning uchun Image-To-3D
   ishga tushmaydi:
   `ggml_vulkan: Device memory allocation ... ErrorOutOfDeviceMemory`.
   Yechim: ComfyUI'ga `/free` yuborish, 8 s kutish, keyin Image-To-3D.
   `start_servers.bat` ularni ketma-ket ishga tushiradi.
6. **Render** Cycles + **OPTIX (GPU)** bilan headless. EEVEE GPU konteksti
   yo'qligi uchun bo'sh rasm qaytaradi — bu normal, kod allaqachon
   Cycles'ga o'tgan. `FORGE_CYCLES_DEVICE=GPU`.
7. **ComfyUI `--highvram` ISHLATILMAYDI.** 12 GB GPU'da barcha modelni
   bir vaqtda ushlab olib RAM'ga suradi va `access violation` bilan
   crash bo'ladi. Standart "smart memory" rejimi ishlaydi: VRAM peak
   11.3-11.9/12.3 GB (92-96%), RAM ~3.4 GB.
8. **Partga bog'liq emas** — bu pipeline detalli **vizual** model yasaydi,
   funksional/rig'd (constraint) 3D emas. Mexanizm ishlashi uchun keyin
   qo'lda constraint qo'yish kerak.

## Qo'shimcha buyruqlar

```powershell
# qismlar sonini boshqarish
--detail draft|normal|high|ultra     # draft=6-10, ultra=24-40 qism

# faqat muammoli qismni qayta ishlatish
--only piston crank_shaft             # ko'p qismli

# sifat chegaralarini o'zgartirish
--seeds 6 --steps 24 --texture-steps 24
--max-tris 100000                    # yengilroq .blend
--res 1600 --samples 96              # render sifati

# qo'shimcha rasm burchaklari (3D ga faqat `hero` yuboriladi)
--image-views hero front side top
```

## Sifat chegaralari va ularni o'zgartirish

QC chegaralari TRELLIS.2 chiqishiga moslashtirilgan va `qc_report.json`
da har biri bo'yicha o'lchov yoziladi:

| O'lchov | Chegara | Nimani anglatadi |
|---|---|---|
| `triangles` | 5 000 – 6 000 000 | juda kam yoki juda ko'p |
| `degenerate_ratio` | ≤ 0.10 | buzilgan yuzalar |
| `largest_component` | ≥ 0.35 | asosiy qismning ulushi |
| `aspect_dev` | ≤ 0.45 | model nisbati sxemadan farq qilishi |

`aspect_dev` eng muhimi — **sxema va rasm kelishmayotganini ko'rsatadi.**
`axis_map` esa o'qlarning chalkashligini aytadi (GLB Y-up, Blender Z-up —
`assemble` buni avtomatik tuzatadi, `axis_map` faqat ma'lumot uchun).

## Natija haqida user'ga xabar berish

Render va `out\assembly_report.json` ni ko'rib, **aniq raqamlar bilan** ayt:
nechta qism, nechta GLB, jami uchburchak soni, `.blend` fayl yo'li, render yo'li.
Agar biror qim sifatsiz bo'lsa, uni yashirmasdan ayt va sababini yoz.

## Tez-tez uchraydigan muammolar

| Xato | Yechim |
|---|---|
| `[XATO] GEMINI_API_KEY yo'q` | `forge\.env` ga kalitni yoz |
| `Server ishlamayapti` | `Image-To-3D\start_server.bat` |
| `ggml_gallocr_alloc_graph failed` | Boshqa GPU dasturini (o'yin, boshqa AI) yop |
| Renderda qism ko'rinmaydi | `spec.json` dagi `placement.location_mm` ni tekshir |
| Render **butunlay bo'sh / qorong'i** | `doctor` ni ishga tushir; `FORGE_RENDER_ENGINE=CYCLES` |
| Model juda yassilangan | `--only <part> --seeds 8 --force` |
| Blender juda sekin | `--max-tris 60000` |
| Blender `[MISS] <part>: GLB yo'q` | `model` bosqichini o'tkazilmagan |
| Model to'g'ri joylashmagan | `spec.json` dagi `location_mm` / `rotation_deg` ni qo'lda tahrirlab `assemble` ni qayta ishga tushur |
| `bmesh.ops.decimate doesn't exist` | Blender 5.2 — kod allaqachon Decimate modifieridan foydalanadi |

## Fayllarni qo'lda tahrirlash

`spec.json` — pipeline'ning **nervi**. Qo'lda o'zgartirish eng kuchli
vosita. Ishlatiladigan maydonlar:

```jsonc
{
  "parts": [{
    "id": "piston",
    "real_size_mm": [86, 86, 55],          // X, Y, Z (uzunlik, kenglik, balandlik)
    "color": "#c8ccd2",
    "image_prompt": "...",
    "placement": {
      "location_mm": [0, 0, 120],          // obyekt markaziga nisbatan
      "rotation_deg": [0, 0, 0],
      "symmetry": "bore"                  // none|x|y|z|bore|corner|radial
    },
    "count": 8
  }]
}
```

- `symmetry` + `count` → ko'p nusxa. Masalan 8 porshin: `count: 8, symmetry: "bore"`
  (X o'qi bo'ylab `real_size_mm[0] * 1.35` qadam bilan teriladi).
- `location_mm` — barcha nusxalar guruhining markazi.
- `rotation_deg` — Euler XYZ, darajada.

Tahrir qilgandan keyin **faqat** `assemble` ni qayta ishga tushir
(model qayta yaratish shart emas).
