# FORGE — obyektdan detalli 3D model

Obyekt nomini yozasiz — pipeline o'sha obyektni **qism-qism** 3D modelga
aylantiradi: sxema chiqaradi, har bir qism uchun rasm yaratadi, rasmni
TRELLIS.2 bilan 3D ga aylantiradi, sifatini tekshiradi va Blender'da
bitta yig'ilgan model sifatida render qiladi.

```
plan  ->  images  ->  model  ->  qc  ->  review  ->  assemble
          |           |         |                  |
     Google AI    ComfyUI    Image-To-3D        Blender
     Studio:      Qwen-Image (rasm -> GLB)      headless
     sxema        2.1 GGUF   TRELLIS.2         + Cycles
     (matn)       (lokal,GPU)                  (GPU/OPTIX)
```

**Misol:** `forge\forge.bat run "LS V8 engine" --detail high` — porshin,
krivoshaft, klapan va boshqa ~8 qism, hammasi alohida 3D.

---

## Nima uchun shu yo'l

Har bir obyektni **butun bitta rasm**dan 3D qilish mumkin emas — model
butun geometriyani buzadi. Shu sababli obyekt **qismlarga** bo'linadi,
har bir qism uchun kanonik 3/4 burchakdagi rasm yaratiladi, har bir qism
alohida 3D ga aylanadi va keyin `spec.json` dagi haqiqiy millimetr
o'lchamlar bo'yicha yig'iladi.

> **Rasm manbai Gemini emas.** AI Studio rasm kvotasi 0, shuning uchun
> rasm **lokal ComfyUI + Qwen-Image-2.1** da GPU'da yaratiladi.
> Gemini faqat **matn** (sxema) uchun ishlatiladi.

---

## Talablar

