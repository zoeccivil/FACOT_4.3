@echo off
echo Creando configuracion de tema por defecto... 

REM Crear carpeta config
if not exist "config" mkdir config

REM Crear archivo de tema con tema "light"
echo {"theme": "light", "saved_theme": "light"} > config\theme.json

echo. 
echo Configuracion creada en: config\theme.json
echo Tema por defecto: light
echo. 
pause