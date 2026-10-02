@echo off
REM ============================================================
REM  setup_all.bat - to'liq o'rnatish (ketma-ket)
REM
REM   01  Python venv + ComfyUI manba kodi + ComfyUI-GGUF
REM   02  ComfyUI modellari (~11 GB)
REM   03  Image-To-3D: kod, build, TRELLIS.2 modellari (~15 GB)
REM   04  forge\.env + Blender tekshiruvi
REM
REM  Jami yuklash: ~26 GB, vaqt: internetga bog'liq (1-3 soat).
REM  Har bosqich o'zidan oldingisini talab qiladi - ketma-ket
REM  ishga tushiriladi. Xato bo'lsa shu bosqichda to'xtaydi.
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================================
echo   FORGE - to'liq o'rnatish
echo ============================================================
echo.

for %%B in (01_setup_python.bat 02_download_models.bat 03_setup_image_to_3d.bat 04_setup_env.bat) do (
  echo.
  echo ------------------------------------------------------------
  echo   %%B
  echo ------------------------------------------------------------
  call "%%B"
  if errorlevel 1 (
    echo.
    echo [XATO] %%B muvaffaqiyatsiz bo'ldi. Yuqoridagi xabarni o'qing,
    echo        muammoni tuzatib, shu bosqichni qayta ishga tushiring.
    pause
    exit /b 1
  )
)

echo.
echo ============================================================
echo   TAYYOR
echo ============================================================
pause
exit /b 0