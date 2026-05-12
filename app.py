"""
Aplicación principal del sistema de inventario CFE TIC
"""
from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime
from config import (
    TEMPLATES_DIR, STATIC_DIR, SECRET_KEY, ZONAS_CFE, ZONAS_LIST,
    DEPARTAMENTOS_CFE, TIPOS_DISPOSITIVO, HOST, PORT, DEBUG
)
from models import (
    init_database, importar_zonas_excel, guardar_dispositivo_manual,
    obtener_alertas, resolver_alerta, get_connection,
    obtener_dispositivo_por_id, actualizar_dispositivo, eliminar_dispositivo
)

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)
app.config['SECRET_KEY'] = SECRET_KEY

init_database()

importar_zonas_excel('areas.xlsx')


@app.route('/')
def index():
    """Redirige al dashboard"""
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    """Vista principal del dashboard con estadísticas"""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM DISPOSITIVOS")
        total_dispositivos = cursor.fetchone()['total']
        
        # Conteo por origen (OCS vs MANUAL)
        cursor.execute("""
            SELECT origen, COUNT(*) as count
            FROM DISPOSITIVOS
            GROUP BY origen
        """)
        origen_rows = cursor.fetchall()
        count_by_origen = {row['origen']: row['count'] for row in origen_rows}
        total_ocs    = count_by_origen.get('OCS', 0)
        total_manual = count_by_origen.get('MANUAL', 0)
        
        cursor.execute("""
            SELECT tipo, COUNT(*) as count 
            FROM DISPOSITIVOS 
            GROUP BY tipo
        """)
        count_by_tipo = {row['tipo']: row['count'] for row in cursor.fetchall()}
        
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN numero_activo IS NOT NULL AND numero_activo != '' THEN 1 ELSE 0 END) as con_activo,
                SUM(CASE WHEN numero_activo IS NULL OR numero_activo = '' THEN 1 ELSE 0 END) as sin_activo
            FROM DISPOSITIVOS
        """)
        activo_data = cursor.fetchone()
        con_activo = activo_data['con_activo'] or 0
        sin_activo = activo_data['sin_activo'] or 0
        
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN dominio = 1 THEN 1 ELSE 0 END) as en_dominio,
                SUM(CASE WHEN dominio = 0 THEN 1 ELSE 0 END) as fuera_dominio
            FROM DISPOSITIVOS
        """)
        dominio_data = cursor.fetchone()
        en_dominio = dominio_data['en_dominio'] or 0
        fuera_dominio = dominio_data['fuera_dominio'] or 0
        
        cursor.execute("""
            SELECT d.cve_zona, z.nombre_zona, COUNT(d.id) as count
            FROM DISPOSITIVOS d
            LEFT JOIN ZONAS z ON d.cve_zona = z.cve_zona
            GROUP BY d.cve_zona
            ORDER BY count DESC
        """)
        dispositivos_por_zona = [dict(row) for row in cursor.fetchall()]
        
        # Dispositivos sin zona asignada
        cursor.execute("""
            SELECT COUNT(*) as total FROM DISPOSITIVOS
            WHERE cve_zona IS NULL OR cve_zona = ''
        """)
        sin_zona = cursor.fetchone()['total']
        
        alertas = obtener_alertas(resueltas=False)
        
        conn.close()
        
        return render_template(
            'dashboard.html',
            total_dispositivos=total_dispositivos,
            total_ocs=total_ocs,
            total_manual=total_manual,
            sin_zona=sin_zona,
            count_by_tipo=count_by_tipo,
            con_activo=con_activo,
            sin_activo=sin_activo,
            en_dominio=en_dominio,
            fuera_dominio=fuera_dominio,
            dispositivos_por_zona=dispositivos_por_zona,
            alertas=alertas,
            zonas=ZONAS_CFE
        )
        
    except Exception as e:
        app.logger.error(f"Error en dashboard: {e}")
        return render_template('dashboard.html', error=str(e))


