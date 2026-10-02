# FORGE — Holat hujjati

> **Oxirgi yangilanish:** 2026-09-27, kechqurun
> **Maqsad:** obyekt nomi (masalan "LS V8 engine") → 3D sxema → har qism uchun rasm → TRELLIS.2 orqali 3D → QC → Blender'da yig'ish.
> **Hozirgi holat:** infratuzilma to'liq qurilgan va GPU'da ishlaydi. **Birinchi haqiqiy ish (LS V8 engine) hali oxirigacha bajarilmagan.**

---

## 1. Nima qilindi (bajarilgan)

### 1.1 Komponentlar (barchasi `D:\AI\BlenderAI` da, portable)

| Papka | Hajm | Vazifasi |
|---|---|---|
| `ComfyUI\` | models 15.88 GB + venv 5.50 GB | Rasmlar (Qwen-Image-2.1) |
| `Image-To-3D\` | 16.18 GB (models 15.31 GB) | Rasmdan 3D (TRELLIS.2, Vulkan) |
| `forge\` | ~0.5 MB | Pipeline kodi + konfiguratsiya |
| `cache\` | yangi | HF/Torch kesh (avval C: da edi) |

> **C: da hech qanday model yo'q.** `C:\Users\Arcadia\.cache\huggingface` dagi 8.1 GB — sizning
> **boshqa** loyihalaringiz (TTS, Whisper, audio separation). Ular tegilmadi.
> Eski urinishdan qolgan bo'sh `models--Qwen--Qwen-Image-2.1` papkasi (41 bayt) o'chirildi.

### 1.2 Modellar (joyida, o'z papkasida)

**ComfyUI/models/**
```
text_encoders/qwen3vl_8b_w4a8.safetensors   6,020 MB   <- rasmiy TE
unet/qwen_image_2.1_Q4_K_M.gguf            3,995 MB   <- ishlatiladi
unet/qwen_image_2.1_Q6_K.gguf              5,604 MB   <- saqlangan, ishlatilmaydi (sig'maydi)
vae/qwen_image_2.1_vae_bf16.safetensors      644 MB
```

**Image-To-3D/models/** — TRELLIS.2 GGUF (15.31 GB), `start_server.bat` orqali `-ggufs` bilan
o'z papkasidan o'qiydi, tashqi kesh ishlatmaydi.

### 1.3 GPU'da ishlash — tasdiqlangan

Sizning talabingiz: **VRAM da ishlasin, CPU offload bo'lmasin.**

O'lchovlar (nvidia-smi, `Image-To-3D` o'chirilgan holda):

| Ko'rsatkich | Natija |
|---|---|
| VRAM peak (generatsiya davomida) | **11,304 – 11,862 MB / 12,288 MB (92–96%)** |
| Hisob joyi | **to'liq GPU** |
| ComfyUI haqiqiy RAM (Working Set) | **3,420 MB** (barqaror, leak yo'q) |
| ComfyUI commit (mmap) | 12.2 GB — fayl bilan bog'langan, **bo'sha evriladi** |
| Tezlik | 20 qadam / 1024px = **94–97 s** |
| BLENDER render | **OPTIX / RTX 3060** (`FORGE_CYCLES_DEVICE=GPU`) |

### 1.4 Tuzatilgan xatolar (jami 11)

**Image qo'lda (rasm) tomoni:**
1. Gemini rasm kvotasi 0 → **ComfyUI + Qwen-Image-2.1** ga o'tildi
2. `--highvram` → RAM'ni 8 GB to'ldirdi + `access violation` crash → **standart "smart memory" rejimi**
3. Q6_K unet + w4a8 TE = 11.98 GB → 12 GB GPU'ga sig'madi → **Q4_K_M unet** (3.995 GB)
4. community "heretic" GGUF text encoder → `12288 != 4096` shakl xatosi, shovqin chiqaradi
   → **rasmiy `qwen3vl_8b_w4a8.safetensors`**
5. Ketma-ket generatsiyalarda `DefaultCPUAllocator: not enough memory` →
   **har generatsiyadan oldin `/free`** (`pre_free=True`)
6. `--highvram` olib tashlandi, `--disable-pinned-memory` qo'shildi
7. **VRAM monitoring** qo'shildi (`_Watch`): har rasmda peak VRAM/RAM chiqadi
8. **Working-set trim** qo'shildi (`_trim_comfy_working_set`): RAM 11.4 → 9.6 GB

**Blender tomoni (avvalgi sessiyada):**
9. Kamera `clip_end=100` mm-o'lchamli sahna kesib qo'yardi
10. EEVEE headless bo'sh rasm berardi → **Cycles**; AgX rangni ezdi → `view_transform="Standard"`
11. GLB Y-up/Blender Z-up o'q burilishi, `best_axis_map` (6 ta permutatsiya),
    `fix_normals`, `Decimate` modifier (1M → 60K uch)

### 1.5 Ishlaydigan zanjir

```
plan  → Gemini (matn) → spec.json          [TASDIQLANGAN, 8 qism, haqiqiy mm]
images → ComfyUI Qwen-Image-2.1 → PNG      [GPU da TASDIQLANGAN, 2/2 rasm]
model  → Image-To-3D TRELLIS.2 → GLB       [sinovdan o'tgan, IoU 0.879, QC 5/5]
qc     → mesh tekshiruvi                   [sinovdan o'tgan]
assemble → Blender Cycles OPTIX            [sinovdan o'tgan, endi GPU da]
```

---

## 2. Nima qilinmagan (keyingi qadamlar)

### 2.1 ❌ ENG MUHIM: haqiqiy ishni oxirigacha bajartish hech qachon

`forge\forge.py images "LS V8 engine"` **ishga tushmagan** — `Start-Process` bilan chaqirilganda
qo'shtirnoq (argument) buzildi:

```
forge: error: unrecognized arguments: V8 engine
```

**Tuzatish:** `Start-Process` o'rniga `forge\forge.bat` yoki to'g'ri tirnoq bilan ishga tushiring:

```powershell
cd D:\AI\BlenderAI
& python forge\forge.py images "LS V8 engine"      # tirnoq PIT
```

Yoki fon rejimida:
```powershell
$p = Start-Process python -ArgumentList 'forge\forge.py','images','"LS V8 engine"' -NoNewWindow -PassThru
```

### 2.2 To'liq birinchi ish, tartib bilan

```powershell
cd D:\AI\BlenderAI
.\forge\start_servers.bat          # 1) Ikkala serverni ishga tushiradi
.\forge\forge.bat doctor           # 2) Barcha qatorlar OK bo'lishi kerak

.\forge\forge.bat images "LS V8 engine"    # 3) 8 ta rasm  (~20 daqiqa, 30 qadam)
.\forge\forge.bat model  "LS V8 engine"    # 4) 8 ta GLB  (har biri 3-8 min)
.\forge\forge.bat qc     "LS V8 engine"    # 5) mesh tekshiruvi
.\forge\forge.bat assemble "LS V8 engine"  # 6) Blender'da yig'ish + GPU render
.\forge\forge.bat review  "LS V8 engine"   # 7) turntable ko'rish
```

> `.bat` ichida `Image-To-3D\.venv\Scripts\python.exe` avtomatik tanlanadi
> (trimesh/scipy/numpy/PIL bor).

### 2.3 ⚠️ VRAM mojarosi — serverlarni ketma-ket ishga tushiring

Ikkala server bir vaqtda ishlamaydi:

```
ggml_vulkan: Device memory allocation of size 500353056 failed.
pipeline load: ss_flow: failed to allocate weights on backend NVIDIA GeForce RTX 3060
```

ComfyUI generatsiyadan keyin VRAMni bo'shatmay turadi. Yechim `generate()` ichidagi `pre_free`
bo'lishi kerak, lekin **qo'lda** server ishga tushirilganda:

```powershell
# ComfyUI ni bo'shatish
Invoke-RestMethod http://127.0.0.1:8188/free -Method Post `
  -Body '{"unload_models":true,"free_memory":true}' -ContentType "application/json"
# 8 sekund kutamiz, VRAM ~1.4 GB ga tushadi
Image-To-3D\start_server.bat
```

`start_servers.bat` hozir Image-To-3D'ni **avval** ishga tushiradi, ComfyUI keyin —
bu to'g'ri tartib. `doctor` ham shu tartibda bo'lishi kerak.

### 2.4 Blender GPU render tekshirilmagan

`FORGE_CYCLES_DEVICE=GPU` / `FORGE_CYCLES_BACKEND=OPTIX` yozildi va
Blender RTX 3060'ni OPTIX sifatida topdi, lekin **haqiqiy render hali ishga tushirilmagan**.
Tekshirish:

```powershell
.\forge\forge.bat assemble "LS V8 engine" --dry-run
# yoki kichik bir qism bilan
.\forge\forge.bat render "LS V8 engine" --part valve_cover
```

Jurnalda `[GPU] sozlanmadi -> CPU` chiqsa, muammo bor.

### 2.5 Hujjatlar yangilanishi kerak

| Fayl | Holat |
|---|---|
| `forge\README.md` | **Eski** — Gemini'ni rasm manbai deb yozgan |
| `.opencode\skill\forge\SKILL.md` | **Eski** — xuddi shu muammo, `start_servers.bat` ham yo'q |
| `HOLDOFF.md` (shu fayl) | Yangi, hozirgi holat |

### 2.6 Tozalash (ixtiyoriy, xavfsiz)

```
D:\AI\BlenderAI\
  dl_q4.bat, dl_q4.log            <- yuklash skriptlari (ishlatildi)
  dl_models.bat, dl_models.log    <- shu
  ss.log                          <- server sinovi
  images_run.log, images_run.err  <- muvaffaqiyatsiz urinish
  ComfyUI\comfyui_start.log, comfyui_err.log
  forge\projects\_t1.png, _t2.png, _gpu_test.png   <- test rasmlari
```

---

## 3. Konfiguratsiya (`forge\.env`)

```ini
GEMINI_API_KEY=***                # matn modeli uchun (sxema) - .env da saqlanadi
FORGE_TEXT_MODEL=gemini-3.7-flash
FORGE_IMAGE_BACKEND=local           # ComfyUI (Gemini rasm kvotasi 0)

FORGE_RENDER_ENGINE=CYCLES
FORGE_CYCLES_DEVICE=GPU             # CPU EMAS
FORGE_CYCLES_BACKEND=OPTIX

COMFY_URL=http://127.0.0.1:8188
FORGE_COMFY_PATH=D:\AI\BlenderAI\ComfyUI
FORGE_GGUF=qwen_image_2.1_Q4_K_M.gguf
FORGE_COMFY_CLIP=qwen3vl_8b_w4a8.safetensors
FORGE_COMFY_VAE=qwen_image_2.1_vae_bf16.safetensors
FORGE_COMFY_STEPS=30
FORGE_COMFY_RES=1024
FORGE_COMFY_RESERVE_VRAM=0.5        # 0.3 sababsiz edi — 0.5 barqaror

FORGE_I2I3D_URL=http://127.0.0.1:8742
FORGE_BLENDER=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe

# PORTABLE: hammasi D: da
FORGE_CACHE_ROOT=D:\AI\BlenderAI\cache
HF_HOME=D:\AI\BlenderAI\cache\hf
HF_HUB_CACHE=D:\AI\BlenderAI\cache\hf\hub
TORCH_HOME=D:\AI\BlenderAI\cache\torch
```

`FORGE_CACHE_ROOT` va uning ichidagi 3 ta o'zgaruvchi `modules/config.py` da
avtomatik yaratiladi va barcha child process'larga (ComfyUI, Image-To-3D) meros bo'ladi.

---

## 4. Nima o'zgartirilgan (kod)

| Fayl | O'zgarish |
|---|---|
| `forge\modules\imagegen_local.py` | Q4 unet, `CLIPLoaderGGUF` avtomatik tanlash, `_Watch` (VRAM/RAM monitor), `_trim_comfy_working_set`, `pre_free`, `--disable-pinned-memory`, `_await` tuzatilgan |
| `forge\modules\config.py` | Kesh papkalarini avtomatik yaratish |
| `forge\blender\assemble.py` | OPTIX/GPU qo'llab-quvvatlash, CPU'ga qaytishdan saqlanish |
| `forge\blender\render.py` | Xuddi shu |
| `forge\start_servers.bat` | Kesh o'zgaruvchilari, `--highvram` olib tashlandi, `--disable-pinned-memory` |
| `forge\.env` | Q4 unet + rasmiy TE, GPU render, kesh yo'llari |

---

## 5. Texnik qarorlar (sabablar bilan)

| Qaror | Sabab |
|---|---|
| Q4_K_M unet (3.995 GB), Q6_K emas | Q6 + TE + VAE = 11.98 GB > 12.288 GB VRAM. Q6 faqat noma yozuv, ishlatilmaydi |
| Rasmiy safetensors TE (6.0 GB) | community "heretic" GGUF kalit nomlari mos kelmaydi → shovqin |
| `--highvram` YO'Q | 12 GB GPU'da barcha modelni ushlab olib, RAM'ga suradi + `access violation` |
| Standart "smart memory" | Hisob **GPU da** (92–96% VRAM), RAM faqat bo'sha evriladigan mmap |
| BLENDER render Cycles/OPTIX | EEVEE headless bo'sh rasm beradi; Cycles GPU da ishlaydi |
| `--max-tris` decimatsiya | 20+ qism × 1M uch = Blender ishlamaydi |
| `spec.json` `real_size_mm` — yagona haqiqat manbai | Qismlar bir xil nisbatda masshtablanadi (non-uniform emas) |

---

## 6. Qisqa "keyingi sessiya" uchun

```
1. cd D:\AI\BlenderAI
2. .\forge\start_servers.bat
3. .\forge\forge.bat doctor              # hammasi OK bo'lishi kerak
4. .\forge\forge.bat images "LS V8 engine"   # ~20 min
5. Rasmlarni ko'rib chiqish -> kerak bo'lsa qayta generatsiya
6. .\forge\forge.bat run "LS V8 engine"      # model -> qc -> assemble
7. Natija: forge\projects\ls-v8-engine\
```

**Eslatma:** serverlar OpenCode qayta ishga tushganda o'chib qoladi —
`start_servers.bat` ni qayta ishga tushiring.
