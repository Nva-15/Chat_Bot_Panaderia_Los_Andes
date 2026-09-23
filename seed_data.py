"""
Genera datos de prueba realistas para la Panadería Los Andes.
- 30 días de ventas con variación diaria
- Múltiples ventas por día en diferentes horarios
- Productos con stock crítico para activar alertas
- Estacionalidad semanal (fines de semana más ventas)
"""
import sqlite3
import random
from datetime import date, datetime, timedelta

DB_PATH = "panaderia.db"

# ============================================================
# 1. PRODUCTOS BASE
# ============================================================
PRODUCTOS = [
    # (nombre, precio, costo, stock_actual, stock_minimo)
    ("Pan francés",       0.50, 0.25, 120, 40),
    ("Pan integral",      0.75, 0.40,  25, 20),   # ⚠️ CRÍTICO
    ("Torta de chocolate",3.50, 1.80,   4, 10),   # 🔴 CRÍTICO
    ("Empanada",          1.50, 0.80,  18, 15),
    ("Alfajor",           2.00, 1.00,  35, 20),
    ("Pan de yema",       0.80, 0.45,  60, 25),
    ("Croissant",         2.50, 1.20,   8, 15),   # ⚠️ CRÍTICO
    ("Bizcocho",          1.20, 0.60,  45, 20),
    ("Pan de molde",      4.00, 2.00,  12, 10),
    ("Galleta surtida",   1.00, 0.50,  80, 30),
]

# ============================================================
# 2. PROBABILIDAD DE VENTA POR PRODUCTO (popularidad)
# ============================================================
POPULARIDAD = {
    "Pan francés":       0.30,   # 30% de las ventas
    "Pan integral":      0.10,
    "Torta de chocolate":0.05,
    "Empanada":          0.08,
    "Alfajor":           0.07,
    "Pan de yema":       0.15,
    "Croissant":         0.05,
    "Bizcocho":          0.08,
    "Pan de molde":      0.04,
    "Galleta surtida":   0.08,
}

# ============================================================
# 3. HORARIOS DE VENTA (mañana y tarde con picos)
# ============================================================
HORARIOS = [
    ("07:00", 0.10), ("08:00", 0.15), ("09:00", 0.10),  # mañana
    ("10:00", 0.07), ("11:00", 0.06), ("12:00", 0.08),  # mediodía
    ("13:00", 0.07), ("14:00", 0.05), ("15:00", 0.05),  # tarde
    ("16:00", 0.07), ("17:00", 0.08), ("18:00", 0.07),  # pico tarde
    ("19:00", 0.05),
]

# ============================================================
# 4. FUNCIONES AUXILIARES
# ============================================================
def _conn():
    return sqlite3.connect(DB_PATH)

def limpiar_tablas():
    """Borra los datos previos para evitar duplicados."""
    with _conn() as conn:
        conn.execute("DELETE FROM ventas")
        conn.execute("DELETE FROM movimientos")
        conn.execute("DELETE FROM reportes_ia")
        conn.execute("DELETE FROM notificaciones")
        conn.execute("DELETE FROM productos")
        conn.commit()
    print("🧹 Tablas limpiadas")

def insertar_productos():
    """Inserta los productos base con stock inicial."""
    with _conn() as conn:
        conn.executemany("""
            INSERT INTO productos (nombre, precio, costo, stock_actual, stock_minimo)
            VALUES (?, ?, ?, ?, ?)
        """, PRODUCTOS)
        conn.commit()
    print(f"✅ {len(PRODUCTOS)} productos insertados")

def _peso_horario():
    """Devuelve un horario según su probabilidad."""
    horarios = [h for h, _ in HORARIOS]
    pesos = [p for _, p in HORARIOS]
    return random.choices(horarios, weights=pesos, k=1)[0]

def _producto_aleatorio():
    """Devuelve un producto según su popularidad."""
    productos = list(POPULARIDAD.keys())
    pesos = list(POPULARIDAD.values())
    return random.choices(productos, weights=pesos, k=1)[0]

def _factor_dia(fecha):
    """Fines de semana venden más. Lunes menos."""
    dia = fecha.weekday()  # 0=lunes, 6=domingo
    if dia in (5, 6):     # sábado, domingo
        return random.uniform(1.3, 1.6)
    if dia == 0:          # lunes
        return random.uniform(0.7, 0.9)
    return random.uniform(0.9, 1.2)