@app.route('/registro-manual', methods=['GET', 'POST'])
def registro_manual():
    """Formulario para registro manual de dispositivos"""
    def build_zonas_options():
        options = [('', 'Seleccionar zona...')]
        for clave in ZONAS_LIST:
            nombre = ZONAS_CFE.get(clave, clave)
            options.append((clave, f"{clave} - {nombre}"))
        return options
    
    if request.method == 'GET':
        return render_template(
            'registro_manual.html',
            zonas=build_zonas_options(),
            departamentos=DEPARTAMENTOS_CFE,
            tipos=TIPOS_DISPOSITIVO
        )
    
    try:
        datos = {
            'mac_address': request.form.get('mac_address', '').strip().upper(),
            'ip_address': request.form.get('ip_address', '').strip(),
            'nombre_host': request.form.get('nombre_host', '').strip(),
            'numero_serie': request.form.get('numero_serie', '').strip(),
            'modelo': request.form.get('modelo', '').strip(),
            'tipo': request.form.get('tipo', ''),
            'numero_inventario': request.form.get('numero_inventario', '').strip(),
            'numero_activo': request.form.get('numero_activo', '').strip(),
            'cve_zona': request.form.get('cve_zona', ''),
            'coordenadas_gps': request.form.get('coordenadas_gps', '').strip(),
            'area_pertenencia': request.form.get('area_pertenencia', '').strip(),
            'dominio': 1 if request.form.get('dominio') else 0
        }
        
        if not datos['mac_address']:
            return render_template(
                'registro_manual.html',
                error="La dirección MAC es obligatoria",
                zonas=build_zonas_options(),
                departamentos=DEPARTAMENTOS_CFE,
                tipos=TIPOS_DISPOSITIVO
            ), 400
        
        dispositivo_id = guardar_dispositivo_manual(datos)
        
        if dispositivo_id:
            return redirect(url_for('dashboard'))
        else:
            return render_template(
                'registro_manual.html',
                error="Error al guardar el dispositivo",
                zonas=build_zonas_options(),
                departamentos=DEPARTAMENTOS_CFE,
                tipos=TIPOS_DISPOSITIVO
            ), 500
            
    except Exception as e:
        app.logger.error(f"Error en registro manual: {e}")
        return render_template(
            'registro_manual.html',
            error=str(e),
            zonas=build_zonas_options(),
            departamentos=DEPARTAMENTOS_CFE,
            tipos=TIPOS_DISPOSITIVO
        ), 500


