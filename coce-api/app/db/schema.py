"""Esquema SQLite COCE central."""
from __future__ import annotations

from app.db.session import get_connection


def ensure_schema() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS coce_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS branches (
                id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 8000,
                use_https INTEGER NOT NULL DEFAULT 0,
                tablet_user TEXT NOT NULL,
                tablet_password_enc TEXT NOT NULL,
                panel_user TEXT,
                panel_password_enc TEXT,
                estado TEXT NOT NULL DEFAULT 'operativo',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                branch_id TEXT,
                branch_nombre TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                detail TEXT,
                ip_address TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_branch ON audit_logs(branch_id);
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);

            CREATE TABLE IF NOT EXISTS coce_messages (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                actor_username TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                urgent INTEGER NOT NULL DEFAULT 0,
                branch_id TEXT NOT NULL,
                branch_nombre TEXT NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivered_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_coce_messages_created ON coce_messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_coce_messages_branch ON coce_messages(branch_id);
            CREATE INDEX IF NOT EXISTS idx_coce_messages_status ON coce_messages(delivery_status);
            """
        )
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(branches)").fetchall()
        }
        if "ingest_token_enc" not in cols:
            conn.execute(
                "ALTER TABLE branches ADD COLUMN ingest_token_enc TEXT"
            )
        conn.commit()
