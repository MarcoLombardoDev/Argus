@echo off
REM compile.bat — Argus
REM
REM Double-click launcher for python build.py on Windows: installs the
REM build-only dependency (PyInstaller) and runs the same build script used
REM from the command line, then keeps the console window open so a failure
REM is actually readable instead of vanishing when the window auto-closes.
REM
REM Assumes Argus's own runtime dependencies (requirements.txt) are already
REM installed — see README.md > Installation & Setup. This only adds what
REM building needs on top of a working install.

setlocal

set "VENV_PYTHON=.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
    set "PYTHON=%VENV_PYTHON%"
) else (
    echo [compile] No .venv found — using the system "python" on PATH.
    set "PYTHON=python"
)

echo [compile] Installing build dependencies (PyInstaller)...
"%PYTHON%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo [compile] Building Argus.exe — this can take several minutes...
"%PYTHON%" build.py
if errorlevel 1 goto :error

echo.
echo [compile] Done. See dist\Argus.exe
pause
exit /b 0

:error
echo.
echo [compile] Build failed — see the output above for the reason.
pause
exit /b 1
