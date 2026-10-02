@echo off
REM ============================================================
REM  FORGE serverlari: ComfyUI (rasm) + Image-To-3D (3D)
REM  Ikkalasi ham GPU'da hisoblaydi. Barcha kesh D: da (portable).
REM ============================================================
setlocal
set WS=%~dp0..
cd /d "%WS%"

REM --- PORTABLE: hech narsa C: ga yozilmasin ---
set "FORGE_CACHE_ROOT=%WS%\cache"
set "HF_HOME=%WS%\cache\hf"
set "HF_HUB_CACHE=%WS%\cache\hf\hub"
set "TORCH_HOME=%WS%\cache\torch"
if not exist "%HF_HUB_CACHE%" mkdir "%HF_HUB_CACHE%"
if not exist "%TORCH_HOME%" mkdir "%TORCH_HOME%"

echo.
echo   FORGE serverlari
echo   ------------------------------------------

call :up 8742 /api/jobs
if "%UP%"=="1" goto I23D_OK
if not exist "Image-To-3D\start_server.bat" goto I23D_MISS
echo   [..]   Image-To-3D ishga tushmoqda...
start "" /min cmd /c "cd /d %WS%\Image-To-3D && start_server.bat"
set T=0
:I23D_WAIT
call :up 8742 /api/jobs
if "%UP%"=="1" goto I23D_OK
set /a T+=1
if %T% GEQ 45 goto I23D_BAD
ping -n 2 127.0.0.1 >nul
goto I23D_WAIT
:I23D_BAD
echo   [xato] Image-To-3D ishga tushmadi - Image-To-3D\server.log ni ko'ring
goto COMFY
:I23D_MISS
echo   [xato] Image-To-3D\start_server.bat topilmadi
goto COMFY
:I23D_OK
echo   [ok]   Image-To-3D   http://127.0.0.1:8742

REM ---------------- ComfyUI ----------------
:COMFY
call :up 8188 /system_stats
if "%UP%"=="1" goto COMFY_OK
if not exist "ComfyUI\main.py" goto COMFY_MISS
echo   [..]   ComfyUI ishga tushmoqda (1-2 daqiqa)...
REM --highvram ishlatilmaydi: 12 GB GPU'da crash beradi (access violation).
REM Standart "smart memory" rejimi hisobni GPU'da olib boradi
REM (VRAM peak ~11.9/12.3 GB), faqat fayl keshi xotirada qoladi.
start "" /min cmd /c "cd /d %WS%\ComfyUI && venv\Scripts\python.exe main.py --port 8188 --listen 127.0.0.1 --reserve-vram 0.5 --disable-pinned-memory >> comfyui_start.log 2>&1"
set T=0
:COMFY_WAIT
call :up 8188 /system_stats
if "%UP%"=="1" goto COMFY_OK
set /a T+=1
if %T% GEQ 100 goto COMFY_BAD
ping -n 3 127.0.0.1 >nul
goto COMFY_WAIT
:COMFY_BAD
echo   [xato] ComfyUI ishga tushmadi - ComfyUI\comfyui_start.log ni ko'ring
goto END
:COMFY_MISS
echo   [--]   ComfyUI topilmadi (ixtiyoriy)
goto END
:COMFY_OK
echo   [ok]   ComfyUI       http://127.0.0.1:8188  (GPU hisob)

:END
echo   ------------------------------------------
echo   Kesh: %HF_HUB_CACHE%
echo   Tekshirish:  forge\forge.bat doctor
echo.
endlocal
exit /b 0

REM ---------------------------------------------------------------
REM  :up <port> <path>  ->  UP=1 yoki 0
:up
set "CODE="
for /f "tokens=*" %%i in ('curl.exe -s -m 3 -o nul -w "%%{http_code}" http://127.0.0.1:%~1%~2 2^>nul') do set "CODE=%%i"
if "%CODE%"=="200" (set "UP=1") else (set "UP=0")
exit /b 0
