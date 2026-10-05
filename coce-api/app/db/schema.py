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
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operador'
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
                delivered_at TEXT,
                read_at TEXT,
                read_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_coce_messages_created ON coce_messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_coce_messages_branch ON coce_messages(branch_id);
            CREATE INDEX IF NOT EXISTS idx_coce_messages_status ON coce_messages(delivery_status);

            CREATE TABLE IF NOT EXISTS technicians (
                dni TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                apellidos TEXT NOT NULL DEFAULT '',
                empresa TEXT NOT NULL DEFAULT '',
                valido_hasta TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_technicians_active ON technicians(active);

            CREATE TABLE IF NOT EXISTS software_releases (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                version TEXT NOT NULL,
                changelog TEXT NOT NULL DEFAULT '',
                sha256 TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                original_filename TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'upload',
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_software_releases_kind ON software_releases(kind);
            CREATE INDEX IF NOT EXISTS idx_software_releases_created ON software_releases(created_at);

            CREATE TABLE IF NOT EXISTS software_deployments (
                id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                branch_id TEXT NOT NULL,
                branch_nombre TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (release_id) REFERENCES software_releases(id)
            );

            CREATE INDEX IF NOT EXISTS idx_software_deployments_release ON software_deployments(release_id);
            CREATE INDEX IF NOT EXISTS idx_software_deployments_branch ON software_deployments(branch_id);
            CREATE INDEX IF NOT EXISTS idx_software_deployments_status ON software_deployments(status);

            CREATE TABLE IF NOT EXISTS coce_alerts (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                branch_id TEXT NOT NULL,
                branch_nombre TEXT NOT NULL DEFAULT '',
                alert_type TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                message TEXT NOT NULL DEFAULT '',
                detail_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_coce_alerts_created ON coce_alerts(created_at);
            CREATE INDEX IF NOT EXISTS idx_coce_alerts_active ON coce_alerts(active);
            CREATE INDEX IF NOT EXISTS idx_coce_alerts_branch ON coce_alerts(branch_id);
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
        msg_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(coce_messages)").fetchall()
        }
        if "read_at" not in msg_cols:
            conn.execute("ALTER TABLE coce_messages ADD COLUMN read_at TEXT")
        if "read_by" not in msg_cols:
            conn.execute("ALTER TABLE coce_messages ADD COLUMN read_by TEXT")
        user_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(coce_users)").fetchall()
        }
        if "role" not in user_cols:
            conn.execute(
                "ALTER TABLE coce_users ADD COLUMN role TEXT NOT NULL DEFAULT 'operador'"
            )
            # Usuarios previos tenían acceso total → admin.
            conn.execute("UPDATE coce_users SET role = 'admin'")
        conn.commit()
