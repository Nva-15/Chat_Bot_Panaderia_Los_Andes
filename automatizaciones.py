from datetime import date, datetime, timedelta
from chatbot import consultar_groq
from prompts import PROMPTS, NORMA_MONEDA
from database import (
    obtener_stock, obtener_ventas_dia, obtener_ventas_semana,
    obtener_top_productos, obtener_consumo_promedio,
    guardar_reporte, guardar_notificacion
)
import os
import sqlite3

REPORTES_DIR = "reportes"
LOGS_DIR = "logs"
DB_PATH = "panaderia.db"
os.makedirs(REPORTES_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)


def _log(mensaje):
    with open(f"{LOGS_DIR}/automatizaciones.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {mensaje}\n")


def _inicio_semana():
    return (date.today() - timedelta(days=date.today().weekday())).isoformat()


def _ya_procesado(tipo, desde_iso):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM reportes_ia WHERE tipo = ? AND fecha_generacion >= ?",
            (tipo, desde_iso)
        )
        return cur.fetchone()[0] > 0


def _guardar_archivo(nombre, contenido):
    ruta = f"{REPORTES_DIR}/{nombre}.md"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta


def _generar(prompt_key, **kwargs):
    config = PROMPTS[prompt_key]
    prompt_usuario = config["usuario"].format(**kwargs)
    return consultar_groq(
        messages=[
            {"role": "system", "content": f"{config['sistema']} {NORMA_MONEDA}"},
            {"role": "user", "content": prompt_usuario}
        ],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"]
    )

# AUTO=====MATIZACIÓN 1: REPORTE DIARIO DE VENTAS (programado 20:00)
def auto_reporte_diario():
    _log("▶️ Ejecutando auto_reporte_diario")
    hoy = date.today().isoformat()
    if _ya_procesado("diario", hoy):
        _log(f"⏭️ Corte {hoy} ya fue procesado, se omite (no se llama a Groq)")
        return None

    ventas = obtener_ventas_dia(hoy)
    if ventas.empty:
        _log("⚠️ Sin ventas hoy, se omite reporte")
        return None

    reporte = _generar(
        "P01_resumen_diario",
        fecha=hoy,
        datos=ventas.to_csv(index=False)
    )

    guardar_reporte("diario", reporte)
    archivo = _guardar_archivo(f"diario_{hoy}", reporte)
    _log(f"✅ Reporte diario guardado en {archivo}")
    return reporte

# AUTOMATIZACIÓN 2: RESUMEN SEMANAL (programado lunes 09:00)
def auto_resumen_semanal():
    _log("▶️ Ejecutando auto_resumen_semanal")
    inicio_semana = _inicio_semana()
    if _ya_procesado("semanal", inicio_semana):
        _log(f"⏭️ Corte semanal desde {inicio_semana} ya fue procesado, se omite")
        return None

    ventas = obtener_ventas_semana()
    if ventas.empty:
        _log("⚠️ Sin datos semanales")
        return None

    reporte = _generar(
        "P14_resumen_semanal",
        datos=ventas.to_csv(index=False)
    )

    guardar_reporte("semanal", reporte)
    archivo = _guardar_archivo(f"semanal_{date.today().isoformat()}", reporte)
    _log(f"✅ Resumen semanal guardado en {archivo}")
    return reporte


# AUTOMATIZACIÓN 3: ALERTA DE STOCK CRÍTICO (cada 2 horas)
# Sin dedup: debe re-evaluar el stock en cada corrida.
def auto_alerta_stock():
    _log("▶️ Ejecutando auto_alerta_stock")
    stock = obtener_stock()
    criticos = stock[stock["stock_actual"] <= stock["stock_minimo"]]
    if criticos.empty:
        _log("✅ Stock OK, sin alertas")
        return None

    alerta = _generar("P07_stock_critico", datos=criticos.to_csv(index=False))
    guardar_reporte("alerta_stock", alerta)

    tabla = "| Producto | Stock actual | Stock mínimo |\n|---|---|---|\n" + "\n".join(
        f"| {r['producto']} | {r['stock_actual']} | {r['stock_minimo']} |"
        for _, r in criticos.iterrows()
    )
    guardar_notificacion("stock_critico", "ALTA", tabla)
    _log(f"⚠️ {len(criticos)} productos críticos detectados")
    return alerta


# AUTOMATIZACIÓN 4: SUGERENCIA DE PEDIDO (diario 07:00)
def auto_sugerir_pedido():
    _log("▶️ Ejecutando auto_sugerir_pedido")
    hoy = date.today().isoformat()
    if _ya_procesado("pedido_proveedor", hoy):
        _log(f"⏭️ Sugerencia de pedido de {hoy} ya fue procesada, se omite")
        return None

    stock = obtener_stock()
    consumo = obtener_consumo_promedio(dias=7)
    datos = stock.merge(consumo, on="producto", how="left").fillna(0)

    sugerencia = _generar("P09_pedido_proveedores",
                          datos=datos.to_csv(index=False))
    guardar_reporte("pedido_proveedor", sugerencia)
    guardar_notificacion("pedido_proveedor", "MEDIA", sugerencia)
    _log("✅ Sugerencia de pedido generada")
    return sugerencia

# AUTOMATIZACIÓN 5: PREDICCIÓN DE DEMANDA (diario 06:00)
def auto_prediccion_demanda():
    _log("▶️ Ejecutando auto_prediccion_demanda")
    hoy = date.today().isoformat()
    if _ya_procesado("prediccion", hoy):
        _log(f"⏭️ Predicción de {hoy} ya fue procesada, se omite")
        return None

    ventas = obtener_ventas_semana()
    if len(ventas) < 3:
        _log("⚠️ Datos insuficientes para predicción")
        return None

    prediccion = _generar("P08_prediccion_demanda",
                          datos=ventas.to_csv(index=False))
    guardar_reporte("prediccion", prediccion)
    _log("✅ Predicción de demanda generada")
    return prediccion


# AUTOMATIZACIÓN 6: ANÁLISIS DE HORAS PICO (domingo 22:00)
def auto_horas_pico():
    _log("▶️ Ejecutando auto_horas_pico")
    hoy = date.today().isoformat()
    if _ya_procesado("horas_pico", hoy):
        _log(f"⏭️ Análisis de horas pico de {hoy} ya fue procesado, se omite")
        return None

    ventas = obtener_ventas_dia() 
    if ventas.empty:
        return None
    analisis = _generar("P05_horas_pico", datos=ventas.to_csv(index=False))
    guardar_reporte("horas_pico", analisis)
    _log("✅ Análisis de horas pico generado")
    return analisis

# AUTOMATIZACIÓN 7: ANÁLISIS DE RENTABILIDAD (semanal)
def auto_rentabilidad():
    _log("▶️ Ejecutando auto_rentabilidad")
    inicio_semana = _inicio_semana()
    if _ya_procesado("rentabilidad", inicio_semana):
        _log(f"⏭️ Análisis de rentabilidad desde {inicio_semana} ya fue procesado, se omite")
        return None

    stock = obtener_stock()
    # Precio y costo están en la tabla productos
    with sqlite3.connect(DB_PATH) as conn:
        import pandas as pd
        df = pd.read_sql_query(
            "SELECT nombre AS producto, precio, costo FROM productos", conn
        )
    df["margen"] = df["precio"] - df["costo"]
    analisis = _generar("P13_rentabilidad", datos=df.to_csv(index=False))
    guardar_reporte("rentabilidad", analisis)
    _log("✅ Análisis de rentabilidad generado")
    return analisis