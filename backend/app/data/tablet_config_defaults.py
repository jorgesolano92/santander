"""Valores por defecto de configuración tablet (sucursal). Espejo de defaultDoorAppConfig.ts."""
from __future__ import annotations

import copy
from typing import Any


def _intercom(
    name: str,
    camera_ip: str,
    pcb: int,
    switch: int,
    *,
    enabled_audio: bool = True,
    sdk_password: str = "Santander@01",
) -> dict[str, Any]:
    return {
        "name": name,
        "cameraIP": camera_ip,
        "httpPort": 80,
        "httpsPort": 443,
        "onvifUsername": "ceroideas",
        "onvifPassword": "Cero21264712-",
        "rtspPort": 554,
        "sdkPort": 9008,
        "sdkUsername": "admin",
        "sdkPassword": sdk_password,
        "voiceChannel": -1,
        "intercomMode": "bridge",
        "bridgeUrl": "ws://192.168.1.155:8765",
        "videoProfile": "MainStream",
        "snapshotPath": "ISAPI/Streaming/channels/101/picture",
        "sipUri": "",
        "sipUsername": "",
        "sipPassword": "",
        "sipDomain": "",
        "enableOnvifEvents": True,
        "enableTLS": False,
        "preferredResolution": "1920x1080",
        "preferredFPS": 25,
        "defaultOpenTime": 5,
        "doorControlUsername": "Scati2023",
        "doorControlPassword": "Scati2023",
        "doorControlPCB": pcb,
        "doorControlSwitch": switch,
        "rtspPath": "profile1",
        "doorControlManualMode": False,
        "doorControlPulseTime": 1,
        "hasAudio": enabled_audio,
        "doorControlAction": "set_output",
        "doorControlRuleKey": "",
        "doorOutputMode": "auto",
    }


def _mode(rule_key: str) -> dict[str, Any]:
    return {
        "rule_key": rule_key,
        "action": "set_rule",
        "enabled": True,
        "output_code": "",
        "output_on": True,
    }


def get_builtin_default_tablet_config() -> dict[str, Any]:
  return {
        "doors": [
            {
                "enabled": True,
                "name": "Calle (P1)",
                "ipExterior": "192.168.1.200",
                "ipInterior": "",
                "intercom": _intercom("Intercomunicador Calle (P1)", "192.168.1.200", 2, 7),
            },
            {
                "enabled": True,
                "name": "Oficina (P2)",
                "ipExterior": "192.168.1.210",
                "ipInterior": "",
                "intercom": _intercom(
                    "Intercomunicador Oficina (P2)",
                    "192.168.1.210",
                    3,
                    7,
                    sdk_password="Santander@01.",
                ),
            },
            {
                "enabled": False,
                "name": "Puerta 3",
                "ipExterior": "127.0.0.1",
                "ipInterior": "",
                "intercom": _intercom("Intercomunicador Puerta 3", "192.168.1.120", 1, 5, enabled_audio=False),
            },
            {
                "enabled": False,
                "name": "Puerta 4",
                "ipExterior": "",
                "ipInterior": "",
                "intercom": _intercom("Intercomunicador Puerta 4", "", 1, 4, enabled_audio=False),
            },
            {
                "enabled": False,
                "name": "Puerta 5",
                "ipExterior": "",
                "ipInterior": "",
                "intercom": _intercom("Intercomunicador Puerta 5", "", 1, 5, enabled_audio=False),
            },
        ],
        "network": {
            "consoleIP": "192.168.1.155",
            "netmask": "255.255.255.0",
            "gateway": "0.0.0.0",
        },
        "api": {
            "port": 8000,
            "username": "ceroideas",
            "password": "12345678",
            "urlToken": "/api/v1/auth/token",
            "urlGet": "/api/v1/get_mode",
            "urlPost": "/api/v1/set_mode",
            "urlModes": "/api/v1/modes",
        },
        "schedules": {
            "comercial": {"ini1": "08:00", "ini2": "14:00"},
            "extendido": {"ini1": "07:00", "ini2": "22:00"},
            "autoservicio": {"ini1": "00:00", "ini2": "23:59"},
            "cerrado": {"ini1": "22:00", "ini2": "08:00"},
        },
        "officeWithATM": False,
        "emergency": {
            "enabled": True,
            "rule_key": "senal_de_incendio_activada",
            "action": "set_rule",
            "output_code": "",
            "output_on": True,
        },
        "modes": {
            "automatico": _mode("horario_automatico"),
            "esclusa": _mode("horario_esclusa"),
            "extendido": _mode("horario_extendido"),
            "autoservicio": _mode("horario_autoservicio"),
            "oficinaCerrada": _mode("horario_cerrado"),
            "cargaCajero": _mode("horario_carga_cajero"),
            "manual": _mode("horario_manual"),
        },
        "tabletCall": {
            "enabled": True,
            "timeoutSeconds": 30,
            "modes": "horario_manual,horario_carga_cajero",
            "pulsadores": "p1",
        },
    }


def clone_builtin_default_tablet_config() -> dict[str, Any]:
    return copy.deepcopy(get_builtin_default_tablet_config())
