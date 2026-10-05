# COCE — Dashboard (POC)

Aplicación **React + Vite + TypeScript** para el **Centro de Control**. Los datos de sucursales y credenciales viven en **`coce-api`** (servidor central); este front solo guarda el **JWT de sesión** en `sessionStorage`.

## Requisitos

1. **coce-api** en marcha (puerto 9000 por defecto).
2. Copiar `.env.example` → `.env` con `VITE_COCE_API_URL`.

## Arranque

```bash
# Terminal 1 — API central
cd coce-api
pip install -r requirements.txt
python -m app.main

# Terminal 2 — Dashboard
cd coce-dashboard
npm install
cp .env.example .env
npm run dev
```

Abre **http://localhost:5174** → pantalla de login COCE → registrar primer usuario si la BD está vacía.

## Funcionalidad

| Acción | Origen |
|--------|--------|
| Login / registro COCE | `coce-api` `/api/coce/auth/*` |
| CRUD sucursales | `coce-api` `/api/coce/branches` |
| Modo activo / cambio modo / placas | `coce-api` proxy → backend de cada oficina |
| Auditoría | `coce-api` `/api/coce/audit` |

Ya **no** se usa `localStorage` para sucursales (`src/storage/sucursales.ts` queda obsoleto).

## CORS y proxy

En desarrollo, `vite.config.ts` puede hacer proxy de `/api/coce` al puerto 9000. En producción, servir el dashboard y la API bajo políticas CORS definidas en `COCE_CORS_ORIGINS`.

## Build

```bash
npm run build
```

Salida en `dist/`. Definir `VITE_COCE_API_URL` en el build apuntando al servidor COCE de producción.