| Nima | Talab |
|---|---|
| OS | Windows 10/11 x64 |
| GPU | NVIDIA, ~12 GB VRAM (RTX 3060 o'lchangan) |
| RAM | 16 GB |
| Blender | 4.x+ (headless render uchun) |
| Disk | ~40 GB bo'sh (modellar ~26 GB) |
| Internet | birinchi o'rnatishda ~26 GB |

---

## O'rnatish

Windows da bitta fayl:

```bat
setup\setup_all.bat
```

Bosqichma-bosqich:

| # | Skript | Nima qiladi |
|---|---|---|
| 01 | `setup\01_setup_python.bat` | ComfyUI + ComfyUI-GGUF klon, venv, torch (CUDA 12.8) |
| 02 | `setup\02_download_models.bat` | Qwen-Image-2.1 unet + text encoder + VAE (~11 GB) |
| 03 | `setup\03_setup_image_to_3d.bat` | Image-To-3D: kod, build, TRELLIS.2 modellari (~15 GB) |
| 04 | `setup\04_setup_env.bat` | `forge\.env` yaratish + Blender izlash |

> 03-bosqich birinchi marta Visual Studio Build Tools o'rnatishi mumkin.
> Keyin terminalni **qayta ochib** skriptni yana ishga tushiring.

Keyin `forge\.env` faylida **faqat bitta narsa** qo'lda to'ldiriladi:

```ini
GEMINI_API_KEY=...        # https://aistudio.google.com/apikey
```

## Ishga tushirish

```bat
forge\start_servers.bat                       :: ComfyUI + Image-To-3D
forge\forge.bat doctor                        :: hammasi OK bo'lishi kerak
forge\forge.bat run "LS V8 engine" --detail high
```

> Serverlar bir vaqtda **ishlamaydi** — VRAM faqat 12 GB.
> `start_servers.bat` ularni ketma-ket ishga tushiradi va ComfyUI'dan
> keyin VRAMni bo'shatadi.

---

## Buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `doctor` | kalit / server / Blender / paketlarni tekshirish |
| `plan` | `spec.json` yaratish (qismlar + mm o'lcham + joylashuv) |
| `images` | har bir qism uchun referens rasm |
| `model` | rasmdan 3D GLB (ko'p seed, IoU bo'yicha tanlash) |
| `qc` | sifat nazorati + avtomatik qayta urinish |
| `review` | har bir qismning turntable renderi |
| `assemble` | Blender'da yig'ish, `.blend` + render |
| `run` | hammasi ketma-ket |

Muhim bayroqlar:

```
--detail draft|normal|high|ultra   qismlar soni (6-10 ... 24-40)
--only <part> [<part> ...]         faqat berilgan qismlarni qayta ishlash
--seeds N                          har bir rasm uchun variantlar soni
--steps N --texture-steps N        TRELLIS.2 sampling qadamlari
--max-tris N                       har bir qism uchun uchburchak limiti
--image-views hero front side top  rasm bosqichi burchaklari
--review-views N                   turntable burchaklar soni
--force                            mavjud natijani qayta yaratish
```

---

## Tuzilma

```
forge/
  forge.py              CLI, barcha bosqichlarni boshqaradi
  forge.bat             Python'ni avtomatik topib ishga tushiradi
  start_servers.bat     ComfyUI + Image-To-3D ni ishga tushiradi
  modules/
    config.py           .env, yo'llar, umumiy yordamchilar
    gemini.py           AI Studio REST mijozi (matn uchun)
    planner.py          3D sxema: qismlar, mm o'lcham, joylashuv, prompt'lar
    imagegen.py         Referens rasm + backend tanlash (local / gemini)
    imagegen_local.py   ComfyUI mijozi, Qwen-Image-2.1 graph, VRAM monitoring
    i2i3d.py            Image-To-3D mijozi, ko'p seed + IoU tanlash
    qc.py               GLB sifat nazorati, o'q mosligini aniqlash
  blender/
    assemble.py         import, o'q mosligi, masshtab, yig'ish, render
    render.py           turntable render (vizual QC)
setup/                  birinchi o'rnatish skriptlari (yuqoriga qarang)
docs/HOLDOFF.md         loyihaning to'liq texnik holati va qarorlar
.opencode/skill/forge/  OpenCode uchun ish yo'riqnomasi (SKILL.md)
```

---

## Natija

```
forge/projects/<slug>/
  spec.json              qismlar, mm o'lchamlar, joylashuv, prompt'lar
  images/<part>.hero.png referens rasm (siluet kesilgan)
  meshes/<part>.glb      3D model
  meshes/<part>.meta.json IoU balli, ishlatilgan seed
  qc_report.json         sifat hisoboti
  renders/<part>/v*.png  turntable (vizual QC)
  out/<object>.blend     yig'ilgan Blender fayli
  renders/preview.png
```

---

## Modellar

Model **hech qachon** git'ga tushmaydi — `setup\02_download_models.bat`
Hugging Face'dan yuklaydi.

| Model | Fayl | Hajm |
|---|---|---|
| Unet (ishlatiladi) | `qwen_image_2.1_Q4_K_M.gguf` | 3.995 GB |
| Unet (saqlanadi, ishlatilmaydi) | `qwen_image_2.1_Q6_K.gguf` | 5.604 GB |
| Text encoder | `qwen3vl_8b_w4a8.safetensors` | 6.020 GB |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` | 644 MB |
| TRELLIS.2 GGUF | 10 ta fayl (`Image-To-3D\models\`) | ~15.3 GB |

**Q6_K nima uchun ishlatilmaydi:** 5.6 + 6.0 + 0.6 = 12.2 GB > 12.3 GB
VRAM. Faqat diskda saqlanadi.

---

## GPU va xotira (12 GB RTX 3060)

Byudjet: unet 3.995 + text encoder 6.020 + VAE 0.644 = **10.66 GB**.
Qolgan ~1.6 GB aktivatsiyaga.

| Ko'rsatkich | Natija |
|---|---|
| VRAM peak (rasm) | 11.3 - 11.9 GB / 12.3 GB (92-96%) |
| ComfyUI haqiqiy RAM | 3.4 GB (barqaror, leak yo'q) |
| Rasm tezligi (1024px, 20 qadam) | ~95 s |

| Nima uchun | |
|---|---|
| `--highvram` **ishlatilmaydi** | 12 GB GPU'da RAM'ga suradi va `access violation` bilan crash bo'ladi |
| community "heretic" GGUF TE ishlatilmaydi | kalit nomlari mos kelmaydi -> shovqin. Rasmiy safetensors ishlatiladi |
| Har rasmdan oldin `/free` | aks holda kesh RAM'ni to'ldirib, keyingi ish "not enough memory" bilan yiqiladi |
| `--disable-pinned-memory` | 15.8 GB RAM da pinned xotira kerak emas |

---

## Muhim cheklovlar

- **Single-view.** TRELLIS.2 bu portda bitta rasm oladi. Har bir qismga
  kanonik 3/4 burchak generatsiya qilinadi; burchak noto'g'ri bo'lsa
  orqa tomon taxmin qilinadi va model buziladi.
- **Masshtab yo'q.** TRELLIS.2 haqiqiy o'lcham bermaydi. `spec.json` dagi
  `real_size_mm` — yagona haqiqat manbai, undan **teng masshtab** bilan
  o'lchamga sig'iziladi (non-uniform emas).
- **Yopiq mesh emas.** TRELLIS.2 chiqishi ko'p bo'lakli va teshikli —
  bu normal. QC yopiqlikni jinoiy deb hisoblamaydi.
- **Render** Cycles + **OPTIX (GPU)** bilan headless. EEVEE GPU konteksti
  yo'qligi uchun bo'sh rasm qaytaradi.
- **Vizual model**, constraint'siz mexanik emas. Harakat qo'shish uchun
  keyin qo'lda constraint kerak.

Qo'shimcha texnik qarorlar va o'lchangan natijalar:
[`docs/HOLDOFF.md`](docs/HOLDOFF.md)

---

## Tashqi loyihalar

| Loyiha | Vazifasi |
|---|---|
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | Qwen-Image-2.1 rasm generatsiyasi |
| [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | GGUF unet yuklash |
| [Image-To-3D](https://github.com/ArcadiaUZ/Image-To-3D) | TRELLIS.2 (C++/ggml + Vulkan), rasm -> GLB |

## Litsenziya

MIT