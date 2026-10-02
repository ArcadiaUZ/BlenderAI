@echo off
REM ============================================================
REM  02) ComfyUI modellarini yuklash  (~11 GB)
REM
REM  Manba: Hugging Face. Hajm tekshiriladi, yuklash uzilganda
REM  davom ettiriladi (curl -C -). Internet ~11 GB kerak.
REM
REM  Ishlatiladigan yagona unet - Q4_K_M (3.995 GB). Q6_K (5.6 GB)
REM  12 GB VRAM'ga sig'maydi, shuning uchun yuklanmaydi.
REM
REM  TRELLIS.2 modellari (~15 GB) alohida:
REM     setup\download_models.ps1 -TrellisOnly
REM  yoki to'liq avtomatik ravishda 03-bosqich orqali.
REM ============================================================
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_models.ps1"
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" goto fail
echo   Keyingi:  setup\03_setup_image_to_3d.bat
pause
exit /b 0
:fail
echo   [xato] Ba'zi modellar yuklanmadi - yuqoridagi xabarni o'qing.
pause
exit /b %RC%