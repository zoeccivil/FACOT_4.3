"""
Analizador de Ejecutables PyInstaller
Extrae, descompila y analiza temas en ejecutables de FACOT
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from tkinter import Tk, filedialog, messagebox
import zipfile
import shutil

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text: ^60}{Colors.RESET}")
    print(f"{Colors. CYAN}{Colors.BOLD}{'='*60}{Colors. RESET}\n")

def print_step(step_num, text):
    print(f"{Colors.BLUE}[{step_num}]{Colors.RESET} {Colors.BOLD}{text}{Colors.RESET}")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors. RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors. RESET}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def select_exe_file():
    """Abre diálogo para seleccionar el EXE."""
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    file_path = filedialog.askopenfilename(
        title="Selecciona el ejecutable FACOT a analizar",
        filetypes=[("Ejecutables", "*.exe"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    
    if not file_path:
        print_error("No se seleccionó ningún archivo")
        sys.exit(1)
    
    return Path(file_path)

def check_dependencies():
    """Verifica e instala dependencias necesarias."""
    print_step(1, "Verificando dependencias...")
    
    dependencies = {
        'pyinstxtractor':  'pyinstxtractor-ng',
        'uncompyle6': 'uncompyle6'
    }
    
    for module, package in dependencies.items():
        try:
            __import__(module)
            print_success(f"{module} ya instalado")
        except ImportError: 
            print_warning(f"Instalando {package}...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '-q'])
                print_success(f"{package} instalado correctamente")
            except subprocess.CalledProcessError: 
                print_error(f"No se pudo instalar {package}")
                return False
    
    return True

def extract_exe(exe_path):
    """Extrae el contenido del EXE usando pyinstxtractor."""
    print_step(2, f"Extrayendo: {exe_path. name}")
    
    # Buscar la carpeta extraída (pyinstxtractor crea diferentes formatos)
    possible_dirs = [
        exe_path.parent / f"{exe_path.stem}_extracted",
        exe_path. parent / exe_path.stem,
        exe_path.with_suffix('.exe_extracted')
    ]
    
    try:
        # Ejecutar pyinstxtractor
        result = subprocess.run(
            [sys.executable, '-m', 'pyinstxtractor', str(exe_path)],
            capture_output=True,
            text=True,
            cwd=str(exe_path.parent)
        )
        
        print(f"{Colors.YELLOW}Output de extracción:{Colors.RESET}")
        print(result.stdout)
        if result.stderr:
            print(f"{Colors.YELLOW}Errores/Warnings:{Colors.RESET}")
            print(result.stderr)
        
        # Buscar la carpeta creada
        for possible_dir in possible_dirs: 
            if possible_dir.exists() and possible_dir.is_dir():
                print_success(f"Extraído en: {possible_dir}")
                return possible_dir
        
        # Si no se encuentra, buscar cualquier carpeta nueva
        print_warning("Buscando carpeta de extracción...")
        for item in exe_path.parent.iterdir():
            if item.is_dir() and exe_path.stem. lower() in item.name.lower() and 'extract' in item.name.lower():
                print_success(f"Encontrada carpeta: {item}")
                return item
        
        print_error("No se pudo encontrar la carpeta de extracción")
        return None
        
    except Exception as e:
        print_error(f"Error extrayendo: {e}")
        return None

def analyze_extracted_files(extracted_dir):
    """Analiza los archivos extraídos."""
    print_step(3, "Analizando archivos extraídos...")
    
    if not extracted_dir or not extracted_dir.exists():
        print_error(f"Carpeta de extracción no válida: {extracted_dir}")
        return None
    
    analysis = {
        'main_file': None,
        'theme_files': [],
        'config_files': [],
        'theme_manager': None,
        'decompiled_main':  None,
        'all_files': []
    }
    
    # Listar todos los archivos
    print(f"\n{Colors.YELLOW}Explorando:  {extracted_dir}{Colors.RESET}")
    
    # Buscar archivos importantes
    for root, dirs, files in os.walk(extracted_dir):
        root_path = Path(root)
        
        for file in files:
            file_path = root_path / file
            analysis['all_files'].append(file_path)
            
            # Main file
            if file == 'main.pyc':
                analysis['main_file'] = file_path
                print_success(f"Encontrado:  main.pyc en {file_path. parent}")
            
            # Theme files
            if 'theme' in file. lower() and file. endswith('.json'):
                analysis['theme_files'].append(file_path)
                print_success(f"Encontrado tema: {file} en {file_path.parent}")
            
            # Config files
            if 'config' in file.lower() and file.endswith('.json'):
                analysis['config_files'].append(file_path)
                print_success(f"Encontrado config: {file} en {file_path.parent}")
            
            # Theme manager
            if file == 'theme_manager.pyc':
                analysis['theme_manager'] = file_path
                print_success(f"Encontrado:  theme_manager.pyc en {file_path.parent}")
    
    print(f"\n{Colors. CYAN}Total de archivos encontrados: {len(analysis['all_files'])}{Colors.RESET}")
    
    return analysis

def decompile_pyc(pyc_file, output_file):
    """Descompila un archivo .pyc a .py."""
    try:
        # Asegurar que la carpeta de salida existe
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        result = subprocess.run(
            [sys.executable, '-m', 'uncompyle6', '-o', str(output_file), str(pyc_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True
        else:
            # Intentar escribir el output parcial
            if output_file.exists() and output_file.stat().st_size > 0:
                return True
            return False
            
    except subprocess.TimeoutExpired:
        print_warning(f"Timeout descompilando {pyc_file. name}")
        return False
    except Exception as e:
        print_warning(f"Error descompilando {pyc_file.name}:  {e}")
        return False

def decompile_important_files(analysis, extracted_dir):
    """Descompila archivos importantes."""
    print_step(4, "Descompilando archivos importantes...")
    
    if not analysis: 
        print_error("No hay análisis disponible")
        return None
    
    # Verificar que extracted_dir existe
    if not extracted_dir.exists():
        print_error(f"La carpeta {extracted_dir} no existe")
        return None
    
    decompiled_dir = extracted_dir / "decompiled"
    
    try:
        # Crear carpeta con permisos explícitos
        decompiled_dir.mkdir(parents=True, exist_ok=True)
        print_success(f"Carpeta de descompilación creada: {decompiled_dir}")
    except Exception as e:
        print_error(f"No se pudo crear carpeta de descompilación: {e}")
        # Intentar en otra ubicación
        decompiled_dir = Path. home() / "Desktop" / "FACOT_decompiled"
        print_warning(f"Intentando en: {decompiled_dir}")
        decompiled_dir.mkdir(parents=True, exist_ok=True)
    
    # Descompilar main. pyc
    if analysis.get('main_file') and analysis['main_file'].exists():
        output = decompiled_dir / "main.py"
        print(f"  Descompilando main.pyc...")
        if decompile_pyc(analysis['main_file'], output):
            analysis['decompiled_main'] = output
            print_success(f"  → {output}")
        else:
            print_warning(f"  No se pudo descompilar completamente main.pyc")
    else:
        print_warning("  main.pyc no encontrado")
    
    # Descompilar theme_manager.pyc
    if analysis.get('theme_manager') and analysis['theme_manager'].exists():
        output = decompiled_dir / "theme_manager.py"
        print(f"  Descompilando theme_manager.pyc...")
        if decompile_pyc(analysis['theme_manager'], output):
            print_success(f"  → {output}")
        else:
            print_warning(f"  No se pudo descompilar completamente theme_manager.pyc")
    else:
        print_warning("  theme_manager.pyc no encontrado")
    
    return decompiled_dir

def analyze_theme_usage(analysis):
    """Analiza cómo se usan los temas."""
    print_step(5, "Analizando uso de temas...")
    
    report = []
    
    # Analizar temas disponibles
    if analysis['theme_files']:
        report.append("\n📁 TEMAS ENCONTRADOS:")
        for theme_file in analysis['theme_files']: 
            try:
                with open(theme_file, 'r', encoding='utf-8') as f:
                    theme_data = json.load(f)
                    theme_id = theme_data.get('id', 'unknown')
                    theme_name = theme_data.get('name', 'Unknown')
                    report.append(f"  • {theme_file. name}")
                    report.append(f"    Ruta: {theme_file}")
                    report.append(f"    ID: {theme_id}")
                    report.append(f"    Nombre: {theme_name}")
                    
                    if 'palette' in theme_data:
                        palette = theme_data['palette']
                        report.append(f"    Background: {palette.get('background', 'N/A')}")
                        report.append(f"    Primary: {palette.get('primary', 'N/A')}")
                    report.append("")
            except Exception as e:
                report.append(f"  • {theme_file.name} (error leyendo:  {e})")
    else:
        report.append("\n⚠ NO SE ENCONTRARON ARCHIVOS DE TEMA")
    
    # Analizar configuración
    if analysis['config_files']:
        report.append("\n⚙️ ARCHIVOS DE CONFIGURACIÓN:")
        for config_file in analysis['config_files']:
            try: 
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    report.append(f"  • {config_file. name}")
                    report.append(f"    Ruta:  {config_file}")
                    if 'theme' in config_data:
                        report.append(f"    Tema configurado: {json.dumps(config_data['theme'], indent=6)}")
                    report.append("")
            except Exception as e:
                report.append(f"  • {config_file.name} (error: {e})")
    
    # Analizar main descompilado
    if analysis. get('decompiled_main') and analysis['decompiled_main'].exists():
        report.append("\n🔍 ANÁLISIS DE main.py:")
        try:
            with open(analysis['decompiled_main'], 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                # Buscar referencias a temas
                if 'theme_to_apply' in content:
                    report.append("  ✓ Variable 'theme_to_apply' encontrada")
                    
                    # Intentar extraer el valor por defecto
                    for line in content.split('\n'):
                        if 'theme_to_apply' in line and '=' in line and not line.strip().startswith('#'):
                            report.append(f"    → {line.strip()}")
                
                if 'get_theme_manager' in content:
                    report. append("  ✓ Usa 'get_theme_manager()'")
                
                if 'apply_theme' in content:
                    report.append("  ✓ Llama a 'apply_theme()'")
                
                if '_apply_safe_menu_styles' in content:
                    report.append("  ✓ Aplica estilos de menú")
                
                if '_get_theme_from_config' in content:
                    report.append("  ✓ Lee tema desde facot_config. json")
                
        except Exception as e:
            report.append(f"  ✗ Error analizando main.py: {e}")
    else:
        report.append("\n⚠ No se pudo descompilar main.py para análisis detallado")
    
    return "\n".join(report)

def save_report(report_text, extracted_dir):
    """Guarda el reporte de análisis."""
    report_file = extracted_dir / "ANALISIS_TEMAS.txt"
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print_success(f"Reporte guardado en:  {report_file}")
        return report_file
    except Exception as e:
        print_error(f"No se pudo guardar el reporte: {e}")
        # Intentar en Desktop
        desktop_report = Path.home() / "Desktop" / "ANALISIS_TEMAS_FACOT.txt"
        with open(desktop_report, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print_success(f"Reporte guardado en: {desktop_report}")
        return desktop_report

def main():
    print_header("ANALIZADOR DE EJECUTABLES FACOT")
    
    # Verificar dependencias
    if not check_dependencies():
        print_error("No se pudieron instalar las dependencias necesarias")
        input("\nPresiona Enter para salir...")
        sys.exit(1)
    
    # Seleccionar archivo
    exe_path = select_exe_file()
    print(f"\n{Colors.BOLD}Archivo seleccionado:{Colors.RESET} {exe_path}")
    print(f"{Colors.BOLD}Tamaño:{Colors.RESET} {exe_path.stat().st_size / (1024*1024):.2f} MB\n")
    
    # Extraer
    extracted_dir = extract_exe(exe_path)
    if not extracted_dir:
        print_error("Falló la extracción")
        input("\nPresiona Enter para salir...")
        sys.exit(1)
    
    # Analizar archivos
    analysis = analyze_extracted_files(extracted_dir)
    if not analysis:
        print_error("No se pudo analizar la extracción")
        input("\nPresiona Enter para salir...")
        sys.exit(1)
    
    # Descompilar archivos importantes
    decompiled_dir = decompile_important_files(analysis, extracted_dir)
    
    # Generar reporte
    report = analyze_theme_usage(analysis)
    print(report)
    
    # Guardar reporte
    report_file = save_report(report, extracted_dir)
    
    # Resumen final
    print_header("RESUMEN")
    print(f"{Colors.BOLD}Carpeta de extracción:{Colors.RESET} {extracted_dir}")
    if decompiled_dir:
        print(f"{Colors.BOLD}Archivos descompilados:{Colors. RESET} {decompiled_dir}")
    print(f"{Colors. BOLD}Reporte completo:{Colors.RESET} {report_file}")
    
    # Preguntar si abrir carpeta
    print(f"\n{Colors.YELLOW}¿Abrir carpeta de resultados?  (S/N):{Colors.RESET} ", end='')
    try:
        if input().strip().upper() == 'S':
            if sys.platform == 'win32': 
                os.startfile(extracted_dir)
            else:
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(extracted_dir)])
    except: 
        pass
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Análisis completado{Colors.RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.RED}Cancelado por el usuario{Colors.RESET}")
        sys.exit(0)
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        input("\nPresiona Enter para salir...")
        sys.exit(1)