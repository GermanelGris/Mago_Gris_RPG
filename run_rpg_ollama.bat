@echo off
REM ============================================================
REM   Nerea RPG - EDICION OLLAMA (portable, sin rutas fijas)
REM   Busca rpg_ollama.py junto a este .bat (o en .\games) y un
REM   Python usable (.venv local, ..\.venv, o el del sistema).
REM   Requiere Ollama corriendo:  ollama serve
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- localizar el archivo del juego ---
set "GAME="
if exist "%~dp0rpg_ollama.py" set "GAME=%~dp0rpg_ollama.py"
if not defined GAME if exist "%~dp0games\rpg_ollama.py" set "GAME=%~dp0games\rpg_ollama.py"
if not defined GAME (
    echo [ERROR] No se encontro rpg_ollama.py junto a este .bat ni en .\games
    pause
    exit /b 1
)

REM --- localizar Python (venv local, venv del proyecto, o del sistema) ---
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
if not defined PY for %%P in (python.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY for %%P in (py.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY (
    echo [ERROR] No se encontro Python ni un entorno .venv
    echo Instala Python o crea el venv:  python -m venv .venv ^&^& .venv\Scripts\pip install pygame
    pause
    exit /b 1
)

echo Iniciando Nerea RPG (edicion Ollama)...
echo  Python: %PY%
echo  Juego : %GAME%
"%PY%" "%GAME%"

echo.
echo El juego se cerro.
pause
