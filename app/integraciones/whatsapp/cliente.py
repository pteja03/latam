"""Cliente de WhatsApp Cloud API: envio de texto/plantillas y descarga de media."""

from dataclasses import dataclass

import httpx

from app.core.config import obtener_config

URL_GRAPH = "https://graph.facebook.com"
MAX_TEXTO = 4096


class MediaDemasiadoGrande(Exception):
    pass


@dataclass
class Media:
    datos: bytes
    mime_type: str


def solo_digitos(telefono: str) -> str:
    return "".join(c for c in telefono if c.isdigit())


def candidatos_e164(telefono_wa: str) -> list[str]:
    """Formas E.164 posibles de un `from` de WhatsApp.

    Mexico: WhatsApp entrega 521XXXXXXXXXX aunque el numero sea +52XXXXXXXXXX.
    """
    digitos = solo_digitos(telefono_wa)
    candidatos = [f"+{digitos}"]
    if digitos.startswith("521") and len(digitos) == 13:
        candidatos.append(f"+52{digitos[3:]}")
    elif digitos.startswith("52") and len(digitos) == 12:
        candidatos.append(f"+521{digitos[2:]}")
    return candidatos


class ClienteWhatsApp:
    def __init__(self, http: httpx.AsyncClient) -> None:
        cfg = obtener_config()
        self._http = http
        self._base = f"{URL_GRAPH}/{cfg.wa_api_version}"
        self._id_numero = cfg.wa_phone_number_id
        self._cabeceras = {"Authorization": f"Bearer {cfg.wa_access_token}"}
        self._idioma = cfg.wa_plantilla_idioma

    async def _enviar(self, cuerpo: dict) -> None:
        respuesta = await self._http.post(
            f"{self._base}/{self._id_numero}/messages",
            headers=self._cabeceras,
            json={"messaging_product": "whatsapp", **cuerpo},
        )
        respuesta.raise_for_status()

    async def enviar_texto(self, telefono: str, texto: str) -> None:
        await self._enviar(
            {
                "to": solo_digitos(telefono),
                "type": "text",
                "text": {"body": texto[:MAX_TEXTO], "preview_url": False},
            }
        )

    async def enviar_plantilla(self, telefono: str, nombre: str, parametros: list[str]) -> None:
        """Fuera de la ventana de 24 h Meta solo permite plantillas aprobadas (IA-16, IA-18)."""
        await self._enviar(
            {
                "to": solo_digitos(telefono),
                "type": "template",
                "template": {
                    "name": nombre,
                    "language": {"code": self._idioma},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": p} for p in parametros],
                        }
                    ],
                },
            }
        )

    async def descargar_media(self, media_id: str, max_bytes: int) -> Media:
        """IA-01: GET /{media_id} -> URL; GET a la URL -> bytes. Solo en memoria (IA-02)."""
        meta = await self._http.get(f"{self._base}/{media_id}", headers=self._cabeceras)
        meta.raise_for_status()
        info = meta.json()
        if int(info.get("file_size") or 0) > max_bytes:
            raise MediaDemasiadoGrande
        archivo = await self._http.get(info["url"], headers=self._cabeceras)
        archivo.raise_for_status()
        if len(archivo.content) > max_bytes:
            raise MediaDemasiadoGrande
        mime = (info.get("mime_type") or "audio/ogg").split(";")[0].strip()
        return Media(datos=archivo.content, mime_type=mime)
