"""WA-02: validacion de la firma X-Hub-Signature-256 con el App Secret."""

import hashlib
import hmac


def firma_valida(cuerpo: bytes, cabecera: str | None, app_secret: str) -> bool:
    if not cabecera or not app_secret or not cabecera.startswith("sha256="):
        return False
    esperada = hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera.removeprefix("sha256="))
