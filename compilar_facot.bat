@echo off
title FACOT - Compilador a Ejecutable
color 0B

echo ========================================
echo  FACOT Professional - Compilador
echo ========================================
echo.
echo Este script compilara FACOT a un ejecutable
echo de un solo archivo (.exe)
echo.
echo Tiempo estimado: 3-5 minutos
echo ========================================
echo.
pause

REM ==========================================
REM  PASO 1: Limpiar compilaciones anteriores
REM ==========================================
echo [1/6] Limpiando archivos de compilaciones anteriores...

if exist dist (
    echo       Eliminando carpeta dist...
    rmdir /s /q dist
)

if exist build (
    echo       Eliminando carpeta build...
    rmdir /s /q build
)

if exist *.spec (
    echo       Eliminando archivos .spec...
    del /q *.spec
)

echo       Limpieza completada
echo.

REM ==========================================
REM  PASO 2: Verificar Python 3.12
REM ==========================================
echo [2/6] Verificando Python 3.12...

py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ========================================
    echo  ERROR: Python 3.12 no encontrado
    echo ========================================
    echo.
    echo Por favor instala Python 3.12 desde:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('py -3.12 --version') do set PYTHON_VERSION=%%v
echo       %PYTHON_VERSION% detectado
echo.

REM ==========================================
REM  PASO 3: Verificar/Instalar PyInstaller
REM ==========================================
echo [3/6] Verificando PyInstaller...

py -3.12 -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo       PyInstaller no encontrado, instalando...
    py -3.12 -m pip install pyinstaller --quiet
    echo       PyInstaller instalado
) else (
    echo       PyInstaller ya instalado
    echo       Actualizando a la ultima version...
    py -3.12 -m pip install --upgrade pyinstaller --quiet
)
echo.

REM ==========================================
REM  PASO 4: Verificar archivos necesarios
REM ==========================================
echo [4/6] Verificando archivos del proyecto...

set MISSING_FILES=0

if not exist "main.py" (
    echo       ERROR: main.py no encontrado
    set MISSING_FILES=1
)

if not exist "utils\theme_manager.py" (
    echo       ERROR: utils\theme_manager.py no encontrado
    set MISSING_FILES=1
)

if not exist "templates" (
    echo       ADVERTENCIA: carpeta templates no encontrada
)

if %MISSING_FILES%==1 (
    echo.
    echo ========================================
    echo  ERROR: Archivos necesarios faltantes
    echo ========================================
    echo.
    pause
    exit /b 1
)

echo       Todos los archivos necesarios encontrados
echo.

REM ==========================================
REM  PASO 5: Compilar con PyInstaller
REM ==========================================
echo [5/6] Compilando FACOT a ejecutable...
echo.
echo       Esto puede tardar 3-5 minutos.
echo       Por favor espera...
echo.

py -3.12 -m PyInstaller ^
    --clean ^
    --onefile ^
    --windowed ^
    --name=FACOT ^
    --add-data "templates;templates" ^
    --add-data "utils;utils" ^
    --add-data "themes;themes" ^
    --add-data "data_access;data_access" ^
    --add-data "firebase;firebase" ^
    --add-data "tabs;tabs" ^
    --add-data "dialogs;dialogs" ^
    --add-data "widgets;widgets" ^
    --add-data "ui;ui" ^
    --collect-all PyQt6 ^
    --hidden-import=PyQt6.QtCore ^
    --hidden-import=PyQt6.QtGui ^
    --hidden-import=PyQt6.QtWidgets ^
    --hidden-import=PyQt6.QtWebEngineWidgets ^
    --hidden-import=PyQt6.QtWebEngineCore ^
    --hidden-import=firebase_admin ^
    --hidden-import=google.cloud.firestore ^
    --hidden-import=google.cloud.storage ^
    --hidden-import=utils.theme_manager ^
    main.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo  ERROR en la compilacion
    echo ========================================
    echo.
    echo Revisa los mensajes de error arriba
    echo.
    pause
    exit /b 1
)

echo.
echo       Compilacion completada exitosamente
echo.

REM ==========================================
REM  PASO 6: Verificar ejecutable
REM ==========================================
echo [6/6] Verificando ejecutable generado...

if not exist "dist\FACOT.exe" (
    echo.
    echo ========================================
    echo  ERROR: Ejecutable no generado
    echo ========================================
    echo.
    echo El archivo dist\FACOT.exe no se creo
    echo Revisa los errores de compilacion
    echo.
    pause
    exit /b 1
)

echo       Ejecutable creado: dist\FACOT.exe
echo.

REM Obtener tamaño del archivo
for %%A in (dist\FACOT.exe) do (
    set SIZE=%%~zA
    set /a SIZE_MB=%%~zA/1048576
)

echo       Tamano: %SIZE_MB% MB
echo.

REM ==========================================
REM  COMPILACION EXITOSA
REM ==========================================
echo ========================================
echo  COMPILACION EXITOSA
echo ========================================
echo.
echo Ejecutable:  dist\FACOT.exe
echo Tamano:      %SIZE_MB% MB
echo.
echo El ejecutable incluye:
echo   - Tema FACOT Professional
echo   - Todos los modulos de Python
echo   - Plantillas HTML
echo   - Configuraciones
echo.
echo ========================================
echo.

set /p RUN_EXE="Deseas ejecutar FACOT ahora? (S/N): "

if /i "%RUN_EXE%"=="S" (
    echo.
    echo Iniciando FACOT...
    echo.
    start "" "dist\FACOT.exe"
    echo.
    echo FACOT iniciado en una nueva ventana
    echo.
) else (
    echo.
    echo Puedes ejecutar FACOT manualmente desde:
    echo dist\FACOT.exe
    echo.
)

echo Presiona cualquier tecla para salir...
pause >nul