# ============================================================
# 5. GENERAR VENTAS DE 30 DÍAS
# ============================================================
def generar_ventas(dias=30):
    """Genera ventas realistas para los últimos N días."""
    hoy = date.today()
    with _conn() as conn:
        cur = conn.cursor()

        # Obtener productos con su id y precio
        cur.execute("SELECT id, nombre, precio FROM productos")
        prods = {row[1]: {"id": row[0], "precio": row[2]} for row in cur.fetchall()}

        total_ventas = 0
        for i in range(dias, -1, -1):
            fecha = hoy - timedelta(days=i)
            factor = _factor_dia(fecha)

            # Base de ventas por día: 20-40 transacciones
            num_ventas = int(random.uniform(20, 40) * factor)

            for _ in range(num_ventas):
                nombre_prod = _producto_aleatorio()
                info = prods[nombre_prod]
                hora = _peso_horario()

                # Cantidad según producto
                if nombre_prod == "Pan francés":
                    cantidad = random.randint(5, 20)
                elif nombre_prod in ("Alfajor", "Bizcocho", "Galleta surtida"):
                    cantidad = random.randint(1, 6)
                elif nombre_prod in ("Torta de chocolate", "Pan de molde"):
                    cantidad = random.randint(1, 3)
                else:
                    cantidad = random.randint(1, 8)

                total = round(cantidad * info["precio"], 2)

                cur.execute("""
                    INSERT INTO ventas (fecha, hora, producto_id, cantidad, total, usuario)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fecha.isoformat(), hora, info["id"], cantidad, total,
                      random.choice(["admin", "vendedor1", "vendedor2"])))

                total_ventas += 1

        conn.commit()
    print(f"✅ {total_ventas} ventas generadas en {dias} días")

# ============================================================
# 6. GENERAR MOVIMIENTOS DE INVENTARIO
# ============================================================
def generar_movimientos(dias=30):
    """Registra entradas y ajustes de inventario."""
    hoy = date.today()
    motivos_entrada = ["Reposición de proveedor", "Compra diaria", "Producción propia"]
    motivos_ajuste = ["Merma por vencimiento", "Producto dañado", "Ajuste por conteo"]

    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM productos")
        prods = cur.fetchall()

        total = 0
        for i in range(dias, -1, -1):
            fecha = hoy - timedelta(days=i)

            # 1 o 2 entradas por día
            for _ in range(random.randint(1, 2)):
                prod_id, _ = random.choice(prods)
                cantidad = random.randint(20, 60)
                cur.execute("""
                    INSERT INTO movimientos (fecha, producto_id, tipo, cantidad, motivo)
                    VALUES (?, ?, 'ENTRADA', ?, ?)
                """, (fecha.isoformat(), prod_id, cantidad,
                      random.choice(motivos_entrada)))
                total += 1

            # Ajustes ocasionales
            if random.random() < 0.3:
                prod_id, _ = random.choice(prods)
                cantidad = random.randint(1, 5)
                cur.execute("""
                    INSERT INTO movimientos (fecha, producto_id, tipo, cantidad, motivo)
                    VALUES (?, ?, 'AJUSTE', ?, ?)
                """, (fecha.isoformat(), prod_id, cantidad,
                      random.choice(motivos_ajuste)))
                total += 1

        conn.commit()
    print(f"✅ {total} movimientos de inventario generados")

# ============================================================
# 7. FORZAR STOCK CRÍTICO
# ============================================================
def forzar_stock_critico():
    """Reduce el stock de algunos productos para que las alertas se disparen."""
    criticos = {
        "Pan integral": 18,        # mínimo 20
        "Torta de chocolate": 3,   # mínimo 10
        "Croissant": 6,            # mínimo 15
        "Pan de molde": 8,         # mínimo 10
    }
    with _conn() as conn:
        for nombre, stock in criticos.items():
            conn.execute(
                "UPDATE productos SET stock_actual = ? WHERE nombre = ?",
                (stock, nombre)
            )
        conn.commit()
    print(f"⚠️ {len(criticos)} productos en estado crítico")

# ============================================================
# 8. EJECUCIÓN PRINCIPAL
# ============================================================
def poblar_todo():
    """Ejecuta todo el pipeline de población de datos."""
    from init_db import inicializar_db

    print("=" * 60)
    print("🌱 POBLANDO DATOS DE PRUEBA - PANADERÍA LOS ANDES")
    print("=" * 60)

    inicializar_db()
    limpiar_tablas()
    insertar_productos()
    generar_ventas(dias=30)
    generar_movimientos(dias=30)
    forzar_stock_critico()

    print("=" * 60)
    print("✅ DATOS DE PRUEBA LISTOS")
    print("=" * 60)


if __name__ == "__main__":
    poblar_todo()