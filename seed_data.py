"""
Genera datos de prueba realistas para la Panadería Los Andes.

- 30 días de ventas INCLUYENDO hoy.
- Descuenta stock al generar cada venta (respeta CHECK >= 0).
- Acepta parámetros `dias` y `limpiar` para ser invocado desde
  inicializar_entorno.py.
- No borra productos si ya existen (idempotente).
- Devuelve un resumen del estado final.
"""
import sqlite3
import random
import sys
from datetime import date, timedelta

DB_PATH = "panaderia.db"


# ============================================================
# 1. PRODUCTOS BASE (mismos que init_db.py)
# ============================================================
PRODUCTOS = [
    ("Pan francés",        0.50, 0.25, 120, 40),
    ("Pan integral",       0.75, 0.40,  25, 20),
    ("Torta de chocolate", 3.50, 1.80,   4, 10),
    ("Empanada",           1.50, 0.80,  18, 15),
    ("Alfajor",            2.00, 1.00,  35, 20),
    ("Pan de yema",        0.80, 0.45,  60, 25),
    ("Croissant",          2.50, 1.20,   8, 15),
    ("Bizcocho",           1.20, 0.60,  45, 20),
    ("Pan de molde",       4.00, 2.00,  12, 10),
    ("Galleta surtida",    1.00, 0.50,  80, 30),
]

POPULARIDAD = {
    "Pan francés":        0.30,
    "Pan integral":       0.10,
    "Torta de chocolate": 0.05,
    "Empanada":           0.08,
    "Alfajor":            0.07,
    "Pan de yema":        0.15,
    "Croissant":          0.05,
    "Bizcocho":           0.08,
    "Pan de molde":       0.04,
    "Galleta surtida":    0.08,
}

HORARIOS = [
    ("07:00", 0.10), ("08:00", 0.15), ("09:00", 0.10),
    ("10:00", 0.07), ("11:00", 0.06), ("12:00", 0.08),
    ("13:00", 0.07), ("14:00", 0.05), ("15:00", 0.05),
    ("16:00", 0.07), ("17:00", 0.08), ("18:00", 0.07),
    ("19:00", 0.05),
]

MOTIVOS_ENTRADA = ["Reposición de proveedor", "Compra diaria", "Producción propia"]
MOTIVOS_AJUSTE = ["Merma por vencimiento", "Producto dañado", "Ajuste por conteo"]


# ============================================================
# 2. UTILIDADES
# ============================================================
def _conn():
    return sqlite3.connect(DB_PATH)


def _tablas_existen():
    """Verifica si las tablas existen."""
    try:
        with _conn() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('productos','ventas','movimientos')"
            )
            return len(cur.fetchall()) == 3
    except Exception:
        return False


def limpiar_tablas(borrar_productos=False):
    """
    Borra datos previos.
    Por defecto NO borra productos (para no chocar con init_db.py).
    """
    with _conn() as conn:
        conn.execute("DELETE FROM ventas")
        conn.execute("DELETE FROM movimientos")
        conn.execute("DELETE FROM reportes_ia")
        conn.execute("DELETE FROM notificaciones")
        if borrar_productos:
            conn.execute("DELETE FROM productos")
        conn.commit()
    print(f"🧹 Tablas limpiadas (productos {'borrados' if borrar_productos else 'intactos'})")


