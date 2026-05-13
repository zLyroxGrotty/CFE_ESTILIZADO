"""
Modelos y funciones de base de datos para el sistema de inventario CFE TIC
"""
import sqlite3
from datetime import datetime
import pandas as pd
import config


def get_connection():
    """Retorna conexión a la base de datos SQLite"""
    return sqlite3.connect(config.DATABASE_PATH)


def init_database():
    """
    Inicializa la base de datos creando las tablas necesarias
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ZONAS (
                    cve_zona TEXT PRIMARY KEY,
                    nombre_zona TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS DISPOSITIVOS (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_address TEXT UNIQUE,
                    ip_address TEXT,
                    nombre_host TEXT,
                    numero_serie TEXT,
                    modelo TEXT,
                    tipo TEXT,
                    origen TEXT DEFAULT 'OCS',
                    numero_inventario TEXT,
                    numero_activo TEXT,
                    cve_zona TEXT,
                    coordenadas_gps TEXT,
                    area_pertenencia TEXT,
                    dominio BOOLEAN DEFAULT 0,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_ultimo_inventario TIMESTAMP,
                    FOREIGN KEY (cve_zona) REFERENCES ZONAS(cve_zona)
                )
            """)
            
            # Migración: agregar columna si ya existe la tabla sin ella
            try:
                cursor.execute("ALTER TABLE DISPOSITIVOS ADD COLUMN numero_inventario TEXT")
            except Exception:
                pass  # La columna ya existe
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ALERTAS (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dispositivo_id INTEGER,
                    tipo_alerta TEXT,
                    mensaje TEXT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resuelta BOOLEAN DEFAULT 0,
                    FOREIGN KEY (dispositivo_id) REFERENCES DISPOSITIVOS(id)
                )
            """)
            
            # Poblar zonas desde config.py (INSERT OR IGNORE para no duplicar)
            for cve_zona, nombre_zona in config.ZONAS_CFE.items():
                cursor.execute("""
                    INSERT OR IGNORE INTO ZONAS (cve_zona, nombre_zona)
                    VALUES (?, ?)
                """, (cve_zona, nombre_zona))
            
            conn.commit()
            print("Base de datos inicializada correctamente")
            return True
            
    except sqlite3.Error as e:
        print(f"Error al inicializar base de datos: {e}")
        return False


def importar_zonas_excel(archivo_excel):
    """
    Importa zonas desde archivo Excel. Si el archivo no existe o está vacío, se omite sin error.
    """
    try:
        import os
        if not os.path.exists(archivo_excel) or os.path.getsize(archivo_excel) == 0:
            print(f"Archivo de zonas '{archivo_excel}' vacío o no encontrado — se omite importación")
            return 0
        
        df = pd.read_excel(archivo_excel)
        if df.empty or 'CVE ZONA' not in df.columns:
            print("Archivo Excel sin datos de zonas válidos — se omite importación")
            return 0
        
        df_filtrado = df[df['CVE ZONA'].astype(str).str.startswith('DP')]
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            count = 0
            for _, row in df_filtrado.iterrows():
                cve_zona = str(row['CVE ZONA']).strip()
                nombre_zona = str(row.get('NOMBRE ZONA', row.get('NOMBRE', ''))).strip()
                
                cursor.execute("""
                    INSERT OR IGNORE INTO ZONAS (cve_zona, nombre_zona)
                    VALUES (?, ?)
                """, (cve_zona, nombre_zona))
                
                if cursor.rowcount > 0:
                    count += 1
            
            conn.commit()
            print(f"Zonas importadas: {count}")
            return count
            
    except Exception as e:
        print(f"Error al importar zonas: {e}")
        return 0


def guardar_dispositivo_manual(datos):
    """
    Guarda un dispositivo registrado manualmente
    
    Args:
        datos: Diccionario con campos del dispositivo
        
    Returns:
        int: ID del dispositivo creado, o None si falló
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO DISPOSITIVOS (
                    mac_address, ip_address, nombre_host, numero_serie,
                    modelo, tipo, origen, numero_inventario, numero_activo, cve_zona,
                    coordenadas_gps, area_pertenencia, dominio
                ) VALUES (?, ?, ?, ?, ?, ?, 'MANUAL', ?, ?, ?, ?, ?, ?)
            """, (
                datos.get('mac_address'),
                datos.get('ip_address'),
                datos.get('nombre_host'),
                datos.get('numero_serie'),
                datos.get('modelo'),
                datos.get('tipo'),
                datos.get('numero_inventario'),
                datos.get('numero_activo'),
                datos.get('cve_zona'),
                datos.get('coordenadas_gps'),
                datos.get('area_pertenencia'),
                datos.get('dominio', 0)
            ))
            
            conn.commit()
            dispositivo_id = cursor.lastrowid
            print(f"Dispositivo manual guardado con ID: {dispositivo_id}")
            return dispositivo_id
            
    except sqlite3.Error as e:
        print(f"Error al guardar dispositivo manual: {e}")
        return None


def actualizar_dispositivo_ocs(datos):
    """
    Actualiza o inserta un dispositivo desde OCS Inventory
    
    Args:
        datos: Diccionario con campos del dispositivo desde OCS
        
    Returns:
        int: ID del dispositivo (nuevo o actualizado)
    """
    try:
        mac_address = datos.get('mac_address')
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM DISPOSITIVOS WHERE mac_address = ?
            """, (mac_address,))
            
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE DISPOSITIVOS SET
                        ip_address = ?,
                        nombre_host = ?,
                        numero_serie = ?,
                        modelo = ?,
                        tipo = ?,
                        numero_activo = ?,
                        cve_zona = ?,
                        coordenadas_gps = ?,
                        area_pertenencia = ?,
                        dominio = ?,
                        fecha_ultimo_inventario = ?
                    WHERE mac_address = ?
                """, (
                    datos.get('ip_address'),
                    datos.get('nombre_host'),
                    datos.get('numero_serie'),
                    datos.get('modelo'),
                    datos.get('tipo'),
                    datos.get('numero_activo'),
                    datos.get('cve_zona'),
                    datos.get('coordenadas_gps'),
                    datos.get('area_pertenencia'),
                    datos.get('dominio', 0),
                    datos.get('fecha_ultimo_inventario'),
                    mac_address
                ))
                
                conn.commit()
                print(f"Dispositivo OCS actualizado: {mac_address}")
                return existing[0]
            else:
                cursor.execute("""
                    INSERT INTO DISPOSITIVOS (
                        mac_address, ip_address, nombre_host, numero_serie,
                        modelo, tipo, origen, numero_activo, cve_zona,
                        coordenadas_gps, area_pertenencia, dominio,
                        fecha_ultimo_inventario
                    ) VALUES (?, ?, ?, ?, ?, ?, 'OCS', ?, ?, ?, ?, ?, ?)
                """, (
                    datos.get('mac_address'),
                    datos.get('ip_address'),
                    datos.get('nombre_host'),
                    datos.get('numero_serie'),
                    datos.get('modelo'),
                    datos.get('tipo'),
                    datos.get('numero_activo'),
                    datos.get('cve_zona'),
                    datos.get('coordenadas_gps'),
                    datos.get('area_pertenencia'),
                    datos.get('dominio', 0),
                    datetime.now()
                ))
                
                conn.commit()
                dispositivo_id = cursor.lastrowid
                print(f"Dispositivo OCS insertado: {mac_address}")
                return dispositivo_id
                
    except sqlite3.Error as e:
        print(f"Error al actualizar dispositivo OCS: {e}")
        return None


def crear_alerta(dispositivo_id, tipo_alerta, mensaje):
    """
    Crea una alerta para un dispositivo
    
    Args:
        dispositivo_id: ID del dispositivo
        tipo_alerta: Tipo de alerta (movilidad, inventario, etc.)
        mensaje: Descripción de la alerta
        
    Returns:
        int: ID de la alerta creada, o None si falló
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO ALERTAS (dispositivo_id, tipo_alerta, mensaje)
                VALUES (?, ?, ?)
            """, (dispositivo_id, tipo_alerta, mensaje))
            
            conn.commit()
            alerta_id = cursor.lastrowid
            print(f"Alerta creada: {tipo_alerta} para dispositivo {dispositivo_id}")
            return alerta_id
            
    except sqlite3.Error as e:
        print(f"Error al crear alerta: {e}")
        return None


def obtener_dispositivos_por_zona(cve_zona=None):
    """
    Obtiene dispositivos filtrados por zona
    
    Args:
        cve_zona: Clave de zona (opcional)
        
    Returns:
        list: Lista de dispositivos
    """
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if cve_zona:
                cursor.execute("""
                    SELECT * FROM DISPOSITIVOS WHERE cve_zona = ?
                """, (cve_zona,))
            else:
                cursor.execute("SELECT * FROM DISPOSITIVOS")
            
            return [dict(row) for row in cursor.fetchall()]
            
    except sqlite3.Error as e:
        print(f"Error al obtener dispositivos: {e}")
        return []


def obtener_alertas(resueltas=False):
    """
    Obtiene alertas del sistema
    
    Args:
        resueltas: Si True, incluye alertas resueltas
        
    Returns:
        list: Lista de alertas
    """
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if resueltas:
                cursor.execute("""
                    SELECT a.*, d.nombre_host, d.ip_address
                    FROM ALERTAS a
                    LEFT JOIN DISPOSITIVOS d ON a.dispositivo_id = d.id
                    ORDER BY a.fecha DESC
                """)
            else:
                cursor.execute("""
                    SELECT a.*, d.nombre_host, d.ip_address
                    FROM ALERTAS a
                    LEFT JOIN DISPOSITIVOS d ON a.dispositivo_id = d.id
                    WHERE a.resuelta = 0
                    ORDER BY a.fecha DESC
                """)
            
            return [dict(row) for row in cursor.fetchall()]
            
    except sqlite3.Error as e:
        print(f"Error al obtener alertas: {e}")
        return []


def resolver_alerta(alerta_id):
    """
    Marca una alerta como resuelta
    
    Args:
        alerta_id: ID de la alerta
        
    Returns:
        bool: True si éxito
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE ALERTAS SET resuelta = 1 WHERE id = ?
            """, (alerta_id,))
            
            conn.commit()
            return cursor.rowcount > 0
            
    except sqlite3.Error as e:
        print(f"Error al resolver alerta: {e}")
        return False


def obtener_dispositivo_por_id(dispositivo_id):
    """
    Obtiene un dispositivo por su ID
    
    Args:
        dispositivo_id: ID del dispositivo
        
    Returns:
        dict: Datos del dispositivo o None
    """
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT d.*, z.nombre_zona 
                FROM DISPOSITIVOS d
                LEFT JOIN ZONAS z ON d.cve_zona = z.cve_zona
                WHERE d.id = ?
            """, (dispositivo_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
            
    except sqlite3.Error as e:
        print(f"Error al obtener dispositivo: {e}")
        return None


def actualizar_dispositivo(dispositivo_id, datos):
    """
    Actualiza un dispositivo existente
    
    Args:
        dispositivo_id: ID del dispositivo
        datos: Diccionario con campos a actualizar
        
    Returns:
        bool: True si éxito
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE DISPOSITIVOS SET
                    mac_address = ?,
                    ip_address = ?,
                    nombre_host = ?,
                    numero_serie = ?,
                    modelo = ?,
                    tipo = ?,
                    numero_inventario = ?,
                    numero_activo = ?,
                    cve_zona = ?,
                    coordenadas_gps = ?,
                    area_pertenencia = ?,
                    dominio = ?
                WHERE id = ?
            """, (
                datos.get('mac_address'),
                datos.get('ip_address'),
                datos.get('nombre_host'),
                datos.get('numero_serie'),
                datos.get('modelo'),
                datos.get('tipo'),
                datos.get('numero_inventario'),
                datos.get('numero_activo'),
                datos.get('cve_zona'),
                datos.get('coordenadas_gps'),
                datos.get('area_pertenencia'),
                datos.get('dominio', 0),
                dispositivo_id
            ))
            
            conn.commit()
            return cursor.rowcount > 0
            
    except sqlite3.Error as e:
        print(f"Error al actualizar dispositivo: {e}")
        return False


def eliminar_dispositivo(dispositivo_id):
    """
    Elimina un dispositivo de la base de datos
    
    Args:
        dispositivo_id: ID del dispositivo a eliminar
        
    Returns:
        bool: True si éxito
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM ALERTAS WHERE dispositivo_id = ?", (dispositivo_id,))
            
            cursor.execute("DELETE FROM DISPOSITIVOS WHERE id = ?", (dispositivo_id,))
            
            conn.commit()
            return cursor.rowcount > 0
            
    except sqlite3.Error as e:
        print(f"Error al eliminar dispositivo: {e}")
        return False


if __name__ == "__main__":
    init_database()
