"""Persistencia de módulos Modbus del panel (IN/OUT configurables, all on/off)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import get_connection

# Valores por defecto ETD8A12 (si open_cmd/close_cmd son NULL en BD)
DEFAULT_CMD_OPEN = 0x0100
DEFAULT_CMD_CLOSE = 0x0200
DEFAULT_CMD_OPEN_ALL = 0x0700
DEFAULT_CMD_CLOSE_ALL = 0x0800
DEFAULT_REG_OUTPUT_START = 0x0000
DEFAULT_REG_INPUT_START = 0x0080
DEFAULT_REG_OUTPUT_BITS = 0x0070
# Instalación fija en nomenclatura SMCSE del Excel (siempre 01 en este proyecto).
SMCSE_INSTALLATION_ID = 1


def format_smcse_code(kind: str, module_id: int, slot_index: int, *, installation_id: int = SMCSE_INSTALLATION_ID) -> str:
    """
    Genera código SMCSE: SMCSE_DI_01_02_01 = entrada, placa 2, canal 1.
    SMCSE_DO_01_03_07 = salida, placa 3, canal 7.
    """
    if kind not in ("input", "output"):
        raise ValueError("kind debe ser input u output")
    io = "DI" if kind == "input" else "DO"
    return f"SMCSE_{io}_{installation_id:02d}_{module_id:02d}_{slot_index:02d}"


def parse_smcse_code(code: str) -> Optional[Tuple[str, int, int]]:
    """
    Interpreta SMCSE_DI_01_02_01 → (kind='input', module_id=2, slot_index=1).
    También acepta DI_01_02_01 / DO_01_02_01 sin prefijo SMCSE.
    """
    if not code or not str(code).strip():
        return None
    parts = str(code).strip().upper().split("_")
    if len(parts) == 5 and parts[0] == "SMCSE" and parts[1] in ("DI", "DO"):
        inst, module_id, slot_index = int(parts[2]), int(parts[3]), int(parts[4])
    elif len(parts) == 4 and parts[0] in ("DI", "DO"):
        inst, module_id, slot_index = int(parts[1]), int(parts[2]), int(parts[3])
    else:
        return None
    if inst != SMCSE_INSTALLATION_ID:
        return None
    kind = "input" if (parts[1] if parts[0] == "SMCSE" else parts[0]) == "DI" else "output"
    return kind, module_id, slot_index


def format_channel_label(kind: str, module_id: int, slot_index: int) -> str:
    """Código guardado en `panel_module_channels.label` y reglas JSON: IN_MM_SS / OUT_MM_SS."""
    prefix = "IN" if kind == "input" else "OUT"
    return f"{prefix}_{module_id:02d}_{slot_index:02d}"


def smcse_to_in_out_codes(kind: str, module_id: int, slot_index: int) -> Tuple[str, str]:
    """Par (IN_MM_SS, SMCSE_…) o (SMCSE_…, OUT_MM_SS) según tipo de canal."""
    io = format_channel_label(kind, module_id, slot_index)
    smcse = format_smcse_code(kind, module_id, slot_index)
    return (io, smcse) if kind == "input" else (smcse, io)


# Nombres por canal según ENTRADAS Y SALIDAS.xlsx / CORRELACION_ENTRADAS_SALIDAS.md
# (module_id, kind, slot_index 1..12, channel_name)
_DEFAULT_CHANNEL_NAME_ROWS: Tuple[Tuple[int, str, int, str], ...] = (
    # Módulo 1 — Central
    (1, "input", 1, "Horario Automático"),
    (1, "input", 2, "Horario Esclusa"),
    (1, "input", 3, "Horario Extendido"),
    (1, "input", 4, "Horario Autoservicio"),
    (1, "input", 5, "Horario Cerrado"),
    (1, "input", 6, "Horario Carga Cajero"),
    (1, "input", 7, "Horario Manual"),
    (1, "input", 8, "Apertura Remota COCE Oficina"),
    (1, "input", 9, "Incendio"),
    (1, "input", 10, "Alarma Conectada"),
    (1, "input", 11, "Presencia Zaguán"),
    (1, "input", 12, "Apertura Remota Calle"),
    (1, "output", 1, "Alarma Zaguán"),
    (1, "output", 2, "Locución Cajero Ocupado"),
    (1, "output", 3, "Locución Pase Por Favor"),
    (1, "output", 4, "Locución Por Su Seguridad"),
    # Módulo 2 — Puerta Calle
    (2, "input", 1, "Radar Interior"),
    (2, "input", 2, "Radar Exterior"),
    (2, "input", 3, "Inductivo (Llave Echada)"),
    (2, "input", 4, "Inductivo (Puerta Abierta/Cerrada)"),
    (2, "input", 5, "Pulsador Emergencia Puerta"),
    (2, "input", 6, "Pulsador Verde (Paralelo EMICOM)"),
    (2, "input", 7, "Llamada Interior"),
    (2, "input", 8, "Llamada Exterior"),
    (2, "input", 9, "Bloqueo Zaguán (Libre)"),
    (2, "input", 10, "Presencia Zaguán"),
    (2, "input", 11, "ICR 2 (Libre)"),
    (2, "input", 12, "Llave Emergencia"),
    (2, "output", 1, "Llave Echada (EMICOM) Selector A"),
    (2, "output", 2, "Llave Echada (Alimentación Bobinas)"),
    (2, "output", 3, "Emergencia Incendio (EMICOM) Night Bank"),
    (2, "output", 4, "Emergencia Resto (EMICOM) Night Bank"),
    (2, "output", 5, "Anulación ICR 2 (EMICOM) Lock"),
    (2, "output", 6, "Anulación Alimentación Pila Winhouse"),
    (2, "output", 7, "Orden de Apertura (EMICOM) EM/OPEN/CLOSE"),
    # Módulo 3 — Puerta Oficina
    (3, "input", 1, "Radar Interior"),
    (3, "input", 2, "Radar Exterior"),
    (3, "input", 3, "Inductivo (Llave Echada)"),
    (3, "input", 4, "Inductivo (Puerta Abierta/Cerrada)"),
    (3, "input", 5, "Pulsador Emergencia Puerta"),
    (3, "input", 6, "Pulsador Verde (Paralelo EMICOM)"),
    (3, "input", 7, "Llamada Interior"),
    (3, "input", 8, "Llamada Exterior"),
    (3, "input", 9, "Bloqueo Zaguán (Libre)"),
    (3, "input", 10, "Presencia Zaguán"),
    (3, "input", 11, "ICR 2 (Libre)"),
    (3, "input", 12, "Llave Emergencia"),
    (3, "output", 1, "Llave Echada (EMICOM) Selector A"),
    (3, "output", 2, "Llave Echada (Alimentación Bobinas)"),
    (3, "output", 3, "Emergencia Incendio (EMICOM) Night Bank"),
    (3, "output", 4, "Emergencia Resto (EMICOM) Night Bank"),
    (3, "output", 5, "Anulación ICR 2 (EMICOM) Lock"),
    (3, "output", 6, "Anulación Alimentación Pila Winhouse"),
    (3, "output", 7, "Orden de Apertura (EMICOM) EM/OPEN/CLOSE"),
)


def _default_channel_name(module_id: int, kind: str, slot_index: int) -> Optional[str]:
    for mid, k, slot, name in _DEFAULT_CHANNEL_NAME_ROWS:
        if mid == module_id and k == kind and slot == slot_index:
            return name
    return None


def sync_channel_names_from_catalog(*, only_if_empty: bool = True) -> int:
    """
    Rellena `channel_name` y `label` (IN_MM_SS / OUT_MM_SS) según catálogo y placa/canal.
    Devuelve número de filas actualizadas.
    """
    ensure_panel_modules_schema()
    updated = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, module_id, kind, slot_index, label, channel_name
            FROM panel_module_channels
            """
        ).fetchall()
        for cid, module_id, kind, slot_index, current_label, current_name in rows:
            mid = int(module_id)
            k = str(kind)
            slot = int(slot_index)
            io_label = format_channel_label(k, mid, slot)
            catalog_name = _default_channel_name(mid, k, slot)
            sets: List[str] = []
            vals: List[Any] = []
            if not only_if_empty or not current_label:
                sets.append("label = ?")
                vals.append(io_label)
            if catalog_name and (not only_if_empty or not current_name):
                sets.append("channel_name = ?")
                vals.append(catalog_name)
            if not sets:
                continue
            vals.append(cid)
            conn.execute(
                f"UPDATE panel_module_channels SET {', '.join(sets)} WHERE id = ?",
                vals,
            )
            updated += 1
        conn.commit()
    return updated


