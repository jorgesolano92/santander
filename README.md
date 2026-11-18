# Control de Accesos — Santander / SAIMA SEGURIDAD

Sistema de control de accesos para oficinas del Banco Santander. Lógica de control en Python (FastAPI), 3 módulos ETD8A12 (Modbus TCP/IP), API REST para tablet Android e interfaz web de configuración.

---

## Estructura del repositorio

| Carpeta / archivo | Descripción |
|-------------------|-------------|
| **backend/** | Servicio Python (FastAPI): API REST, SQLite, comunicación con ETD8A12. |
| **frontend/** | Interfaz web de configuración (React + Vite). |
| **deploy/windows/** | Instalación / actualización / arranque al encender (PC sucursal Windows). |
| **deploy/linux/** | Instalación como servicio systemd (Ubuntu/Debian). |
| **coce-dashboard/** | POC dashboard tipo COCE: sucursales, modos y placas vía API del backend. |
| **alcance.md** | Alcance del proyecto (requisitos, 7 modos, 33 actuaciones). |
| **ARQUITECTURA.md** | Arquitectura en capas y tablas SQLite. |
| **API_SPEC.md** | Especificación de la API REST. |
| **MODELO_DATOS.md** | Modelo de datos (tablas, relaciones). |
| **GUIA_SUBTASKS.md** | Guía de subtasks Fase 0. |
| **APROVECHAMIENTO_POC.md** | Qué se reutiliza del software de prueba. |
| **DESARROLLO.md** | Cómo ejecutar backend y frontend en desarrollo. |

---

## Arranque rápido (desarrollo)

1. **Backend:** `cd backend && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt && python run.py`  
   → http://localhost:8000 — Docs: http://localhost:8000/docs  

2. **Frontend:** `cd frontend && npm install && npm run dev`  
   → http://localhost:5173 (las peticiones a `/api` se reenvían al backend).

3. **COCE (POC):** `cd coce-dashboard && npm install && npm run dev`  
   → http://localhost:5174 — conecta a cada sucursal por IP/puerto (ver `coce-dashboard/README.md`).

Ver **DESARROLLO.md** para más detalle.
