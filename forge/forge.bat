@echo off
REM ============================================================
REM  FORGE launcher — kerakli Python'ni avtomatik topadi
REM  Ishlatish:  forge\forge.bat doctor
REM              forge\forge.bat run "LS V8 engine"
REM ============================================================
setlocal
set ROOT=%~dp0
set WS=%ROOT%..

REM 1) Image-To-3D o'rnatilgan venv (trimesh/scipy/numpy/pillow bor)
if exist "%WS%\Image-To-3D\.venv\Scripts\python.exe" (
  "%WS%\Image-To-3D\.venv\Scripts\python.exe" "%ROOT%forge.py" %*
  exit /b %ERRORLEVEL%
)

REM 2) Sistem Python
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%ROOT%forge.py" %*
  exit /b %ERRORLEVEL%
)

REM 3) py launcher
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%ROOT%forge.py" %*
  exit /b %ERRORLEVEL%
)

echo [XATO] Python topilmadi. Image-To-3D\setup.bat ni ishga tushiring.
exit /b 1
