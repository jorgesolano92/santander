"""Valores por defecto de configuración tablet (sucursal). Espejo de DEFAULT_TABLET_PANEL_CONFIG / defaultDoorAppConfig."""
from __future__ import annotations

import copy
from typing import Any


CSIP_API_KEY_DEFAULT = "f3fb37ac959b795507cf3d6794b1f29b91ed2b1b1d1f06c6"


def _intercom_base(
    name: str,
    camera_ip: str,
    pcb: int,
    switch: int,
    *,
    enabled_audio: bool = True,
    sdk_password: str = "Santander@01",
    onvif_user: str = "ceroideas",
    onvif_password: str = "Cero21264712-",
    rtsp_path: str = "profile1",
    intercom_mode: str = "bridge",
    csip_button_id: str = "p1",
) -> dict[str, Any]:
    return {
        "name": name,
        "cameraIP": camera_ip,
        "httpPort": 80,
        "httpsPort": 443,
        "onvifUsername": onvif_user,
        "onvifPassword": onvif_password,
        "rtspPort": 554,
        "sdkPort": 9008,
        "sdkUsername": "admin",
        "sdkPassword": sdk_password,
        "voiceChannel": -1,
        "intercomMode": intercom_mode,
        "bridgeUrl": "ws://192.168.1.155:8765",
        "videoProfile": "MainStream",
        "snapshotPath": "ISAPI/Streaming/channels/101/picture",
        "sipUri": "",
        "sipUsername": "",
        "sipPassword": "",
        "sipDomain": "",
        "sipServer": "",
        "sipCallDestination": "",
        "csipApiHost": "192.168.1.70:8090",
        "csipApiUseHttps": False,
        "csipApiKey": CSIP_API_KEY_DEFAULT,
        "csipBearerToken": "",
        "sipSignaling": "pbx",
        "sipP2pPeerIp": "",
        "csipCallTargetType": "default",
        "csipCallTarget": "",
        "csipCallUser": "",
        "csipCallRecording": False,
        "csipButtonId": csip_button_id,
        "enableOnvifEvents": True,
        "enableTLS": False,
        "preferredResolution": "1920x1080",
        "preferredFPS": 25,
        "defaultOpenTime": 5,
        "doorControlUsername": "Scati2023",
        "doorControlPassword": "Scati2023",
        "doorControlPCB": pcb,
        "doorControlSwitch": switch,
        "rtspPath": rtsp_path,
        "doorControlManualMode": False,
        "doorControlPulseTime": 1,
        "hasAudio": enabled_audio,
        "doorControlAction": "set_output",
        "doorControlRuleKey": "",
        "doorOutputMode": "auto",
    }


def _intercom_p1_panphone() -> dict[str, Any]:
    """P1 Calle: cámara/CSIP Panphone + SIP tablet vía FreePBX."""
    ic = _intercom_base(
        "Intercomunicador Calle (P1)",
        "192.168.1.70",
        2,
        7,
        onvif_user="admin",
        onvif_password="panphone",
        rtsp_path="video1",
        intercom_mode="sip",
        csip_button_id="p1",
    )
    ic.update(
        {
            "sipUri": "sip:201@192.168.1.154",
            "sipUsername": "201",
            "sipPassword": "Santander201",
            "sipDomain": "192.168.1.154",
            "sipServer": "192.168.1.154:8088/ws",
            "sipCallDestination": "sip:100@192.168.1.154",
            "doorControlAction": "door_endpoint",
            "doorControlEndpoint": "api/v1/door/open/p1",
        }
    )
    return ic


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
                "intercom": _intercom_p1_panphone(),
            },
            {
                "enabled": True,
                "name": "Oficina (P2)",
                "ipExterior": "192.168.1.210",
                "ipInterior": "",
                "intercom": _intercom_base(
                    "Intercomunicador Oficina (P2)",
                    "192.168.1.210",
                    3,
                    7,
                    sdk_password="Santander@01.",
                    csip_button_id="p2",
                ),
            },
            {
                "enabled": False,
                "name": "Puerta 3",
                "ipExterior": "127.0.0.1",
                "ipInterior": "",
                "intercom": _intercom_base(
                    "Intercomunicador Puerta 3",
                    "192.168.1.120",
                    1,
                    5,
                    enabled_audio=False,
                    csip_button_id="p1",
                ),
            },
            {
                "enabled": False,
                "name": "Puerta 4",
                "ipExterior": "",
                "ipInterior": "",
                "intercom": _intercom_base(
                    "Intercomunicador Puerta 4",
                    "",
                    1,
                    4,
                    enabled_audio=False,
                    csip_button_id="p1",
                ),
            },
            {
                "enabled": False,
                "name": "Puerta 5",
                "ipExterior": "",
                "ipInterior": "",
                "intercom": _intercom_base(
                    "Intercomunicador Puerta 5",
                    "",
                    1,
                    5,
                    enabled_audio=False,
                    csip_button_id="p1",
                ),
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
            "rule_key": "pulsador_emergencia_verde_puerta_oficina",
            "action": "set_rule",
            "output_code": "",
            "output_on": True,
        },
        "fireSignal": {
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
            "modes": "horario_manual,horario_carga_cajero,horario_extendido",
            "pulsadores": "p1",
        },
        "configLogin": {
            "ordinal": "admin",
            "password": "123456",
            "revision": "factory",
        },
        "visualization": {
            "autoStartCameras": True,
        },
        "cargaCajero": {
            "videoporteroDoorId": "P2",
        },
    }


def clone_builtin_default_tablet_config() -> dict[str, Any]:
    return copy.deepcopy(get_builtin_default_tablet_config())
