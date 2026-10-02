@echo off
REM ============================================================
REM  01) Python muhiti  -  ComfyUI venv (CUDA torch)
REM
REM  ComfyUI uchun alohida venv yaratadi va torch+torchvision
REM  ni CUDA 12.8 bilan o'rnatadi. Forge esa Image-To-3D
REM  venv'ini ishlatadi (03-bosqichda o'rnatiladi).
REM ============================================================
setlocal
cd /d "%~dp0.."
set WS=%CD%

echo.
echo   [1/3] ComfyUI manba kodi
if not exist "ComfyUI\main.py" (
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git ComfyUI
) else (
  echo   [ok] ComfyUI allaqachon bor
)

echo.
echo   [2/3] ComfyUI-GGUF custom node (GGUF unet yuklash uchun)
if not exist "ComfyUI\custom_nodes\ComfyUI-GGUF" (
  git clone --depth 1 https://github.com/city96/ComfyUI-GGUF.git ComfyUI\custom_nodes\ComfyUI-GGUF
) else (
  echo   [ok] ComfyUI-GGUF allaqachon bor
)

echo.
echo   [3/3] Python venv + torch (CUDA 12.8) - bu biroz vaqt oladi
if exist "ComfyUI\venv\Scripts\python.exe" (
  echo   [ok] venv allaqachon bor - o'tkaziladi
  goto FIN
)

where py >nul 2>nul
if %ERRORLEVEL%==0 ( set PY=py -3.12 ) else ( set PY=python )

pushd ComfyUI
%PY% -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
python -m pip install -r custom_nodes\ComfyUI-GGUF\requirements.txt
python -c "import torch;print('TORCH',torch.__version__,'CUDA',torch.cuda.is_available(),torch.version.cuda)"
popd

:FIN
echo.
echo   Tayyor. Keyingi:  setup\02_download_models.bat
echo.
endlocal
exit /b 0