def _ensure_channel_name_column(conn: Any) -> None:
    """Migración: añade `channel_name` en BD creadas antes de este campo."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(panel_module_channels)").fetchall()}
    if "channel_name" not in cols:
        conn.execute("ALTER TABLE panel_module_channels ADD COLUMN channel_name TEXT")


def _ensure_pulse_columns(conn: Any) -> None:
    """Migración: contador de pulsaciones físicas y límite de mantenimiento (solo IN)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(panel_module_channels)").fetchall()}
    if "pulse_count" not in cols:
        conn.execute(
            "ALTER TABLE panel_module_channels ADD COLUMN pulse_count INTEGER NOT NULL DEFAULT 0"
        )
    if "pulse_limit" not in cols:
        conn.execute("ALTER TABLE panel_module_channels ADD COLUMN pulse_limit INTEGER")


def ensure_panel_modules_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 5000,
                slave_id INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                bitmask_address INTEGER,
                relation_register INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_module_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('input', 'output')),
                slot_index INTEGER NOT NULL,
                label TEXT,
                channel_name TEXT,
                address INTEGER NOT NULL,
                open_cmd INTEGER,
                close_cmd INTEGER,
                FOREIGN KEY (module_id) REFERENCES panel_modules(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_panel_channels_module_kind
            ON panel_module_channels (module_id, kind, slot_index)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_module_bulk (
                module_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('all_on', 'all_off')),
                address INTEGER NOT NULL,
                value INTEGER NOT NULL,
                PRIMARY KEY (module_id, kind),
                FOREIGN KEY (module_id) REFERENCES panel_modules(id) ON DELETE CASCADE
            )
            """
        )
        _ensure_channel_name_column(conn)
        _ensure_pulse_columns(conn)
        conn.commit()


def _row_module(row: Tuple[Any, ...]) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "host": row[2],
        "port": row[3],
        "slave_id": row[4],
        "sort_order": row[5],
        "bitmask_address": row[6],
        "relation_register": row[7],
    }


def _row_channel(row: Tuple[Any, ...]) -> dict:
    module_id = int(row[1])
    kind = str(row[2])
    slot_index = int(row[3])
    label = row[4]
    in_code, out_code = smcse_to_in_out_codes(kind, module_id, slot_index)
    io_code = in_code if kind == "input" else out_code
    out = {
        "id": row[0],
        "module_id": module_id,
        "kind": kind,
        "slot_index": slot_index,
        "label": label or io_code,
        "smcse_code": format_smcse_code(kind, module_id, slot_index),
        "io_code": io_code,
        "channel_name": row[5],
        "address": row[6],
        "open_cmd": row[7],
        "close_cmd": row[8],
    }
    if kind == "input":
        out["pulse_count"] = int(row[9] or 0)
        out["pulse_limit"] = int(row[10]) if row[10] is not None else None
    return out


_CHANNEL_SELECT = """
    SELECT id, module_id, kind, slot_index, label, channel_name, address, open_cmd, close_cmd,
           COALESCE(pulse_count, 0), pulse_limit
    FROM panel_module_channels
