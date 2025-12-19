# 📦 Compilación de FACOT a Ejecutable

## 🚀 Compilación Rápida

### Windows

1. Asegúrate de tener **Python 3.12** instalado
2. Ejecuta el script de compilación:
   ```cmd
   compilar_facot.bat
   ```
3. Espera 3-5 minutos
4. Ejecuta `dist\FACOT.exe`

### Linux/Mac

```bash
python3.12 -m PyInstaller FACOT.spec
```

## 📋 Requisitos Previos

- **Python 3.12** ([Descargar](https://www.python.org/downloads/))
- **PyInstaller** (se instala automáticamente)
- **Todas las dependencias** del proyecto instaladas

## 🔧 Opciones Avanzadas

### Compilar con archivo .spec

```cmd
py -3.12 -m PyInstaller FACOT.spec
```

### Compilar con consola (para debug)

Edita `compilar_facot.bat` y cambia:
```batch
--windowed ^
```
Por:
```batch
--console ^
```

### Reducir tamaño del ejecutable

El script usa `upx=True` para comprimir. Para desactivar:

En `FACOT.spec`, cambia:
```python
upx=True,
```
Por:
```python
upx=False,
```

## 📁 Estructura de Salida

```
FACOT_4.3/
├── dist/
│   └── FACOT.exe          ← Ejecutable final
├── build/                 ← Archivos temporales
├── compilar_facot.bat     ← Script de compilación
└── FACOT.spec             ← Configuración PyInstaller
```

## 🐛 Solución de Problemas

### Error: "Python 3.12 no encontrado"

Instala Python 3.12 desde [python.org](https://www.python.org/downloads/)

### Error: "PyInstaller failed"

```cmd
py -3.12 -m pip install --upgrade pyinstaller
```

### Error: "Module not found"

Verifica que `utils/theme_manager.py` exista.

### Ejecutable muy grande (>300MB)

Esto es normal para aplicaciones PyQt6. Incluye:
- Python runtime
- PyQt6 completo
- Firebase SDK
- Todas las dependencias

## ✅ Verificación

Después de compilar, verifica:

1. ✅ El archivo `dist/FACOT.exe` existe
2. ✅ Tamaño aproximado: 150-250 MB
3. ✅ Al ejecutar, muestra la ventana principal
4. ✅ El tema FACOT Professional está aplicado
5. ✅ El selector de empresas funciona correctamente

## 📞 Soporte

Si tienes problemas, revisa los logs en la consola durante la compilación.
