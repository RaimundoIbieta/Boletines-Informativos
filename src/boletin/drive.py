from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from boletin.config import CREDENTIALS_DIR

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_PATH = CREDENTIALS_DIR / "drive_token.json"
CLIENT_SECRET_PATH = CREDENTIALS_DIR / "credentials.json"


def _get_credentials() -> Credentials:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                raise FileNotFoundError(
                    f"Falta {CLIENT_SECRET_PATH}.\n"
                    "1) Crea un proyecto en https://console.cloud.google.com/\n"
                    "2) Habilita Google Drive API\n"
                    "3) Crea credenciales OAuth (app de escritorio)\n"
                    "4) Descarga el JSON como credentials/credentials.json\n"
                    "5) Ejecuta: python -m boletin drive-auth"
                )
            authenticate_drive()
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def authenticate_drive() -> None:
    """Abre el flujo OAuth una vez y guarda el token."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"Falta {CLIENT_SECRET_PATH}. Descarga el JSON OAuth de Google Cloud."
        )

    print("Se abrirá el navegador para autorizar Google Drive.")
    print("Si no se abre, copia la URL que aparezca en la terminal.")
    print("Puerto local: http://localhost:8765/")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(
        port=8765,
        open_browser=True,
        prompt="consent",
        authorization_prompt_message="Abre esta URL en tu navegador:\n{url}\n",
        success_message="Autorización OK. Ya puedes volver a Cursor.",
    )
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Google Drive autenticado. Token en %s", TOKEN_PATH)
    print(f"Token guardado en {TOKEN_PATH}")


def _find_or_create_folder(service, folder_name: str) -> str:
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{folder_name}' and trashed=false"
    )
    result = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=5)
        .execute()
    )
    files = result.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    created = service.files().create(body=meta, fields="id").execute()
    return created["id"]


def upload_pdf(
    pdf_path: Path,
    *,
    folder_name: str = "Boletines Informativos",
) -> dict:
    """
    Sube el PDF a Drive y lo deja legible con link.
    Retorna {file_id, web_view_link, web_content_link}.
    """
    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder_id = _find_or_create_folder(service, folder_name)

    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf", resumable=True)
    meta = {"name": pdf_path.name, "parents": [folder_id]}
    created = (
        service.files()
        .create(body=meta, media_body=media, fields="id, webViewLink, webContentLink")
        .execute()
    )
    file_id = created["id"]

    # Link cualquiera con el enlace
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # Refrescar links
    file = (
        service.files()
        .get(fileId=file_id, fields="id, webViewLink, webContentLink")
        .execute()
    )
    logger.info("PDF subido a Drive: %s", file.get("webViewLink"))
    return {
        "file_id": file["id"],
        "web_view_link": file.get("webViewLink") or "",
        "web_content_link": file.get("webContentLink") or "",
    }