"""


def list_module_ids_ordered() -> List[int]:
    ensure_panel_modules_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM panel_modules ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        return [r[0] for r in rows]


def get_boards_config_map() -> Dict[int, dict]:
    """Mapa id -> {name, host, port, slave_id} para runtime Modbus."""
    ensure_panel_modules_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, host, port, slave_id, sort_order, bitmask_address, relation_register
            FROM panel_modules ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
    return {r[0]: _row_module(r) for r in rows}


def get_channels_for_module(module_id: int) -> Tuple[List[dict], List[dict]]:
    ensure_panel_modules_schema()
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            {_CHANNEL_SELECT}
            WHERE module_id = ?
            ORDER BY kind ASC, slot_index ASC, id ASC
            """,
            (module_id,),
        ).fetchall()
    inputs = [_row_channel(r) for r in rows if r[2] == "input"]
    outputs = [_row_channel(r) for r in rows if r[2] == "output"]
    return inputs, outputs


def get_bulk_commands(module_id: int) -> Dict[str, Tuple[int, int]]:
    ensure_panel_modules_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT kind, address, value FROM panel_module_bulk WHERE module_id = ?",
            (module_id,),
        ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def get_full_config_for_api() -> List[dict]:
    """Lista de módulos con canales y bulk para el frontend."""
    ensure_panel_modules_schema()
    mids = list_module_ids_ordered()
    out: List[dict] = []
    for mid in mids:
        cfg = get_boards_config_map().get(mid)
        if not cfg:
            continue
        ins, outs = get_channels_for_module(mid)
        bulk = get_bulk_commands(mid)
        out.append(
            {
                **cfg,
                "inputs": ins,
                "outputs": outs,
                "bulk": {
                    "all_on": {"address": bulk["all_on"][0], "value": bulk["all_on"][1]} if "all_on" in bulk else None,
                    "all_off": {"address": bulk["all_off"][0], "value": bulk["all_off"][1]} if "all_off" in bulk else None,
                },
            }
        )
    return out