def insertar_productos():
    """Inserta productos si no existen. Idempotente."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM productos")
        existentes = cur.fetchone()[0]

        if existentes >= len(PRODUCTOS):
            print(f"✅ Ya hay {existentes} productos, no se insertan")
            return existentes

        conn.executemany("""
            INSERT OR IGNORE INTO productos
                (nombre, precio, costo, stock_actual, stock_minimo)
            VALUES (?, ?, ?, ?, ?)
        """, PRODUCTOS)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM productos")
        total = cur.fetchone()[0]
        print(f"✅ {total} productos en la BD")
        return total


# ============================================================
# 3. HELPERS DE ALEATORIEDAD
# ============================================================
def _peso_horario():
    horarios = [h for h, _ in HORARIOS]
    pesos = [p for _, p in HORARIOS]
    return random.choices(horarios, weights=pesos, k=1)[0]


def _producto_aleatorio():
    productos = list(POPULARIDAD.keys())
    pesos = list(POPULARIDAD.values())
    return random.choices(productos, weights=pesos, k=1)[0]


def _factor_dia(fecha):
    """Fines de semana venden más. Lunes menos."""
    dia = fecha.weekday()
    if dia in (5, 6):
        return random.uniform(1.3, 1.6)
    if dia == 0:
        return random.uniform(0.7, 0.9)
    return random.uniform(0.9, 1.2)


def _cantidad_para_producto(nombre):
    if nombre == "Pan francés":
        return random.randint(5, 20)
    if nombre in ("Alfajor", "Bizcocho", "Galleta surtida"):
        return random.randint(1, 6)
    if nombre in ("Torta de chocolate", "Pan de molde", "Croissant"):
        return random.randint(1, 3)
    return random.randint(1, 8)


# ============================================================
# 4. VENTAS (incluye HOY, descuenta stock)
# ============================================================
def generar_ventas(dias=30):
    """
    Genera ventas realistas para los últimos `dias` días INCLUYENDO hoy.
    Descuenta stock respetando el CHECK constraint >= 0.
    """
    hoy = date.today()

    with _conn() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()

        # Cargar productos con stock
        cur.execute("SELECT id, nombre, precio, stock_actual FROM productos")
        prods = {
            row[1]: {"id": row[0], "precio": row[2], "stock": row[3]}
            for row in cur.fetchall()
        }

        if not prods:
            print("❌ No hay productos. Ejecuta init_db.py primero.")
            return 0

        total_ventas = 0
        total_ingresos = 0.0

        # range(dias-1, -1, -1) incluye hoy y da exactamente `dias` días
        for i in range(dias - 1, -1, -1):
            fecha = hoy - timedelta(days=i)
            factor = _factor_dia(fecha)

            # Menos ventas si es hoy (día no terminado)
            if i == 0:
                num_ventas = random.randint(8, 18)
            else:
                num_ventas = int(random.uniform(20, 40) * factor)

            for _ in range(num_ventas):
                nombre_prod = _producto_aleatorio()
                info = prods[nombre_prod]

                # Si no hay stock, buscar otro producto
                if info["stock"] <= 0:
                    disponibles = [n for n, p in prods.items() if p["stock"] > 0]
                    if not disponibles:
                        break
                    nombre_prod = random.choice(disponibles)
                    info = prods[nombre_prod]

                cantidad_deseada = _cantidad_para_producto(nombre_prod)
                cantidad = min(cantidad_deseada, info["stock"])

                if cantidad <= 0:
                    continue

                total = round(cantidad * info["precio"], 2)
                hora = _peso_horario()

                cur.execute("""
                    INSERT INTO ventas (fecha, hora, producto_id, cantidad, total, usuario)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fecha.isoformat(), hora, info["id"], cantidad, total,
                      random.choice(["admin", "vendedor1", "vendedor2"])))

                # Descontar stock (respeta CHECK >= 0)
                cur.execute("""
                    UPDATE productos SET stock_actual = stock_actual - ?
                    WHERE id = ?
                """, (cantidad, info["id"]))

                info["stock"] -= cantidad
                total_ventas += 1
                total_ingresos += total

        conn.commit()

    print(f"✅ {total_ventas} ventas generadas ({dias} días, incluye hoy)")
    print(f"💰 Ingresos totales: S/ {total_ingresos:,.2f}")
    return total_ventas


# ============================================================
# 5. MOVIMIENTOS DE INVENTARIO
# ============================================================
def generar_movimientos(dias=30):
    """Registra entradas y ajustes de inventario."""
    hoy = date.today()

    with _conn() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        cur.execute("SELECT id FROM productos")
        prods = cur.fetchall()

        if not prods:
            return 0

        total = 0
        for i in range(dias - 1, -1, -1):
            fecha = hoy - timedelta(days=i)

            for _ in range(random.randint(1, 2)):
                prod_id = random.choice(prods)[0]
                cantidad = random.randint(20, 60)
                cur.execute("""
                    INSERT INTO movimientos (fecha, producto_id, tipo, cantidad, motivo)
                    VALUES (?, ?, 'ENTRADA', ?, ?)
                """, (fecha.isoformat(), prod_id, cantidad,
                      random.choice(MOTIVOS_ENTRADA)))
                total += 1

            if random.random() < 0.3:
                prod_id = random.choice(prods)[0]
                cantidad = random.randint(1, 5)
                cur.execute("""
                    INSERT INTO movimientos (fecha, producto_id, tipo, cantidad, motivo)
                    VALUES (?, ?, 'AJUSTE', ?, ?)
                """, (fecha.isoformat(), prod_id, cantidad,
                      random.choice(MOTIVOS_AJUSTE)))
                total += 1

        conn.commit()

    print(f"✅ {total} movimientos de inventario generados")
    return total