@app.route('/dispositivos')
def dispositivos():
    """Lista todos los dispositivos con filtros y paginación"""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        tipo_filter    = request.args.get('tipo', '')
        zona_filter    = request.args.get('zona', '')
        origen_filter  = request.args.get('origen', '')
        activo_filter  = request.args.get('activo', '')
        dominio_filter = request.args.get('dominio', '')
        sin_zona_filter = request.args.get('sin_zona', '')
        search = request.args.get('busqueda', '')
        page = int(request.args.get('page', 1))
        per_page = 10
        
        query = "SELECT d.*, z.nombre_zona FROM DISPOSITIVOS d LEFT JOIN ZONAS z ON d.cve_zona = z.cve_zona WHERE 1=1"
        params = []
        
        if tipo_filter:
            query += " AND d.tipo = ?"
            params.append(tipo_filter)
        
        if zona_filter:
            query += " AND d.cve_zona = ?"
            params.append(zona_filter)
        
        if origen_filter:
            query += " AND d.origen = ?"
            params.append(origen_filter)
        
        if activo_filter == 'con':
            query += " AND d.numero_activo IS NOT NULL AND d.numero_activo != ''"
        elif activo_filter == 'sin':
            query += " AND (d.numero_activo IS NULL OR d.numero_activo = '')"
        
        if dominio_filter == '1':
            query += " AND d.dominio = 1"
        elif dominio_filter == '0':
            query += " AND d.dominio = 0"
        
        if sin_zona_filter == '1':
            query += " AND (d.cve_zona IS NULL OR d.cve_zona = '')"
        
        if search:
            query += " AND (d.nombre_host LIKE ? OR d.ip_address LIKE ? OR d.mac_address LIKE ? OR d.numero_activo LIKE ? OR d.numero_inventario LIKE ?)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search_param, search_param])
        
        cursor.execute(f"SELECT COUNT(*) as total FROM ({query})", params)
        total = cursor.fetchone()['total']
        
        query += " ORDER BY d.fecha_registro DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])
        
        cursor.execute(query, params)
        dispositivos = [dict(row) for row in cursor.fetchall()]
        
        for d in dispositivos:
            if d.get('fecha_registro'):
                d['fecha_registro'] = datetime.strptime(d['fecha_registro'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M')
            if d.get('fecha_ultimo_inventario'):
                d['fecha_ultimo_inventario'] = datetime.strptime(d['fecha_ultimo_inventario'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M')
        
        conn.close()
        
        total_pages = (total + per_page - 1) // per_page
        
        return render_template(
            'dispositivos.html',
            dispositivos=dispositivos,
            zonas=ZONAS_CFE,
            tipos=TIPOS_DISPOSITIVO,
            tipo_filter=tipo_filter,
            zona_filter=zona_filter,
            origen_filter=origen_filter,
            activo_filter=activo_filter,
            dominio_filter=dominio_filter,
            sin_zona_filter=sin_zona_filter,
            search=search,
            page=page,
            total_pages=total_pages
        )
        
    except Exception as e:
        app.logger.error(f"Error en dispositivos: {e}")
        return render_template('dispositivos.html', error=str(e))


@app.route('/api/dispositivos')
def api_dispositivos():
    """API JSON para obtener dispositivos filtrados"""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        tipo = request.args.get('tipo')
        zona = request.args.get('zona')
        
        query = "SELECT * FROM DISPOSITIVOS WHERE 1=1"
        params = []
        
        if tipo:
            query += " AND tipo = ?"
            params.append(tipo)
        
        if zona:
            query += " AND cve_zona = ?"
            params.append(zona)
        
        query += " ORDER BY fecha_registro DESC LIMIT 100"
        
        cursor.execute(query, params)
        dispositivos = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': dispositivos,
            'count': len(dispositivos)
        })
        
    except Exception as e:
        app.logger.error(f"Error en API dispositivos: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/sincronizar', methods=['POST'])
def sincronizar():
    """Dispara sincronización manual con OCS Inventory"""
    try:
        from sincronizador import sincronizar_bd_local, verificar_alertas, verificar_inventario_vencido
        sincronizados = sincronizar_bd_local()
        alertas_mov = verificar_alertas()
        alertas_inv = verificar_inventario_vencido()
        return jsonify({
            'success': True,
            'sincronizados': sincronizados,
            'alertas_generadas': alertas_mov + alertas_inv,
            'mensaje': f'{sincronizados} dispositivos sincronizados, {alertas_mov + alertas_inv} alertas generadas'
        })
    except Exception as e:
        app.logger.error(f"Error en sincronización: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/alertas/resolver/<int:alerta_id>')
def resolver_alerta_route(alerta_id):
    """Marca una alerta como resuelta"""
    try:
        success = resolver_alerta(alerta_id)
        if success:
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('dashboard'))
    except Exception as e:
        app.logger.error(f"Error al resolver alerta: {e}")
        return redirect(url_for('dashboard'))


@app.route('/dispositivos/editar/<int:dispositivo_id>', methods=['GET', 'POST'])
def editar_dispositivo(dispositivo_id):
    """Editar un dispositivo existente"""
    dispositivo = obtener_dispositivo_por_id(dispositivo_id)
    
    if not dispositivo:
        return redirect(url_for('dispositivos'))
    
    if request.method == 'GET':
        zonas_options = [('', 'Seleccionar zona...')]
        for clave in ZONAS_LIST:
            nombre = ZONAS_CFE.get(clave, clave)
            zonas_options.append((clave, f"{clave} - {nombre}"))
        
        return render_template(
            'editar_dispositivo.html',
            dispositivo=dispositivo,
            zonas=zonas_options,
            tipos=TIPOS_DISPOSITIVO
        )
    
    try:
        datos = {
            'mac_address': request.form.get('mac_address', '').strip().upper(),
            'ip_address': request.form.get('ip_address', '').strip(),
            'nombre_host': request.form.get('nombre_host', '').strip(),
            'numero_serie': request.form.get('numero_serie', '').strip(),
            'modelo': request.form.get('modelo', '').strip(),
            'tipo': request.form.get('tipo', ''),
            'numero_inventario': request.form.get('numero_inventario', '').strip(),
            'numero_activo': request.form.get('numero_activo', '').strip(),
            'cve_zona': request.form.get('cve_zona', ''),
            'coordenadas_gps': request.form.get('coordenadas_gps', '').strip(),
            'area_pertenencia': request.form.get('area_pertenencia', '').strip(),
            'dominio': 1 if request.form.get('dominio') else 0
        }
        
        success = actualizar_dispositivo(dispositivo_id, datos)
        
        if success:
            return redirect(url_for('dispositivos'))
        else:
            zonas_options = [('', 'Seleccionar zona...')]
            for clave in ZONAS_LIST:
                nombre = ZONAS_CFE.get(clave, clave)
                zonas_options.append((clave, f"{clave} - {nombre}"))
            return render_template(
                'editar_dispositivo.html',
                dispositivo=dispositivo,
                zonas=zonas_options,
                tipos=TIPOS_DISPOSITIVO,
                error="Error al actualizar el dispositivo"
            ), 500
            
    except Exception as e:
        app.logger.error(f"Error al editar dispositivo: {e}")
        return redirect(url_for('dispositivos'))


@app.route('/dispositivos/eliminar/<int:dispositivo_id>', methods=['POST'])
def eliminar_dispositivo_route(dispositivo_id):
    """Eliminar un dispositivo"""
    try:
        success = eliminar_dispositivo(dispositivo_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'No se pudo eliminar'}), 500
    except Exception as e:
        app.logger.error(f"Error al eliminar dispositivo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/dispositivos/detalle/<int:dispositivo_id>')
def detalle_dispositivo(dispositivo_id):
    """Ver detalle de un dispositivo"""
    dispositivo = obtener_dispositivo_por_id(dispositivo_id)
    
    if not dispositivo:
        return redirect(url_for('dispositivos'))
    
    return render_template(
        'detalle_dispositivo.html',
        dispositivo=dispositivo,
        zonas=ZONAS_CFE
    )


@app.errorhandler(404)
def not_found(error):
    """Manejo de error 404"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Manejo de error 500"""
    app.logger.error(f"Error interno: {error}")
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=DEBUG)
