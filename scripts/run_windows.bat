@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    py -3 -m venv .venv || goto :error
)

if not exist ".venv\Scripts\python.exe" (
    echo No se pudo crear el entorno virtual. Instala Python 3.10 o superior.
    goto :error
)

".venv\Scripts\python.exe" -c "import cv2, numpy, kociemba" 2>NUL
if errorlevel 1 (
    echo Instalando dependencias...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

echo Iniciando RubikVisionSolver con DirectShow...
".venv\Scripts\python.exe" -m src.main --backend dshow %*
if errorlevel 1 (
    echo DirectShow no funciono; reintentando con Media Foundation...
    ".venv\Scripts\python.exe" -m src.main --backend msmf %*
)
exit /b 0

:error
echo No se pudo iniciar la aplicacion.
exit /b 1
