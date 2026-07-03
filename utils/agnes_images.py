"""
Gemeinsamer Agnes-API-Client für Bildgenerierung (Pets, Zombies, …).
"""

from __future__ import annotations

import base64
import logging

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


class AgnesImageError(Exception):
    """Fehler bei der Agnes-Bildgenerierung."""


def agnes_configured() -> bool:
    """True wenn ein Agnes-API-Key gesetzt ist."""
    return bool(Config.AGNES_API_KEY)


async def request_agnes_image(prompt: str) -> bytes:
    """Ruft die Agnes-API auf und liefert Bild-Bytes (PNG)."""
    if not agnes_configured():
        raise AgnesImageError(
            "Agnes-API nicht konfiguriert. Trage `AGNES_API_KEY` in der `.env` ein."
        )

    payload = {
        "model": Config.AGNES_IMAGE_MODEL,
        "prompt": prompt,
        "size": Config.AGNES_IMAGE_SIZE,
        "return_base64": True,
    }
    headers = {
        "Authorization": f"Bearer {Config.AGNES_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=Config.AGNES_REQUEST_TIMEOUT)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(Config.AGNES_API_URL, json=payload, headers=headers) as response:
                body = await response.json(content_type=None)
                if response.status >= 400:
                    message = body.get("error", {}).get("message") if isinstance(body, dict) else None
                    detail = message or str(body)
                    raise AgnesImageError(f"Agnes-API Fehler ({response.status}): {detail}")

                if not isinstance(body, dict):
                    raise AgnesImageError("Ungültige Antwort der Agnes-API.")

                data = body.get("data") or []
                if not data:
                    raise AgnesImageError("Agnes-API hat kein Bild geliefert.")

                item = data[0]
                if isinstance(item, dict):
                    b64_data = item.get("b64_json")
                    if b64_data:
                        return base64.b64decode(b64_data)

                    image_url = item.get("url")
                    if image_url:
                        async with session.get(image_url) as image_response:
                            if image_response.status >= 400:
                                raise AgnesImageError("Bild-Download fehlgeschlagen.")
                            return await image_response.read()

                raise AgnesImageError("Agnes-API Antwort enthält kein Bild.")
    except aiohttp.ClientError as exc:
        logger.exception("Agnes-API Netzwerkfehler")
        raise AgnesImageError("Verbindung zur Agnes-API fehlgeschlagen.") from exc
