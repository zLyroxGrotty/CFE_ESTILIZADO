"""
Configuración del sistema de inventario CFE TIC
"""
import os
import sys
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')

TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Configuración OCS MariaDB (reemplaza OCS_API_URL, OCS_API_USER, etc.)
OCS_DB_HOST = "localhost"
OCS_DB_PORT = 3306
OCS_DB_NAME = "ocsweb"
OCS_DB_USER = "root"
OCS_DB_PASS = "tu_password"

ZONAS_CFE = {
    "DP000": "OFICINAS DIVISIONALES",
    "DP030": "ZONA SAN JUAN DEL RIO",
    "DP060": "ZONA IRAPUATO",
    "DP070": "ZONA LEON",
    "DP080": "ZONA IRAPUATO",
    "DP090": "ZONA QUERETARO",
    "DP100": "ZONA SALVATIERRA",
    "DP130": "ZONA IXMIQUILPAN",
    "DP520": "ZONA AGUASCALIENTES",
    "DP530": "ZONA FRESNILLO",
    "DP580": "ZONA ZACATECAS"
}

DEPARTAMENTOS_CFE = [
    "GERENCIA DIVISIONAL",
    "SUBGERENCIA DE TRABAJO Y SERVICIOS ADMISTRATIVOS",
    "SUBGERENCIA COMERCIAL",
    "SUBGERENCIA DISTRIBUCION",
    "ADMINISTRACION",
    "DISTRIBUCION",
    "COMERCIAL",
    "TIC",
    "SUPERINTENDENCIA"
]

ZONAS_LIST = [
    "DP000", "DP030", "DP060", "DP070", "DP080", "DP090",
    "DP100", "DP130", "DP520", "DP530", "DP580"
]

RANGOS_IP_POR_ZONA = {}

SECRET_KEY = secrets.token_hex(32)

DEBUG = True

PORT = 5000

HOST = "127.0.0.1"

TIPOS_DISPOSITIVO = [
    "PC",
    "Laptop",
    "Server",
    "Switch",
    "Router",
    "Impresora",
    "Impresora sin red",
    "Módem",
    "Otro"
]

DOMINIO_CFE = "cfe.mx"


def get_zonas_options():
    """
    Retorna lista de tuplas (clave, valor) para selects HTML
    Formato: [('', 'Seleccionar zona...'), ('DP000', 'DP000 - OFICINAS DIVISIONALES'), ...]
    """
    options = [('', 'Seleccionar zona...')]
    for clave in ZONAS_LIST:
        nombre = ZONAS_CFE.get(clave, clave)
        options.append((clave, f"{clave} - {nombre}"))
    return options


def validate_directories():
    """
    Valida que existan las carpetas necesarias del proyecto
    """
    required_dirs = [TEMPLATES_DIR, STATIC_DIR]
    missing_dirs = []
    
    for directory in required_dirs:
        if not os.path.isdir(directory):
            missing_dirs.append(directory)
    
    if missing_dirs:
        print(f"Advertencia: Las siguientes carpetas no existen: {missing_dirs}")
        for directory in missing_dirs:
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"Carpeta creada: {directory}")
            except Exception as e:
                print(f"Error al crear {directory}: {e}")
    
    return len(missing_dirs) == 0


if __name__ == "__main__":
    validate_directories()
    print(f"Base directory: {BASE_DIR}")
    print(f"Database path: {DATABASE_PATH}")
    print(f"Zonas disponibles: {len(ZONAS_LIST)}")
