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
        "doorControlUsername": "ceroideas",
        "doorControlPassword": "12345678",
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


def _intercom_panphone_sip(
    name: str,
    camera_ip: str,
    *,
    pcb: int,
    switch: int,
    csip_button_id: str,
    door_endpoint: str,
    sip_call_destination: str,
) -> dict[str, Any]:
    """Panphone + SIP tablet vía FreePBX (mapa A: P1=.80/101, P2=.70/100)."""
    ic = _intercom_base(
        name,
        camera_ip,
        pcb,
        switch,
        onvif_user="admin",
        onvif_password="panphone",
        rtsp_path="video1",
        intercom_mode="sip",
        csip_button_id=csip_button_id,
    )
    ic.update(
        {
            "snapshotPath": "camara.php",
            "sipUri": "sip:201@192.168.1.154",
            "sipUsername": "201",
            "sipPassword": "Santander201",
            "sipDomain": "192.168.1.154",
            "sipServer": "192.168.1.154:8088/ws",
            "sipCallDestination": sip_call_destination,
            "csipApiHost": f"{camera_ip}:8090",
            "doorControlUsername": "ceroideas",
            "doorControlPassword": "12345678",
            "doorControlPCB": pcb,
            "doorControlSwitch": switch,
            "doorControlAction": "door_endpoint",
            "doorControlEndpoint": door_endpoint,
            "doorControlRuleKey": "",
            "doorOutputMode": "auto",
        }
    )
    return ic


def _intercom_p1_panphone() -> dict[str, Any]:
    """P1 Calle: Panphone .80 / FreePBX ext 101."""
    return _intercom_panphone_sip(
        "Intercomunicador Calle (P1)",
        "192.168.1.80",
        pcb=2,
        switch=7,
        csip_button_id="p1",
        door_endpoint="api/v1/door/open/p1",
        sip_call_destination="sip:101@192.168.1.154",
    )


def _intercom_p2_panphone() -> dict[str, Any]:
    """P2 Oficina: Panphone .70 / FreePBX ext 100."""
    return _intercom_panphone_sip(
        "Intercomunicador Oficina (P2)",
        "192.168.1.70",
        pcb=3,
        switch=7,
        csip_button_id="p2",
        door_endpoint="api/v1/door/open/p2",
        sip_call_destination="sip:100@192.168.1.154",
    )


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
                "ipExterior": "192.168.1.80",
                "ipInterior": "",
                "intercom": _intercom_p1_panphone(),
            },
            {
                "enabled": True,
                "name": "Oficina (P2)",
                "ipExterior": "192.168.1.70",
                "ipInterior": "",
                "intercom": _intercom_p2_panphone(),
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
