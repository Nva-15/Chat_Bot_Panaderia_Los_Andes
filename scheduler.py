"""
Programador de tareas automatizadas con APScheduler.
Se inicia al arrancar Streamlit y corre en segundo plano.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import atexit

from automatizaciones import (
    auto_reporte_diario,
    auto_resumen_semanal,
    auto_alerta_stock,
    auto_sugerir_pedido,
    auto_prediccion_demanda,
    auto_horas_pico,
    auto_rentabilidad
)

scheduler = BackgroundScheduler(timezone="America/Lima")


def iniciar_scheduler():
    """Registra y arranca todas las tareas programadas."""

    # 1. Reporte diario a las 20:00
    scheduler.add_job(
        auto_reporte_diario,
        CronTrigger(hour=20, minute=0),
        id="reporte_diario",
        name="Reporte diario de ventas",
        replace_existing=True
    )

    # 2. Resumen semanal lunes 09:00
    scheduler.add_job(
        auto_resumen_semanal,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="resumen_semanal",
        name="Resumen semanal gerencial",
        replace_existing=True
    )

    # 3. Alerta de stock cada 2 horas
    scheduler.add_job(
        auto_alerta_stock,
        IntervalTrigger(hours=2),
        id="alerta_stock",
        name="Alerta de stock crítico",
        replace_existing=True
    )

    # 4. Sugerencia de pedido todos los días a las 07:00
    scheduler.add_job(
        auto_sugerir_pedido,
        CronTrigger(hour=7, minute=0),
        id="sugerir_pedido",
        name="Sugerencia de pedido a proveedores",
        replace_existing=True
    )

    # 5. Predicción de demanda todos los días a las 06:00
    scheduler.add_job(
        auto_prediccion_demanda,
        CronTrigger(hour=6, minute=0),
        id="prediccion_demanda",
        name="Predicción de demanda",
        replace_existing=True
    )

    # 6. Análisis de horas pico domingos a las 22:00
    scheduler.add_job(
        auto_horas_pico,
        CronTrigger(day_of_week="sun", hour=22, minute=0),
        id="horas_pico",
        name="Análisis de horas pico",
        replace_existing=True
    )

    # 7. Rentabilidad semanal los lunes a las 10:00
    scheduler.add_job(
        auto_rentabilidad,
        CronTrigger(day_of_week="mon", hour=10, minute=0),
        id="rentabilidad",
        name="Análisis de rentabilidad",
        replace_existing=True
    )

    scheduler.start()
    print(f"🚀 Scheduler iniciado a las {datetime.now().isoformat()}")
    print(f"📋 Tareas registradas: {[job.name for job in scheduler.get_jobs()]}")

    # Cierre limpio al salir
    atexit.register(lambda: scheduler.shutdown(wait=False))


def listar_tareas():
    """Devuelve las tareas activas con su próxima ejecución."""
    return [
        {
            "id": job.id,
            "nombre": job.name,
            "próxima_ejecución": str(job.next_run_time),
            "estado": "activa"
        }
        for job in scheduler.get_jobs()
    ]


def ejecutar_ahora(job_id):
    """Ejecuta una tarea manualmente y devuelve el resultado generado."""
    job = scheduler.get_job(job_id)
    if job:
        return job.func()
    return None