# ============================================================
# 6. FORZAR STOCK CRÍTICO
# ============================================================
def forzar_stock_critico():
    """Reduce el stock de algunos productos para activar alertas."""
    criticos = {
        "Pan integral":       18,
        "Torta de chocolate":  3,
        "Croissant":           6,
        "Pan de molde":        8,
    }
    hoy = date.today().isoformat()

    with _conn() as conn:
        cur = conn.cursor()
        for nombre, stock_nuevo in criticos.items():
            cur.execute(
                "SELECT id, stock_actual FROM productos WHERE nombre = ?",
                (nombre,)
            )
            row = cur.fetchone()
            if not row:
                continue
            prod_id, stock_viejo = row

            cur.execute(
                "UPDATE productos SET stock_actual = ? WHERE id = ?",
                (stock_nuevo, prod_id)
            )

            # Registrar ajuste para trazabilidad
            if stock_nuevo < stock_viejo:
                cur.execute("""
                    INSERT INTO movimientos (fecha, producto_id, tipo, cantidad, motivo)
                    VALUES (?, ?, 'AJUSTE', ?, ?)
                """, (hoy, prod_id, stock_viejo - stock_nuevo,
                      "Ajuste de prueba para activar alertas"))

        conn.commit()

    print(f"⚠️  {len(criticos)} productos en estado crítico")


# ============================================================
# 7. PIPELINE PRINCIPAL
# ============================================================
def poblar_todo(dias=30, limpiar=True, borrar_productos=False):
    """
    Ejecuta el pipeline de población.

    Args:
        dias: número de días a generar.
        limpiar: si True, borra ventas/movimientos/reportes previos.
        borrar_productos: si True, también borra productos (no recomendado).
    """
    print("=" * 60)
    print("🌱 POBLANDO DATOS DE PRUEBA - PANADERÍA LOS ANDES")
    print("=" * 60)

    # 1. Asegurar tablas
    if not _tablas_existen():
        print("⚠️  Faltan tablas. Ejecutando init_db.py...")
        from init_db import inicializar_db
        inicializar_db()

    # 2. Limpiar (opcional)
    if limpiar:
        limpiar_tablas(borrar_productos=borrar_productos)

    # 3. Asegurar productos
    insertar_productos()

    # 4. Generar ventas
    generar_ventas(dias=dias)

    # 5. Generar movimientos
    generar_movimientos(dias=dias)

    # 6. Forzar stock crítico
    forzar_stock_critico()

    # 7. Resumen
    resumen = _resumen_final()
    print("=" * 60)
    print("✅ DATOS DE PRUEBA LISTOS")
    print("=" * 60)
    print(resumen)
    print("=" * 60)

    return resumen


def _resumen_final():
    """Devuelve un resumen textual del estado de la BD."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM productos")
        n_prod = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM ventas")
        n_ventas = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM ventas WHERE fecha = ?",
            (date.today().isoformat(),)
        )
        n_hoy = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM movimientos")
        n_mov = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM productos WHERE stock_actual <= stock_minimo"
        )
        n_criticos = cur.fetchone()[0]

    return (
        f"   🥖 Productos          : {n_prod}\n"
        f"   🛒 Ventas totales      : {n_ventas}\n"
        f"   📅 Ventas de HOY       : {n_hoy}\n"
        f"   📦 Movimientos         : {n_mov}\n"
        f"   ⚠️  Productos críticos  : {n_criticos}"
    )


# ============================================================
# 8. CLI
# ============================================================
if __name__ == "__main__":
    dias = 30
    limpiar = True
    borrar_productos = False

    if "--dias" in sys.argv:
        idx = sys.argv.index("--dias")
        try:
            dias = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("⚠️  Uso: --dias <número>")
            sys.exit(1)

    if "--sin-limpiar" in sys.argv:
        limpiar = False

    if "--borrar-productos" in sys.argv:
        borrar_productos = True

    poblar_todo(dias=dias, limpiar=limpiar, borrar_productos=borrar_productos)