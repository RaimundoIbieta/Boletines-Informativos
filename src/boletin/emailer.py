from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from boletin.config import Settings
from boletin.models import BoletinSemanal

logger = logging.getLogger(__name__)


def send_boletin_email(
    settings: Settings,
    boletin: BoletinSemanal,
    *,
    recipients: list[str],
    html_body: str,
    text_body: str,
    pdf_path: Path,
) -> None:
    if not recipients:
        raise ValueError("No hay destinatarios")

    inicio = boletin.periodo_inicio.strftime("%d/%m/%Y")
    fin = boletin.periodo_fin.strftime("%d/%m/%Y")
    subject = f"{boletin.theme_label} — {inicio} al {fin}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.gmail_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    pdf_bytes = pdf_path.read_bytes()
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )

    password = settings.gmail_app_password.replace(" ", "")
    context = ssl.create_default_context()

    logger.info("Enviando boletín a %s vía Gmail SMTP…", ", ".join(recipients))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(settings.gmail_user, password)
        server.send_message(msg)
    logger.info("Correo enviado correctamente.")
