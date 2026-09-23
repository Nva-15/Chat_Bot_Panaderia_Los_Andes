"""
Inicialización automática del entorno para Streamlit Cloud.
Se ejecuta UNA SOLA VEZ por sesión de servidor con @st.cache_resource.

No depende de inyectar_ventas_hoy.py: la lógica está integrada aquí.
"""
import os
import sqlite3
import random
import streamlit as st
from datetime import date

DB_PATH = "panaderia.db"

HORARIOS = [
    "07:15", "07:45", "08:30", "09:00", "09:45",
    "11:00", "11:30", "12:30", "13:00", "13:45",
    "15:00", "15:30", "16:30", "17:00", "17:45",
    "18:00", "18:30", "19:00"
]


# ============================================================
# VERIFICACIONES
# ============================================================
def _bd_existe():
    return os.path.exists(DB_PATH)


def _bd_tiene_datos():
    """Verifica que la BD tenga productos y ventas."""
    if not _bd_existe():
        return False
    try:
        with sqlite3.connect(DB_PATH) as conn:
            n_prod = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
            n_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
            return n_prod > 0 and n_ventas > 0
    except Exception:
        return False


def _hay_ventas_hoy():
    if not _bd_existe():
        return False
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM ventas WHERE fecha = ?",
                (date.today().isoformat(),)
            )
            return cur.fetchone()[0] > 0
    except Exception:
        return False


# ============================================================
# INYECCIÓN DE VENTAS DEL DÍA (lógica integrada)
# ============================================================
def _inyectar_ventas_hoy(min_ventas=15):
    """
    Genera ventas aleatorias para hoy.
    Valida stock antes de vender para no violar el CHECK constraint.
    Si no hay stock, repone automáticamente.
    """
    hoy = date.today().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()

        # ¿Cuántas ventas hay hoy?
        cur.execute("SELECT COUNT(*) FROM ventas WHERE fecha = ?", (hoy,))
        existentes = cur.fetchone()[0]

        if existentes >= min_ventas:
            print(f"[init] Ya hay {existentes} ventas hoy.")
            return 0

        faltan = min_ventas - existentes
        print(f"[init] Inyectando {faltan} ventas para hoy...")

        # Productos con stock
        cur.execute("""
            SELECT id, nombre, precio, stock_actual
            FROM productos WHERE stock_actual > 0
        """)
        productos = [list(r) for r in cur.fetchall()]

        # Si no hay stock, reponer
        if not productos:
            print("[init] ⚠️ Sin stock. Reponiendo productos críticos...")
            cur.execute("""
                UPDATE productos SET stock_actual = stock_minimo + 100
                WHERE stock_actual <= stock_minimo
            """)
            conn.commit()
            cur.execute("""
                SELECT id, nombre, precio, stock_actual
                FROM productos WHERE stock_actual > 0
            """)
            productos = [list(r) for r in cur.fetchall()]

        inyectadas = 0
        intentos = 0

        while inyectadas < faltan and intentos < faltan * 5:
            intentos += 1
            prod = random.choice(productos)
            prod_id, nombre, precio, stock = prod

            if stock <= 0:
                productos = [p for p in productos if p[0] != prod_id]
                if not productos:
                    break
                continue

            # Cantidad según producto
            if nombre == "Pan francés":
                cant = random.randint(3, 12)
            elif nombre in ("Alfajor", "Bizcocho", "Galleta surtida"):
                cant = random.randint(1, 5)
            else:
                cant = random.randint(1, 6)

            cant = min(cant, stock)
            if cant <= 0:
                continue

            total = round(cant * precio, 2)
            hora = random.choice(HORARIOS)

            cur.execute("""
                INSERT INTO ventas (fecha, hora, producto_id, cantidad, total, usuario)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (hoy, hora, prod_id, cant, total, "auto"))

            cur.execute("""
                UPDATE productos SET stock_actual = stock_actual - ?
                WHERE id = ?
            """, (cant, prod_id))

            prod[3] -= cant
            if prod[3] <= 0:
                productos = [p for p in productos if p[0] != prod_id]

            inyectadas += 1

        conn.commit()
        print(f"[init] ✅ {inyectadas} ventas inyectadas para {hoy}")
        return inyectadas


# ============================================================
# INICIALIZACIÓN PRINCIPAL
# ============================================================
@st.cache_resource(show_spinner="🚀 Inicializando sistema...")
def inicializar_entorno():
    """
    Punto de entrada. Se ejecuta una sola vez por sesión de servidor.
    Flujo:
      1. Si la BD no existe o está vacía → init_db + seed_data
      2. Si no hay ventas de hoy → inyectar
    """
    print("=" * 60)
    print("[init] Iniciando verificación del entorno...")
    print("=" * 60)

    # --- FASE 1: Crear y poblar la BD si es necesario ---
    if not _bd_tiene_datos():
        print("[init] BD vacía o inexistente. Creando esquema...")

        from init_db import inicializar_db
        inicializar_db()

        print("[init] Poblando 30 días de datos...")
        from seed_data import poblar_todo
        poblar_todo(dias=30, limpiar=False)

        print("[init] ✅ Base de datos creada y poblada")
    else:
        print("[init] ✅ BD ya tiene datos, no se repuebla")

    # --- FASE 2: Garantizar ventas de hoy ---
    if not _hay_ventas_hoy():
        print("[init] No hay ventas de hoy. Inyectando...")
        _inyectar_ventas_hoy(min_ventas=15)
    else:
        print("[init] ✅ Ya hay ventas de hoy")

    print("=" * 60)
    print("[init] 🎉 Entorno listo")
    print("=" * 60)

    return True