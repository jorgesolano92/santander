"""Estado sucursal para heartbeat COCE."""
from __future__ import annotations

from typing import Any


def build_heartbeat_payload() -> dict[str, Any]:
    from app.api.routes import panel as panel_mod

    boards_map = panel_mod.pms.get_boards_config_map()
    total = len(boards_map)
    connected = 0
    for bid in boards_map:
        if panel_mod.io_state.get(bid, {}).get("connected"):
            connected += 1
    modbus = connected > 0
    return {
        "modbus": modbus,
        "boards_connected": connected,
        "boards_total": total,
        "current_mode": panel_mod.current_mode,
    }
