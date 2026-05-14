"""
Sincronizador para conectar con API de OCS Inventory
"""
import requests
import sqlite3
from datetime import datetime
from config import (
    OCS_API_URL, OCS_API_USER, OCS_API_PASS, OCS_TIMEOUT,
    ZONAS_CFE, RANGOS_IP_POR_ZONA
)
from models import (
    get_connection, actualizar_dispositivo_ocs, crear_alerta
)


def obtener_dispositivos_ocs():
    """
    Obtiene dispositivos desde la API de OCS Inventory
    
    Returns:
        list: Lista de dispositivos de OCS
    """
    try:
        auth = (OCS_API_USER, OCS_API_PASS)
        response = requests.get(
            f"{OCS_API_URL}/computers",
            auth=auth,
            timeout=OCS_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('computers', [])
        else:
            print(f"Error API OCS: {response.status_code}")
            return []
            
    except requests.exceptions.Timeout:
        print("Timeout conectando a OCS API")
        return []
    except requests.exceptions.ConnectionError:
        print("Error de conexión a OCS API")
        return []
    except Exception as e:
        print(f"Error al obtener dispositivos OCS: {e}")
        return []


def sincronizar_bd_local():
    """
    Sincroniza la base de datos local con datos de OCS
    
    Returns:
        int: Número de dispositivos sincronizados
    """
    print("Iniciando sincronización con OCS Inventory...")
    
    dispositivos_ocs = obtener_dispositivos_ocs()
    
    if not dispositivos_ocs:
        print("No se recibieron dispositivos de OCS")
        return 0
    
    count = 0
    for device in dispositivos_ocs:
        try:
            mac_address = device.get('MAC', '').strip().upper()
            if not mac_address:
                continue
            
            ip_address = device.get('IP', '')
            nombre_host = device.get('NAME', '')
            numero_serie = device.get('SERIALNUMBER', '')
            modelo = device.get('MODEL', '')
            
            tipo = map_tipo_ocs(device.get('TYPE', ''))
            
            datos = {
                'mac_address': mac_address,
                'ip_address': ip_address,
                'nombre_host': nombre_host,
                'numero_serie': numero_serie,
                'modelo': modelo,
                'tipo': tipo,
                'numero_activo': device.get('ACTIVEFIXNUM', ''),
                'cve_zona': inferir_zona(ip_address),
                'coordenadas_gps': device.get('GPS', ''),
                'area_pertenencia': device.get('DEPARTMENT', ''),
                'dominio': 1 if device.get('DOMAIN', '').lower() == 'cfe.mx' else 0
            }
            
            actualizar_dispositivo_ocs(datos)
            count += 1
            
        except Exception as e:
            print(f"Error al procesar dispositivo: {e}")
            continue
    
    print(f"Sincronización completada: {count} dispositivos")
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
    print(f"API URL: {OCS_API_URL}")
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
