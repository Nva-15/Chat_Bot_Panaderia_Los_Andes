import streamlit as st

# PASO 1: set_page_config DEBE ser la primera llamada a Streamlit
st.set_page_config(
    page_title="Panadería Los Andes",
    page_icon="🥖",
    layout="wide"
)

# PASO 2: Resto de imports
from datetime import date, datetime, timedelta
import pandas as pd

from inicializar_entorno import inicializar_entorno
from scheduler import iniciar_scheduler, listar_tareas, ejecutar_ahora
from prompts import PROMPTS, NORMA_MONEDA
from chatbot import consultar_groq
from pdf_export import generar_pdf_reporte, generar_pdf_comparacion
from pruebas_shot import ejecutar_comparacion
from shot_prompts import DATOS_VENTAS_PRUEBA, PREGUNTA
from database import (
    obtener_stock, obtener_ventas_dia, obtener_top_productos,
    obtener_ventas_semana, registrar_venta, obtener_notificaciones_no_leidas,
    marcar_notificacion_leida, limpiar_notificaciones_leidas, obtener_ultimo_reporte
)

# PASO 3: Inicialización del entorno (BD + datos + ventas de hoy)
# Se ejecuta una sola vez por sesión de servidor gracias a @st.cache_resource

inicializar_entorno()

# PASO 4: Iniciar scheduler (una sola vez por proceso del servidor)
# @st.cache_resource comparte el resultado entre todas las sesiones del
# navegador, así no se registran los trabajos varias veces.
@st.cache_resource(show_spinner=False)
def _arrancar_scheduler():
    iniciar_scheduler()
    return True

try:
    _arrancar_scheduler()
except Exception as e:
    st.warning(f"No se pudo iniciar el scheduler: {e}")

# PASO 5: Estado inicial de la sesión
if "messages" not in st.session_state:
    st.session_state.messages = []
if "role" not in st.session_state:
    st.session_state.role = None

# LOGIN
if st.session_state.role is None:
    st.title("🥖 Panadería Los Andes")
    st.subheader("Acceso interno")
    with st.form("login"):
        rol = st.selectbox("Rol", ["Administrador", "Vendedor"])
        usuario = st.text_input("Usuario")
        clave = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar"):
            st.session_state.role = rol
            st.session_state.usuario = usuario
            st.rerun()
    st.stop()

# SIDEBAR
with st.sidebar:
    st.title("🥖 Los Andes")
    st.write(f"👤 **{st.session_state.usuario}**")
    st.write(f"🔑 **{st.session_state.role}**")
    st.divider()

    MENU_OPCIONES = [
        "💬 Chatbot", "📊 Reportes IA", "🧪 Zero/One/Few-Shot",
        "📦 Inventario", "⚙️ Automatizaciones", "🔔 Notificaciones", "ℹ️ Ayuda"
    ]
    if "menu_opcion" not in st.session_state:
        st.session_state.menu_opcion = MENU_OPCIONES[0]

    # Notificaciones pendientes
    pendientes = obtener_notificaciones_no_leidas()
    if not pendientes.empty:
        if st.button(
            f"🔔 {len(pendientes)} notificaciones pendientes",
            use_container_width=True
        ):
            st.session_state.menu_opcion = "🔔 Notificaciones"
            st.rerun()

    opcion = st.radio("Menú", MENU_OPCIONES, key="menu_opcion")
    st.divider()
    if st.button("🚪 Cerrar sesión"):
        st.session_state.role = None
        st.session_state.messages = []
        st.rerun()

