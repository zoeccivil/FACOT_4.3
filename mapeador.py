import os

def generar_mapa_proyecto(ruta_inicio, ignorar_carpetas=None, ignorar_archivos=None):
    """
    Genera un árbol de directorios y archivos para el proyecto.
    """
    if ignorar_carpetas is None:
        # Carpetas comunes que no necesitamos mapear
        ignorar_carpetas = {'__pycache__', '.git', '.vscode', 'venv', 'env'}
    
    if ignorar_archivos is None:
        # Archivos que no necesitamos mapear (incluyendo este mismo script)
        ignorar_archivos = {'.gitignore', 'mapeador.py'}

    print(f"--- Mapa del Proyecto en: {os.path.abspath(ruta_inicio)} ---")
    print("\n(Copia y pega todo desde esta línea hacia abajo)\n")
    print(f"{os.path.basename(os.path.abspath(ruta_inicio))}/")

    for raiz, carpetas, archivos in os.walk(ruta_inicio, topdown=True):
        # Filtramos las carpetas que queremos ignorar
        carpetas[:] = [c for c in carpetas if c not in ignorar_carpetas]
        
        nivel = raiz.replace(ruta_inicio, '').count(os.sep)
        indentacion = ' ' * 4 * (nivel)
        
        # Imprimir carpetas
        if nivel > 0: # Evitar imprimir la raíz dos veces
            print(f"{indentacion}├── {os.path.basename(raiz)}/")

        # Indentación para los archivos dentro de esta carpeta
        sub_indentacion = ' ' * 4 * (nivel + 1)
        
        # Imprimir archivos
        for f in archivos:
            if f not in ignorar_archivos:
                print(f"{sub_indentacion}├── {f}")

    print("\n--- Fin del Mapa ---")

if __name__ == "__main__":
    # Ejecutamos el mapa desde el directorio actual ('.')
    directorio_actual = '.'
    generar_mapa_proyecto(directorio_actual)