@echo off
REM ============================================================
REM   Nerea RPG - INSTALADOR (portable, sin rutas fijas)
REM   Crea un entorno .venv junto a este .bat e instala pygame.
REM   Despues, juega con run_rpg.bat (o run_rpg_ollama.bat).
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- localizar Python del sistema ---
set "PY="
for %%P in (python.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY for %%P in (py.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY (
    echo [ERROR] No se encontro Python en el sistema.
    echo Descargalo de https://www.python.org/downloads/  ^(marca "Add to PATH"^)
    pause
    exit /b 1
)
echo Python encontrado: %PY%

REM --- crear el entorno virtual .venv si no existe ---
if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual .venv...
    "%PY%" -m venv ".venv"
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno .venv
        pause
        exit /b 1
    )
)

set "VPY=.venv\Scripts\python.exe"

REM --- 1) comprobar / actualizar pip ANTES de instalar nada ---
echo Comprobando version de pip...
"%VPY%" -m pip --version
echo Buscando actualizaciones de pip...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [AVISO] No se pudo actualizar pip; se intentara instalar igual.
)

REM --- 2) instalar pygame (las dependencias del juego) ---
echo Instalando pygame...
if exist "requirements_rpg.txt" (
    "%VPY%" -m pip install -r "requirements_rpg.txt"
) else (
    "%VPY%" -m pip install pygame
)
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Instalacion completa. Ya puedes jugar:
echo     - run_rpg.bat          ^(version Nerea^)
echo     - run_rpg_ollama.bat   ^(solo Ollama, requiere 'ollama serve'^)
echo ============================================================
pause
