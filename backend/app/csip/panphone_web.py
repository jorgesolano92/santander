"""Ajustes de audio de la placa Panphone vía su interfaz web (http://IP:8090).

La API CSIP custom1 no expone el volumen; la web sí (``main.php?id=4``). Se inicia
sesión con ``checklogin.php`` y se reenvía el formulario de audio completo con los
valores actuales, cambiando solo ``volumenSpeaker`` / ``volumenMicro`` (escala 0–10).
"""
from __future__ import annotations

import html
import logging
import re
import threading
from http.cookiejar import CookieJar
from typing import Optional
from urllib import error, parse, request
from urllib.parse import urlparse

from app.core.config import settings
from app.csip.devices import get_device

log = logging.getLogger("csip.panphone_web")

VOLUME_MIN = 0
VOLUME_MAX = 10
_AUDIO_PAGE = "/main.php?id=4"
_AUDIO_FALLBACK = {
    "audio_buffer": "20-160",
    "jitter_buffer": "5-10",
    "datosAudio": "",
}
_lock = threading.Lock()


class PanphoneWebError(RuntimeError):
    pass


def _plate_id(door: str) -> str:
    d = (door or "").strip().lower()
    if d in ("p1", "1", "door1", "calle"):
        return "p1"
    if d in ("p2", "2", "door2", "oficina"):
        return "p2"
    raise PanphoneWebError(f"Puerta desconocida: {door}")


def _web_base(door: str) -> str:
    plate = _plate_id(door)
    device = get_device(plate)
    if not device:
        raise PanphoneWebError(f"Placa {plate} no configurada en CSIP_DEVICES")
    raw = device.base_url if "://" in device.base_url else f"http://{device.base_url}"
    u = urlparse(raw)
    if not u.hostname:
        raise PanphoneWebError(f"base_url inválida para {plate}")
    port = u.port or 8090
    return f"{u.scheme or 'http'}://{u.hostname}:{port}"


class _Session:
    def __init__(self, base: str) -> None:
        self.base = base
        self.opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        self.timeout = float(settings.panphone_web_timeout_s or 8.0)

    def _open(self, path: str, data: Optional[dict[str, str]] = None) -> str:
        body = parse.urlencode(data).encode() if data is not None else None
        req = request.Request(self.base + path, data=body)
        if body is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except error.URLError as e:
            raise PanphoneWebError(f"Placa {self.base} no responde: {e}") from e
        return raw.decode("utf-8", errors="replace")

    def login(self) -> None:
        password = settings.panphone_web_password or ""
        if not password:
            raise PanphoneWebError("PANPHONE_WEB_PASSWORD no configurada en el .env del panel")
        self._open("/")
        self._open(
            "/checklogin.php",
            {"myusername": settings.panphone_web_user or "admin", "mypassword": password, "lang": "ES"},
        )

    def get(self, path: str) -> str:
        return self._open(path)

    def post(self, path: str, data: dict[str, str]) -> str:
        return self._open(path, data)


def _attr(tag: str, name: str) -> Optional[str]:
    m = re.search(rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.I)
    if not m:
        return None
    return html.unescape(next(g for g in m.groups() if g is not None))


def _audio_form(page: str) -> str:
    idx = page.find('name="volumenSpeaker"')
    if idx < 0:
        idx = page.find("name='volumenSpeaker'")
    if idx < 0:
        raise PanphoneWebError("No se encontró el formulario de audio (¿credenciales web incorrectas?)")
    start = page.rfind("<form", 0, idx)
    end = page.find("</form>", idx)
    return page[start if start >= 0 else 0 : end if end >= 0 else len(page)]


def _form_values(form: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for m in re.finditer(r"<input\b[^>]*>", form, re.I):
        tag = m.group(0)
        name = _attr(tag, "name")
        kind = (_attr(tag, "type") or "text").lower()
        if not name or kind in ("submit", "button", "reset", "image", "file"):
            continue
        if re.search(r"\bdisabled\b", tag, re.I):
            continue
        if kind in ("checkbox", "radio"):
            if re.search(r"\bchecked\b", tag, re.I):
                values[name] = _attr(tag, "value") or "on"
            continue
        values[name] = _attr(tag, "value") or ""
    for m in re.finditer(r"<select\b([^>]*)>(.*?)</select>", form, re.I | re.S):
        name = _attr(m.group(1), "name")
        if not name:
            continue
        options = re.findall(r"<option\b[^>]*>", m.group(2), re.I)
        chosen = next((o for o in options if re.search(r"\bselected\b", o, re.I)), options[0] if options else None)
        if chosen is not None:
            values[name] = _attr(chosen, "value") or ""
    for m in re.finditer(r"<textarea\b([^>]*)>(.*?)</textarea>", form, re.I | re.S):
        name = _attr(m.group(1), "name")
        if name:
            values[name] = html.unescape(m.group(2).strip())
    return values


def _to_level(raw: Optional[str]) -> Optional[int]:
    try:
        return max(VOLUME_MIN, min(VOLUME_MAX, int(str(raw).strip())))
    except (TypeError, ValueError):
        return None


def _read(session: _Session) -> dict[str, str]:
    values = _form_values(_audio_form(session.get(_AUDIO_PAGE)))
    if "volumenSpeaker" not in values or "volumenMicro" not in values:
        raise PanphoneWebError("La placa no devolvió los volúmenes actuales")
    return values


def _public(door: str, values: dict[str, str]) -> dict:
    return {
        "door": _plate_id(door),
        "speaker": _to_level(values.get("volumenSpeaker")),
        "microphone": _to_level(values.get("volumenMicro")),
        "min": VOLUME_MIN,
        "max": VOLUME_MAX,
    }


def get_audio(door: str) -> dict:
    with _lock:
        session = _Session(_web_base(door))
        session.login()
        return _public(door, _read(session))


def set_audio(door: str, *, speaker: Optional[int] = None, microphone: Optional[int] = None) -> dict:
    if speaker is None and microphone is None:
        raise PanphoneWebError("Indica speaker o microphone")
    with _lock:
        session = _Session(_web_base(door))
        session.login()
        current = _read(session)
        payload = {**_AUDIO_FALLBACK, **current}
        if speaker is not None:
            payload["volumenSpeaker"] = str(_to_level(speaker))
        if microphone is not None:
            payload["volumenMicro"] = str(_to_level(microphone))
        session.post(_AUDIO_PAGE, payload)
        result = _public(door, _read(session))
    log.info("Panphone %s audio -> altavoz=%s micro=%s", result["door"], result["speaker"], result["microphone"])
    return result