# CHATBOT
if opcion == "💬 Chatbot":
    st.header("🤖 Pandito AI")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Escribe tu consulta..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Detección simple de intención
        p = prompt.lower()
        if any(w in p for w in ["venta", "vend", "ingreso"]):
            cfg = PROMPTS["P19_consulta_ventas"]
            hoy_iso = date.today().isoformat()
            ayer_iso = (date.today() - timedelta(days=1)).isoformat()
            if "ayer" in p:
                fecha_consulta = ayer_iso
            elif "hoy" in p:
                fecha_consulta = hoy_iso
            else:
                fecha_consulta = st.session_state.get(
                    "fecha_consulta_ventas", hoy_iso
                )
            st.session_state.fecha_consulta_ventas = fecha_consulta

            etiqueta = (
                "hoy" if fecha_consulta == hoy_iso
                else "ayer" if fecha_consulta == ayer_iso
                else fecha_consulta
            )
            etiqueta = f"{etiqueta} ({fecha_consulta})"

            ventas = obtener_ventas_dia(fecha_consulta)
            total = round(ventas["total"].sum(), 2) if not ventas.empty else 0.0
            top = obtener_top_productos(fecha_consulta)
            datos = (
                f"Total vendido {etiqueta}: S/ {total:.2f}\n"
                f"Detalle por producto ese día (cantidad y monto en soles):\n"
                f"{top.to_csv(index=False) if not top.empty else 'Sin ventas registradas ese día.'}"
            )
            user_prompt = cfg["usuario"].format(pregunta=prompt, datos=datos)

        elif any(w in p for w in ["stock", "queda", "inventario"]):
            cfg = PROMPTS["P18_consulta_stock"]
            datos = obtener_stock().to_csv(index=False)
            user_prompt = cfg["usuario"].format(pregunta=prompt, datos=datos)

        else:
            cfg = PROMPTS["P20_ayuda_sistema"]
            user_prompt = cfg["usuario"].format(pregunta=prompt)

        # Historial previo acotado
        historial = st.session_state.messages[:-1][-10:]

        with st.chat_message("assistant"):
            with st.spinner("Pandito está pensando..."):
                respuesta = consultar_groq(
                    messages=[
                        {"role": "system", "content": f"{cfg['sistema']} {NORMA_MONEDA}"},
                        *historial,
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=cfg["temperature"],
                    max_tokens=cfg["max_tokens"]
                )
            st.markdown(respuesta)
            st.session_state.messages.append(
                {"role": "assistant", "content": respuesta}
            )

# REPORTES IA (manuales)
elif opcion == "📊 Reportes IA":
    st.header("📊 Reportes Generados por IA")
    st.caption("Estos reportes también se generan automáticamente según el cronograma.")

    if "reporte_actual" not in st.session_state:
        st.session_state.reporte_actual = None

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📈 Reporte diario"):
            with st.spinner("Generando..."):
                from automatizaciones import auto_reporte_diario
                r = auto_reporte_diario()
                ventas = obtener_ventas_dia()
                st.session_state.reporte_actual = {
                    "titulo": "Reporte Diario de Ventas",
                    "nombre_archivo": f"reporte_diario_{date.today().isoformat()}.pdf",
                    "contenido": r or (
                        "Sin ventas registradas hoy, o el corte de hoy "
                        "ya había sido procesado previamente."
                    ),
                    "tabla": {
                        "columnas": ["Hora", "Producto", "Cantidad", "Total (S/)"],
                        "filas": [
                            [f["hora"], f["producto"], f["cantidad"], f"S/ {f['total']:.2f}"]
                            for f in ventas.to_dict("records")
                        ]
                    } if not ventas.empty else None
                }

    with col2:
        if st.button("📊 Resumen semanal"):
            with st.spinner("Generando..."):
                from automatizaciones import auto_resumen_semanal
                r = auto_resumen_semanal()
                ventas = obtener_ventas_semana()
                st.session_state.reporte_actual = {
                    "titulo": "Resumen Semanal de Ventas",
                    "nombre_archivo": f"resumen_semanal_{date.today().isoformat()}.pdf",
                    "contenido": r or (
                        "Sin datos suficientes, o el corte de esta semana "
                        "ya había sido procesado previamente."
                    ),
                    "tabla": {
                        "columnas": ["Fecha", "Total (S/)"],
                        "filas": [
                            [f["fecha"], f"S/ {f['total']:.2f}"]
                            for f in ventas.to_dict("records")
                        ]
                    } if not ventas.empty else None
                }

    with col3:
        if st.button("⚠️ Alerta stock"):
            with st.spinner("Analizando..."):
                from automatizaciones import auto_alerta_stock
                r = auto_alerta_stock()
                stock = obtener_stock()
                criticos = stock[stock["stock_actual"] <= stock["stock_minimo"]]
                st.session_state.reporte_actual = {
                    "titulo": "Alerta de Inventario",
                    "nombre_archivo": f"alerta_stock_{date.today().isoformat()}.pdf",
                    "contenido": r or "Stock OK, no hay productos por debajo del mínimo.",
                    "tabla": {
                        "columnas": ["Producto", "Stock actual", "Stock mínimo"],
                        "filas": criticos[["producto", "stock_actual", "stock_minimo"]].values.tolist()
                    } if not criticos.empty else None
                }

    if st.session_state.reporte_actual:
        rep = st.session_state.reporte_actual
        st.divider()
        st.subheader(rep["titulo"])
        if rep["tabla"]:
            st.dataframe(
                pd.DataFrame(rep["tabla"]["filas"], columns=rep["tabla"]["columnas"]),
                use_container_width=True, hide_index=True
            )
        st.markdown(rep["contenido"])

        pdf_bytes = generar_pdf_reporte(
            rep["titulo"], rep["contenido"], tabla_datos=rep["tabla"]
        )
        st.download_button(
            "⬇️ Descargar en PDF",
            data=pdf_bytes,
            file_name=rep["nombre_archivo"],
            mime="application/pdf"
        )

# ZERO / ONE / FEW-SHOT
elif opcion == "🧪 Zero/One/Few-Shot":
    st.header("🧪 Comparación de técnicas de prompting")
    st.caption(
        "Misma pregunta y mismos datos ficticios para las 3 técnicas. "
        "Solo cambia cómo se arma el prompt enviado a Groq."
    )

    with st.expander("📋 Datos y pregunta usados (fijos para las 3 técnicas)"):
        st.code(DATOS_VENTAS_PRUEBA, language="csv")
        st.write(f"**Pregunta:** {PREGUNTA}")

    if "resultados_shot" not in st.session_state:
        st.session_state.resultados_shot = None

    if st.button("▶️ Ejecutar las 3 técnicas"):
        with st.spinner("Consultando a Groq (Zero-Shot, One-Shot, Few-Shot)..."):
            st.session_state.resultados_shot = ejecutar_comparacion()

    if st.session_state.resultados_shot:
        resultados = st.session_state.resultados_shot

        st.subheader("📊 Evaluación comparativa")
        st.caption("Completa manualmente exactitud/claridad para el informe final.")
        tabla = pd.DataFrame({
            "Técnica": ["Zero-Shot", "One-Shot", "Few-Shot"],
            "Exactitud": ["", "", ""],
            "Claridad": ["", "", ""],
            "Respeta datos": ["", "", ""],
            "Revisión humana": ["Sí", "Sí", "Sí"],
        })
        st.data_editor(tabla, use_container_width=True, hide_index=True)

        pdf_bytes = generar_pdf_comparacion(resultados, PREGUNTA, DATOS_VENTAS_PRUEBA)
        st.download_button(
            "⬇️ Descargar comparación en PDF",
            data=pdf_bytes,
            file_name=f"comparacion_shots_{date.today().isoformat()}.pdf",
            mime="application/pdf"
        )
        st.caption("Cada respuesta también queda guardada como evidencia en la carpeta `pruebas/`.")

# INVENTARIO
elif opcion == "📦 Inventario":
    st.header("📦 Inventario Actual")

    stock = obtener_stock()
    for _, row in stock.iterrows():
        critico = row["stock_actual"] <= row["stock_minimo"]
        icono = "🔴" if critico else "🟢"
        st.write(
            f"{icono} **{row['producto']}** — "
            f"Stock: {row['stock_actual']} / Mín: {row['stock_minimo']} — "
            f"Precio: S/ {row['precio']:.2f}"
        )

    st.divider()
    st.subheader("🧾 Registrar venta")
    st.caption("Estas ventas alimentan el reporte diario y el análisis de horas pico de hoy.")

    with st.form("registrar_venta"):
        producto_nombre = st.selectbox("Producto", stock["producto"])
        cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1)
        if st.form_submit_button("Registrar"):
            producto = stock[stock["producto"] == producto_nombre].iloc[0]
            total = round(cantidad * producto["precio"], 2)
            registrar_venta(
                int(producto["id"]), int(cantidad), total,
                usuario=st.session_state.usuario
            )
            st.session_state.venta_confirmada = {
                "producto": producto_nombre,
                "cantidad": int(cantidad),
                "total": total
            }
            st.rerun()

    if st.session_state.get("venta_confirmada"):
        v = st.session_state.pop("venta_confirmada")
        st.success(
            f"✅ Venta registrada: {v['cantidad']} x {v['producto']} "
            f"(S/ {v['total']:.2f})"
        )

