"""
Sincronizador para conectar con MariaDB de OCS Inventory
"""
import sqlite3
from datetime import datetime
import pymysql
from config import (
    OCS_DB_HOST, OCS_DB_PORT, OCS_DB_NAME, OCS_DB_USER, OCS_DB_PASS,
    ZONAS_CFE, RANGOS_IP_POR_ZONA
)
from models import (
    get_connection, actualizar_dispositivo_ocs, crear_alerta
)


def obtener_dispositivos_ocs():
    """Obtiene dispositivos desde MariaDB de OCS Inventory (directo)"""
    try:
        conn = pymysql.connect(
            host=OCS_DB_HOST,
            port=OCS_DB_PORT,
            db=OCS_DB_NAME,
            user=OCS_DB_USER,
            passwd=OCS_DB_PASS,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    h.NAME        AS nombre_host,
                    h.LASTDATE    AS fecha_ultimo_inventario,
                    h.OSNAME      AS osname,
                    n.IPADDRESS   AS ip_address,
                    n.MACADDR     AS mac_address,
                    b.SSN         AS numero_serie,
                    b.SMODEL      AS modelo,
                    ai.TAG        AS dominio_tag
                FROM hardware h
                LEFT JOIN networks n ON n.HARDWARE_ID = h.ID
                    AND n.IPADDRESS != '0.0.0.0'
                    AND n.IPADDRESS NOT LIKE '169.254.%'
                    AND n.MACADDR NOT LIKE '00:00:00:%'
                LEFT JOIN bios b        ON b.HARDWARE_ID = h.ID
                LEFT JOIN accountinfo ai ON ai.HARDWARE_ID = h.ID
                WHERE h.DEVICEID != '_SYSTEMGROUP_'
                  AND n.MACADDR IS NOT NULL AND n.MACADDR != ''
                GROUP BY h.ID
            """)
            dispositivos = cursor.fetchall()
        conn.close()
        return dispositivos
    except pymysql.MySQLError as e:
        print(f"Error conectando a OCS MariaDB: {e}")
        return []


def sincronizar_bd_local():
    dispositivos_ocs = obtener_dispositivos_ocs()
    count = 0
    for device in dispositivos_ocs:
        mac = (device.get('mac_address') or '').strip().upper()
        if not mac:
            continue
        dominio_tag = device.get('dominio_tag') or ''
        fecha = device.get('fecha_ultimo_inventario')
        datos = {
            'mac_address':             mac,
            'ip_address':              device.get('ip_address'),
            'nombre_host':             device.get('nombre_host'),
            'numero_serie':            device.get('numero_serie'),
            'modelo':                  device.get('modelo'),
            'tipo':                    map_tipo_ocs(device.get('osname', '')),
            'numero_activo':           None,
            'cve_zona':                inferir_zona(device.get('ip_address', '')),
            'coordenadas_gps':         None,
            'area_pertenencia':        dominio_tag,
            'dominio':                 1 if 'cfe.mx' in dominio_tag.lower() else 0,
            'fecha_ultimo_inventario': fecha.isoformat() if hasattr(fecha, 'isoformat') else fecha,
        }
        actualizar_dispositivo_ocs(datos)
        count += 1
    return count


def map_tipo_ocs(tipo_ocs):
    """
    Mapea el tipo de dispositivo de OCS a los tipos del sistema
    
    Args:
        tipo_ocs: Tipo string de OCS Inventory
        
    Returns:
        str: Tipo mapeado
    """
    tipo_ocs = str(tipo_ocs).lower()
    
    if 'laptop' in tipo_ocs or 'notebook' in tipo_ocs:
        return 'Laptop'
    elif 'server' in tipo_ocs or 'servidor' in tipo_ocs:
        return 'Server'
    elif 'switch' in tipo_ocs:
        return 'Switch'
    elif 'router' in tipo_ocs:
        return 'Router'
    elif 'printer' in tipo_ocs or 'impresora' in tipo_ocs:
        return 'Impresora'
    elif 'modem' in tipo_ocs:
        return 'Módem'
    elif 'pc' in tipo_ocs or 'desktop' in tipo_ocs or 'computadora' in tipo_ocs:
        return 'PC'
    else:
        return 'Otro'


def inferir_zona(ip_address):
    """
    Infiere la zona CFE basándose en la IP
    
    Args:
        ip_address: Dirección IP del dispositivo
        
    Returns:
        str: Clave de zona (DP000-DP580) o empty string
    """
    if not ip_address:
        return ''
    
    if not RANGOS_IP_POR_ZONA:
        return ''
    
    try:
        ip_parts = ip_address.split('.')
        if len(ip_parts) != 4:
            return ''
        
        ip_num = int(ip_parts[0]) * 256 + int(ip_parts[1])
        
        for zona, rango in RANGOS_IP_POR_ZONA.items():
            ip_start, ip_end = rango
            if ip_start <= ip_num <= ip_end:
                return zona
                
    except Exception:
        pass
    
    return ''


def verificar_alertas():
    """
    Verifica y genera alertas por movilidad de equipos
    (cambios de IP entre zonas)
    
    Returns:
        int: Número de alertas generadas
    """
    print("Verificando alertas de movilidad...")
    
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, mac_address, ip_address, nombre_host, cve_zona
            FROM DISPOSITIVOS
            WHERE origen = 'OCS'
        """)
        
        dispositivos = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT dispositivo_id, ip_address, fecha
            FROM ALERTAS
            WHERE tipo_alerta = 'movilidad'
            ORDER BY fecha DESC
        """)
        
        alertas_previas = {row['dispositivo_id']: row['ip_address'] for row in cursor.fetchall()}
        
        conn.close()
        
        count = 0
        for dispositivo in dispositivos:
            dispositivo_id = dispositivo['id']
            ip_actual = dispositivo['ip_address']
            
            if not ip_actual:
                continue
            
            ip_anterior = alertas_previas.get(dispositivo_id)
            
            if ip_anterior and ip_anterior != ip_actual:
                mensaje = (f"Cambio de IP detectado: {ip_anterior} -> {ip_actual} "
                          f"en dispositivo {dispositivo['nombre_host']}")
                
                crear_alerta(dispositivo_id, 'movilidad', mensaje)
                count += 1
        
        print(f"Alertas de movilidad generadas: {count}")
        return count
        
    except Exception as e:
        print(f"Error al verificar alertas: {e}")
        return 0


def verificar_inventario_vencido():
    """
    Verifica dispositivos que no han reportado inventario en más de 30 días
    
    Returns:
        int: Número de alertas generadas
    """
    print("Verificando inventario vencido...")
    
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, nombre_host, fecha_ultimo_inventario
            FROM DISPOSITIVOS
            WHERE origen = 'OCS'
            AND fecha_ultimo_inventario IS NOT NULL
            AND datetime(fecha_ultimo_inventario) < datetime('now', '-30 days')
        """)
        
        dispositivos_vencidos = [dict(row) for row in cursor.fetchall()]
        
        count = 0
        for dispositivo in dispositivos_vencidos:
            dispositivo_id = dispositivo['id']
            mensaje = (f"Dispositivo sin inventario hace más de 30 días: "
                      f"{dispositivo['nombre_host']}")
            
            crear_alerta(dispositivo_id, 'inventario_vencido', mensaje)
            count += 1
        
        conn.close()
        print(f"Alertas de inventario vencido: {count}")
        return count
        
    except Exception as e:
        print(f"Error al verificar inventario vencido: {e}")
        return 0


def main():
    """
    Ejecuta el flujo completo de sincronización
    """
    print("=" * 50)
    print("INICIO DE SINCRONIZACIÓN OCS INVENTORY")
    print("=" * 50)
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"MariaDB: {OCS_DB_HOST}:{OCS_DB_PORT}/{OCS_DB_NAME}")
    print("-" * 50)
    
    sincronizados = sincronizar_bd_local()
    print(f"Dispositivos sincronizados: {sincronizados}")
    
    alertas_movilidad = verificar_alertas()
    alertas_inventario = verificar_inventario_vencido()
    
    print("-" * 50)
    print(f"Total alertas generadas: {alertas_movilidad + alertas_inventario}")
    print("=" * 50)
    print("SINCRONIZACIÓN COMPLETADA")
    print("=" * 50)


if __name__ == '__main__':
    main()