def create_module(name: str, host: str, port: int = 5000, slave_id: int = 1) -> int:
    ensure_panel_modules_schema()
    with get_connection() as conn:
        max_so = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM panel_modules").fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO panel_modules (name, host, port, slave_id, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, host, port, slave_id, max_so + 1),
        )
        mid = int(cur.lastrowid)
        conn.commit()
    return mid


def update_module(
    module_id: int,
    *,
    name: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    slave_id: Optional[int] = None,
    sort_order: Optional[int] = None,
    bitmask_address: Any = ...,
    relation_register: Any = ...,
) -> None:
    """Actualiza solo los argumentos distintos de None / omitidos (bitmask/relation usan ... = no tocar)."""
    ensure_panel_modules_schema()
    fields: List[str] = []
    vals: List[Any] = []
    if name is not None:
        fields.append("name = ?")
        vals.append(name)
    if host is not None:
        fields.append("host = ?")
        vals.append(host)
    if port is not None:
        fields.append("port = ?")
        vals.append(port)
    if slave_id is not None:
        fields.append("slave_id = ?")
        vals.append(slave_id)
    if sort_order is not None:
        fields.append("sort_order = ?")
        vals.append(sort_order)
    if bitmask_address is not ...:
        fields.append("bitmask_address = ?")
        vals.append(bitmask_address)
    if relation_register is not ...:
        fields.append("relation_register = ?")
        vals.append(relation_register)
    if not fields:
        return
    vals.append(module_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE panel_modules SET {', '.join(fields)} WHERE id = ?", vals)
        conn.commit()


def apply_module_update(module_id: int, fields: Dict[str, Any]) -> None:
    """Actualiza columnas presentes en `fields` (permite NULL explícito en bitmask_address / relation_register)."""
    allowed = {"name", "host", "port", "slave_id", "sort_order", "bitmask_address", "relation_register"}
    ensure_panel_modules_schema()
    cols: List[str] = []
    vals: List[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        cols.append(f"{k} = ?")
        vals.append(v)
    if not cols:
        return
    vals.append(module_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE panel_modules SET {', '.join(cols)} WHERE id = ?", vals)
        conn.commit()


def delete_module(module_id: int) -> bool:
    ensure_panel_modules_schema()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM panel_modules WHERE id = ?", (module_id,))
        conn.commit()
        return cur.rowcount > 0


def add_channel(
    module_id: int,
    kind: str,
    address: int,
    *,
    slot_index: Optional[int] = None,
    label: Optional[str] = None,
    channel_name: Optional[str] = None,
    open_cmd: Optional[int] = None,
    close_cmd: Optional[int] = None,
) -> int:
    ensure_panel_modules_schema()
    if kind not in ("input", "output"):
        raise ValueError("kind debe ser input u output")
    with get_connection() as conn:
        if slot_index is None:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(slot_index), 0) FROM panel_module_channels
                WHERE module_id = ? AND kind = ?
                """,
                (module_id, kind),
            ).fetchone()
            slot_index = int(row[0]) + 1
        cur = conn.execute(
            """
            INSERT INTO panel_module_channels
            (module_id, kind, slot_index, label, channel_name, address, open_cmd, close_cmd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (module_id, kind, slot_index, label, channel_name, address, open_cmd, close_cmd),
        )
        cid = int(cur.lastrowid)
        conn.commit()
    return cid


def update_channel(
    channel_id: int,
    *,
    slot_index: Optional[int] = None,
    label: Any = ...,
    channel_name: Any = ...,
    address: Optional[int] = None,
    open_cmd: Any = ...,
    close_cmd: Any = ...,
    pulse_limit: Any = ...,
) -> None:
    ensure_panel_modules_schema()
    fields: List[str] = []
    vals: List[Any] = []
    if slot_index is not None:
        fields.append("slot_index = ?")
        vals.append(slot_index)
    if label is not ...:
        fields.append("label = ?")
        vals.append(label)
    if channel_name is not ...:
        fields.append("channel_name = ?")
        vals.append(channel_name)
    if address is not None:
        fields.append("address = ?")
        vals.append(address)
    if open_cmd is not ...:
        fields.append("open_cmd = ?")
        vals.append(open_cmd)
    if close_cmd is not ...:
        fields.append("close_cmd = ?")
        vals.append(close_cmd)
    if pulse_limit is not ...:
        fields.append("pulse_limit = ?")
        vals.append(pulse_limit)
    if not fields:
        return
    vals.append(channel_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE panel_module_channels SET {', '.join(fields)} WHERE id = ?", vals)
        conn.commit()


def increment_channel_pulse_count(channel_id: int) -> int:
    """Incrementa contador de pulsaciones físicas (solo canales input)."""
    ensure_panel_modules_schema()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE panel_module_channels
            SET pulse_count = COALESCE(pulse_count, 0) + 1
            WHERE id = ? AND kind = 'input'
            """,
            (channel_id,),
        )
        row = conn.execute(
            "SELECT pulse_count FROM panel_module_channels WHERE id = ? AND kind = 'input'",
            (channel_id,),
        ).fetchone()
        conn.commit()
        return int(row[0]) if row else 0


def reset_channel_pulse_count(channel_id: int) -> bool:
    """Reinicia contador tras mantenimiento (solo canales input)."""
    ensure_panel_modules_schema()
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE panel_module_channels
            SET pulse_count = 0
            WHERE id = ? AND kind = 'input'
            """,
            (channel_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_channel(channel_id: int) -> bool:
    ensure_panel_modules_schema()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM panel_module_channels WHERE id = ?", (channel_id,))
        conn.commit()
        return cur.rowcount > 0


def set_bulk_command(module_id: int, kind: str, address: int, value: int) -> None:
    ensure_panel_modules_schema()
    if kind not in ("all_on", "all_off"):
        raise ValueError("kind debe ser all_on o all_off")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO panel_module_bulk (module_id, kind, address, value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(module_id, kind) DO UPDATE SET
                address = excluded.address,
                value = excluded.value
            """,
            (module_id, kind, address, value),
        )
        conn.commit()


def seed_default_modules_if_empty() -> None:
    """Tres placas ETD8A12 con mapa clásico 12+12 y all on/off en registro base."""
    ensure_panel_modules_schema()
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM panel_modules").fetchone()[0]
        if n > 0:
            return
        defaults = [
            ("Placa 1 — Central", "192.168.1.101", 5000, 1, 1),
            ("Placa 2 — Puerta Calle", "192.168.1.102", 5000, 1, 2),
            ("Placa 3 — Puerta Oficina", "192.168.1.103", 5000, 1, 3),
        ]
        for name, host, port, slave, so in defaults:
            cur = conn.execute(
                """
                INSERT INTO panel_modules (name, host, port, slave_id, sort_order, bitmask_address, relation_register)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, host, port, slave, so, DEFAULT_REG_OUTPUT_BITS, 0x00FA),
            )
            mid = int(cur.lastrowid)
            for i in range(12):
                slot = i + 1
                conn.execute(
                    """
                    INSERT INTO panel_module_channels
                    (module_id, kind, slot_index, label, channel_name, address, open_cmd, close_cmd)
                    VALUES (?, 'input', ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        mid,
                        slot,
                        format_channel_label("input", mid, slot),
                        _default_channel_name(mid, "input", slot),
                        DEFAULT_REG_INPUT_START + i,
                    ),
                )
            for i in range(12):
                slot = i + 1
                conn.execute(
                    """
                    INSERT INTO panel_module_channels
                    (module_id, kind, slot_index, label, channel_name, address, open_cmd, close_cmd)
                    VALUES (?, 'output', ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        mid,
                        slot,
                        format_channel_label("output", mid, slot),
                        _default_channel_name(mid, "output", slot),
                        DEFAULT_REG_OUTPUT_START + i,
                    ),
                )
            conn.execute(
                "INSERT INTO panel_module_bulk (module_id, kind, address, value) VALUES (?, 'all_on', ?, ?)",
                (mid, DEFAULT_REG_OUTPUT_START, DEFAULT_CMD_OPEN_ALL),
            )
            conn.execute(
                "INSERT INTO panel_module_bulk (module_id, kind, address, value) VALUES (?, 'all_off', ?, ?)",
                (mid, DEFAULT_REG_OUTPUT_START, DEFAULT_CMD_CLOSE_ALL),
            )
        conn.commit()
