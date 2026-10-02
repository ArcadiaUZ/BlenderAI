@echo off
REM ============================================================
REM  03) Image-To-3D (TRELLIS.2) - rasm -> 3D GLB serveri
REM
REM  Bu alohida ochiq loyiha: github.com/ArcadiaUZ/Image-To-3D
REM  U o'z setup.ps1 orqali vositalar, kod, build va modellarni
REM  (~15 GB) o'rnatadi - shuning uchun bu skript faqat
REM  repo'ni klonlaydi va uning setup'ini chaqiradi.
REM
REM  PyTorch'siz: C++/ggml + Vulkan. CUDA toolkit ham,
REM  Vulkan SDK ham kerak emas.
REM ============================================================
setlocal
cd /d "%~dp0.."
set WS=%CD%

echo.
echo   Image-To-3D (TRELLIS.2)
echo   ------------------------------------------------------------

if not exist "Image-To-3D\setup.bat" (
  echo   [..]   klonlanmoqda...
  git clone --depth 1 https://github.com/ArcadiaUZ/Image-To-3D.git Image-To-3D
  if errorlevel 1 (
    echo   [xato] klonlash muvaffaqiyatsiz
    exit /b 1
  )
) else (
  echo   [ok]   allaqachon o'rnatilgan
)

echo.
echo   [..]   setup.bat ishga tushmoqda (modellarning yuklanishi uzoq turadi)...
echo         Birinchi marta Visual Studio Build Tools so'raydi.
echo         O'rnatilgan bo'lsa - terminalni QAYTA ochib, bu skriptni
echo         yana ishga tushiring.
echo.
pushd Image-To-3D
call setup.bat
set RC=%ERRORLEVEL%
popd

echo.
if "%RC%"=="2" (
  echo   [!] Visual Studio o'rnatildi. Terminalni qayta ochib,
  echo       setup\03_setup_image_to_3d.bat ni yana ishga tushiring.
  pause
  exit /b 0
)
if not "%RC%"=="0" (
  echo   [xato] Image-To-3D o'rnatilmadi. Image-To-3D\provision.log ni ko'ring.
  pause
  exit /b %RC%
)

echo   Keyingi:  setup\04_setup_env.bat
pause
exit /b 0