# AUTOMATIZACIONES
elif opcion == "⚙️ Automatizaciones":
    st.header("⚙️ Panel de Automatizaciones")
    st.caption("Tareas programadas que se ejecutan sin intervención manual.")

    tareas = listar_tareas()
    df = pd.DataFrame(tareas)
    st.dataframe(df, use_container_width=True)

    TIPO_REPORTE_POR_JOB = {
        "reporte_diario": "diario",
        "resumen_semanal": "semanal",
        "alerta_stock": "alerta_stock",
        "sugerir_pedido": "pedido_proveedor",
        "prediccion_demanda": "prediccion",
        "horas_pico": "horas_pico",
        "rentabilidad": "rentabilidad",
    }

    st.subheader("🚀 Ejecutar manualmente")
    for t in tareas:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{t['nombre']}**")
            st.caption(f"Próxima: {t['próxima_ejecución']}")
        with col2:
            if st.button("Ejecutar", key=f"run_{t['id']}"):
                with st.spinner("Ejecutando..."):
                    resultado = ejecutar_ahora(t["id"])
                st.session_state.resultado_automatizacion = {
                    "nombre": t["nombre"],
                    "job_id": t["id"],
                    "contenido": resultado
                }
                st.rerun()

    if st.session_state.get("resultado_automatizacion"):
        r = st.session_state.pop("resultado_automatizacion")
        st.divider()
        st.subheader(f"📄 Resultado: {r['nombre']}")

        contenido_mostrado = None
        if r["contenido"]:
            st.success(f"✅ {r['nombre']} se ejecutó correctamente.")
            contenido_mostrado = r["contenido"]
        else:
            tipo = TIPO_REPORTE_POR_JOB.get(r["job_id"])
            ultimo = obtener_ultimo_reporte(tipo) if tipo else None
            if ultimo:
                contenido_mostrado, fecha_generacion = ultimo
                st.info(
                    f"Este corte ya se había generado el "
                    f"{fecha_generacion[:16].replace('T', ' ')}. "
                    "Mostrando ese último resultado:"
                )
            else:
                st.info(
                    "Sin novedades: no había datos suficientes para generar "
                    "este reporte."
                )

        if contenido_mostrado:
            col_contenido, col_pdf = st.columns([4, 1])
            with col_contenido:
                st.markdown(contenido_mostrado)
            with col_pdf:
                pdf_bytes = generar_pdf_reporte(r["nombre"], contenido_mostrado)
                st.download_button(
                    "⬇️ Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"{r['job_id']}_{date.today().isoformat()}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{r['job_id']}"
                )

