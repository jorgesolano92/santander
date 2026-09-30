"""Actualiza tablet_config en SQLite: P1=.80 / P2=.70 Panphone + defaults actuales."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "control_accesos.db"


def main() -> None:
    from app.data.tablet_config_defaults import get_builtin_default_tablet_config

    builtin = get_builtin_default_tablet_config()
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT config_json FROM tablet_config WHERE id=1")
    row = cur.fetchone()
    cfg = json.loads(row[0]) if row and row[0] else {}
    doors = list(cfg.get("doors") or [])
    while len(doors) < 2:
        doors.append({})
    doors[0] = builtin["doors"][0]
    doors[1] = builtin["doors"][1]
    cfg["doors"] = doors
    if "tabletCall" in builtin:
        cfg["tabletCall"] = builtin["tabletCall"]

    payload = json.dumps(cfg, ensure_ascii=False)
    rev = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE tablet_config SET config_json=?, revision=?, updated_at=? WHERE id=1",
        (payload, rev, now),
    )
    conn.commit()
    conn.close()
    print("tablet_config: P1=.80 p1, P2=.70 p2 OK")


if __name__ == "__main__":
    main()
