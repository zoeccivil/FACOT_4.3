@echo off
echo ========================================
echo  Compilando FACOT con Tema Professional
echo ========================================

REM Limpiar
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.spec del /q *.spec

REM Compilar con tema FACOT Pro embebido
py -3. 12 -m PyInstaller --clean --onefile --windowed --name=FACOT ^
    --add-data "templates;templates" ^
    --add-data "utils;utils" ^
    --add-data "utils/themes/theme_facot-pro.json;themes" ^
    --add-data "data_access;data_access" ^
    --add-data "firebase;firebase" ^
    --collect-all PyQt6 ^
    --hidden-import=PyQt6.QtWebEngineWidgets ^
    --hidden-import=firebase_admin ^
    --hidden-import=google.cloud.firestore ^
    main.py

if exist dist\FACOT. exe (
    echo. 
    echo ========================================
    echo  Compilacion exitosa - FACOT Pro Theme
    echo ========================================
    echo. 
    echo Ejecutable:  dist\FACOT.exe
    echo. 
    set /p run="Ejecutar ahora? (S/N): "
    if /i "%run%"=="S" start "" dist\FACOT.exe
)

pause