# NOTIFICACIONES
elif opcion == "🔔 Notificaciones":
    st.header("🔔 Notificaciones del Sistema")

    if st.button("🧹 Limpiar notificaciones ya leídas"):
        limpiar_notificaciones_leidas()
        st.success("Notificaciones leídas eliminadas.")

    pendientes = obtener_notificaciones_no_leidas()
    if pendientes.empty:
        st.info("No hay notificaciones pendientes.")
    else:
        for _, n in pendientes.iterrows():
            color = "🔴" if n["prioridad"] == "ALTA" else "🟡"
            with st.expander(f"{color} [{n['tipo']}] {n['fecha'][:16]}"):
                st.markdown(n["mensaje"])
                if st.button("✅ Marcar como leída", key=f"leida_{n['id']}"):
                    marcar_notificacion_leida(n["id"])
                    st.rerun()

# AYUDA
elif opcion == "ℹ️ Ayuda":
    st.header("ℹ️ Ayuda")
    st.markdown("""
    ### 🤖 Pandito AI
    Chatbot interno con modelo **openai/gpt-oss-120b** vía Groq.

    ### ⚙️ Automatizaciones activas
    | Tarea | Frecuencia | Hora |
    |-------|-----------|------|
    | Reporte diario | Diario | 20:00 |
    | Resumen semanal | Lunes | 09:00 |
    | Alerta de stock | Cada 2h | — |
    | Sugerencia de pedido | Diario | 07:00 |
    | Predicción de demanda | Diario | 06:00 |
    | Análisis horas pico | Domingo | 22:00 |
    | Rentabilidad | Lunes | 10:00 |
    """)