# datos_prueba.py
import sqlite3
import random
from datetime import datetime

# Configuración
db_path = 'database.db'
zonas = ["DP000", "DP030", "DP060", "DP070", "DP080", "DP090", "DP100", "DP130", "DP520", "DP530", "DP580"]
tipos = ["PC", "Laptop", "Switch", "Router", "Impresora", "Server"]
areas = ["TIC", "Administración", "Comercial", "Distribución", "Gerencia"]

def generar_mac():
    return ":".join([f"{random.randint(0,255):02X}" for _ in range(6)])

def generar_ip():
    return f"10.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}"

def generar_serie():
    return f"SN{random.randint(10000,99999)}"

def generar_activo():
    return f"ACT-{random.randint(1000,9999)}" if random.random() > 0.3 else ""  # 30% sin activo

def generar_dominio():
    return 1 if random.random() > 0.2 else 0  # 80% con dominio

# Conectar a BD
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Generar 50 dispositivos de prueba
for i in range(50):
    zona = random.choice(zonas)
    tipo = random.choice(tipos)
    
    datos = {
        'mac_address': generar_mac(),
        'ip_address': generar_ip(),
        'nombre_host': f"EQUIPO-{i+1:03d}",
        'numero_serie': generar_serie(),
        'modelo': f"Modelo {random.choice(['HP', 'Dell', 'Cisco', 'Lenovo'])}",
        'tipo': tipo,
        'numero_activo': generar_activo(),
        'cve_zona': zona,
        'coordenadas_gps': f"{random.uniform(19.0,21.0):.6f}, {-random.uniform(99.0,101.0):.6f}",
        'area_pertenencia': random.choice(areas),
        'dominio': generar_dominio(),
        'origen': random.choice(['OCS', 'MANUAL']),
        'fecha_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'fecha_ultimo_inventario': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    cursor.execute("""
        INSERT OR IGNORE INTO dispositivos 
        (mac_address, ip_address, nombre_host, numero_serie, modelo, tipo, 
         numero_activo, cve_zona, coordenadas_gps, area_pertenencia, dominio,
         origen, fecha_registro, fecha_ultimo_inventario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tuple(datos.values()))

conn.commit()
conn.close()
print("✅ 50 dispositivos de prueba insertados")