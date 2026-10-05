# COCE API — servidor central

API FastAPI + SQLite para el **Centro de Operaciones**: usuarios administradores COCE, registro de sucursales, credenciales cifradas, proxy hacia cada PC de oficina y **auditoría** de acciones (las sucursales no pueden alterar estos registros).

## Arranque rápido

```bash
cd coce-api
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # ajustar COCE_JWT_SECRET y COCE_SECRETS_KEY en producción
python -m app.main
```

Por defecto escucha en **http://0.0.0.0:9000**.

## Primer usuario

1. Con BD vacía: `POST /api/coce/auth/register` con `username` + `password` (mín. 8 caracteres).
2. Si ya hay usuarios: cabecera `X-Coce-Setup-Token` = valor de `COCE_SETUP_TOKEN` en `.env`.
3. Login: `POST /api/coce/auth/login` → JWT.

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/coce/auth/register` | Alta usuario COCE |
| POST | `/api/coce/auth/login` | JWT sesión |
| GET | `/api/coce/auth/me` | Usuario actual |
| GET/POST | `/api/coce/branches` | Listar / crear sucursales |
| GET/PUT/DELETE | `/api/coce/branches/{id}` | CRUD sucursal |
| GET | `/api/coce/branches/{id}/snapshot` | Estado remoto (modos + placas) |
| POST | `/api/coce/branches/{id}/set-mode` | Activar modo (auditoría) |
| GET | `/api/coce/audit` | Histórico acciones administrativas |

Todas las rutas salvo `register`/`login` requieren `Authorization: Bearer <token>`.

## Base de datos

Archivo por defecto: `coce-api/data/coce.db`

Tablas:

- `coce_users` — administradores COCE
- `branches` — sucursales (contraseñas tablet/panel **cifradas** con Fernet)
- `audit_logs` — acciones (`auth.login`, `branch.create`, `branch.set_mode`, …)

## Variables de entorno

Ver `.env.example`. Imprescindibles en producción:

- `COCE_JWT_SECRET`
- `COCE_SECRETS_KEY` (generar con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `COCE_CORS_ORIGINS` — URL del dashboard COCE

## Dashboard

En `coce-dashboard` define `VITE_COCE_API_URL=http://localhost:9000` (o usa el proxy de Vite en dev).

## Arquitectura

```text
coce-dashboard  →  coce-api (SQLite + auditoría)
                        ↓ HTTP (solo servidor)
                   backend sucursal (/api/v1, /api/panel)
                        ↓ Modbus
                   placas ETD8A12
```

El COCE **nunca** debe abrir Modbus a las placas; solo el backend de cada oficina.
