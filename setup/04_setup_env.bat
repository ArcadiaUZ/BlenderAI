@echo off
REM ============================================================
REM  04) forge\.env yaratish + Blender tekshiruvi
REM
REM  .env.example -> .env nusxalanadi. Ichiga Google AI Studio
REM  kalitini qo'lda yozish kerak (FAQAT matn uchun: sxema,
REM  qismlar, prompt'lar - rasm lokal ComfyUI'da yaratiladi).
REM
REM  forge/.env  hech qachon git'ga tushmaydi.
REM ============================================================
setlocal
cd /d "%~dp0.."

echo.
echo   Sozlash
echo   ------------------------------------------------------------

if exist "forge\.env" (
  echo   [!] forge\.env allaqachon bor - o'zgartirilmaydi
  goto blender
)
if not exist "forge\.env.example" (
  echo   [xato] forge\.env.example topilmadi
  exit /b 1
)
copy /y "forge\.env.example" "forge\.env" >nul
echo   [ok] forge\.env yaratildi
echo.
echo   >>> forge\.env faylini ochib GEMINI_API_KEY= qatoriga
echo   >>> kalitni yozing:  https://aistudio.google.com/apikey
echo.

:blender
echo   Blender izlanmoqda...
set "BL="
for /f "tokens=*" %%p in ('dir /b /o-n "%ProgramFiles%\Blender Foundation\Blender *\blender.exe" 2^>nul') do (
  if not defined BL set "BL=%ProgramFiles%\Blender Foundation\%%p"
)
if defined BL (
  echo   [ok]   %BL%
  echo   >>> forge\.env da FORGE_BLENDER ni shu yo'lga o'zgartiring
) else (
  echo   [--]   Blender topilmadi. Blender 4.x+ o'rnating:
  echo         https://www.blender.org/download/
  echo         keyin forge\.env da FORGE_BLENDER ni ko'rsating.
)

echo.
echo   O'rnatish tugadi.
echo.
echo   1) forge\start_servers.bat
echo   2) forge\forge.bat doctor        - hammasi OK bo'lishi kerak
echo   3) forge\forge.bat run "LS V8 engine" --detail high
echo.
pause
exit /b 0