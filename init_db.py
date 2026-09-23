import sqlite3
import os

DB_PATH = "panaderia.db"

def inicializar_db():
    """Crea las tablas necesarias si no existen."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabla de productos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            precio REAL NOT NULL,
            costo REAL NOT NULL DEFAULT 0,
            stock_actual INTEGER NOT NULL DEFAULT 0,
            stock_minimo INTEGER NOT NULL DEFAULT 10
        )
    """)

    # Tabla de ventas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            producto_id INTEGER NOT NULL,
            cantidad INTEGER NOT NULL,
            total REAL NOT NULL,
            usuario TEXT,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)

    # Tabla de movimientos de inventario
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            producto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            motivo TEXT,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)

    # Tabla de reportes generados por IA
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reportes_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            fecha_generacion TEXT NOT NULL,
            contenido TEXT NOT NULL,
            leido INTEGER DEFAULT 0
        )
    """)

    # Tabla de notificaciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            prioridad TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            fecha TEXT NOT NULL,
            leida INTEGER DEFAULT 0
        )
    """)

    # Datos iniciales de productos
    productos = [
        ("Pan francés", 0.50, 0.25, 100, 30),
        ("Pan integral", 0.75, 0.40, 50, 20),
        ("Torta de chocolate", 3.50, 1.80, 10, 5),
        ("Empanada", 1.50, 0.80, 25, 10),
        ("Alfajor", 2.00, 1.00, 40, 15),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO productos (nombre, precio, costo, stock_actual, stock_minimo)
        VALUES (?, ?, ?, ?, ?)
    """, productos)

    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada")

if __name__ == "__main__":
    inicializar_db()