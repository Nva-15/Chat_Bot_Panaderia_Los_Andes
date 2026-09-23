import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import requests
from database import obtener_notificaciones_no_leidas


def notificar_email(asunto, mensaje, destinatario):
    """Envía notificación por correo (opcional)."""
    remitente = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    if not remitente or not password:
        return False

    msg = MIMEMultipart()
    msg["From"] = remitente
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.attach(MIMEText(mensaje, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remitente, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error enviando correo: {e}")
        return False


def notificar_telegram(mensaje):
    """Envía notificación por Telegram (opcional)."""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": mensaje})
        return r.status_code == 200
    except Exception:
        return False


def obtener_pendientes():
    """Devuelve las notificaciones no leídas para mostrar en Streamlit."""
    return obtener_notificaciones_no_leidas()