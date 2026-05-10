# generar_alertas.py
import sqlite3
from datetime import datetime, timedelta
import random

db_path = 'database.db'

# Conectar a BD
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Obtener algunos dispositivos
cursor.execute("SELECT id, nombre_host FROM dispositivos LIMIT 10")
dispositivos = cursor.fetchall()

tipos_alerta = [
    "movilidad",
    "ip_cambiada",
    "zona_incorrecta",
    "sin_inventario"
]

mensajes = [
    "Dispositivo reportando IP fuera de su zona asignada",
    "Cambio de segmento de red detectado",
    "IP no corresponde a la zona registrada",
    "Equipo sin actualizar en más de 30 días"
]

# Generar 5 alertas
for i in range(5):
    if dispositivos:
        dispositivo = random.choice(dispositivos)
        fecha = datetime.now() - timedelta(days=random.randint(0, 10))
        
        cursor.execute("""
            INSERT INTO alertas 
            (dispositivo_id, tipo_alerta, mensaje, fecha, resuelta)
            VALUES (?, ?, ?, ?, 0)
        """, (
            dispositivo[0],
            random.choice(tipos_alerta),
            random.choice(mensajes),
            fecha.strftime('%Y-%m-%d %H:%M:%S')
        ))

conn.commit()
conn.close()
print("✅ 5 alertas de prueba generadas")