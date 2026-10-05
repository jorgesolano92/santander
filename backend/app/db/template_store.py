import sqlite3
import json
from app.db.session import get_connection

def _init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS template_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            config_json TEXT NOT NULL
        )
    ''')
    # Insert default if not exists
    c.execute('INSERT OR IGNORE INTO template_config (id, config_json) VALUES (1, "{}")')
    conn.commit()
    conn.close()

def get_template_config() -> dict:
    _init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT config_json FROM template_config WHERE id=1')
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return {}
    return {}

def set_template_config(config: dict):
    _init_db()
    conn = get_connection()
    c = conn.cursor()
    config_str = json.dumps(config)
    c.execute('UPDATE template_config SET config_json=? WHERE id=1', (config_str,))
    conn.commit()
    conn.close()
