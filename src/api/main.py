"""
src/api/main.py — API REST FastAPI para CryptoIA

Expone los datos del bot de trading para consumo desde el dashboard Node.js.
Lee de PostgreSQL — completamente independiente del motor de trading.

Ejecutar:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

Documentación automática:
    http://192.168.1.8:8000/docs      (Swagger UI)
    http://192.168.1.8:8000/redoc     (ReDoc)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import time

from src.api.routers import estado, ciclos, operaciones, billetera, mercado

# ==============================================================================
# APP
# ==============================================================================
app = FastAPI(
    title="CryptoIA API",
    description=(
        "API REST para el bot de trading CryptoIA.\n\n"
        "Lee datos de PostgreSQL y los expone para el dashboard.\n"
        "El motor de trading corre independientemente en background."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — permite que el dashboard Node.js consuma la API desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # En producción, restringir al dominio del dashboard
    allow_credentials=True,
    allow_methods=["GET"],     # Solo lectura — el bot escribe, la API solo lee
    allow_headers=["*"],
)

# ==============================================================================
# ROUTERS
# ==============================================================================
app.include_router(estado.router,      prefix="/estado",      tags=["Estado"])
app.include_router(ciclos.router,      prefix="/ciclos",      tags=["Ciclos"])
app.include_router(operaciones.router, prefix="/operaciones", tags=["Operaciones"])
app.include_router(billetera.router,   prefix="/billetera",   tags=["Billetera"])
app.include_router(mercado.router,     prefix="/mercado",     tags=["Mercado"])


# ==============================================================================
# ENDPOINTS RAÍZ
# ==============================================================================

@app.get("/", tags=["Root"])
def root():
    """Endpoint raíz — verifica que la API está corriendo."""
    return {
        "api":     "CryptoIA",
        "version": "1.0.0",
        "status":  "online",
        "docs":    "/docs",
        "endpoints": [
            "/estado",
            "/ciclos",
            "/ciclos/ultimo",
            "/operaciones",
            "/billetera",
            "/billetera/rendimiento",
            "/mercado/actual",
            "/mercado/agentes",
        ]
    }


@app.get("/health", tags=["Root"])
def health():
    """Health check — para monitoreo y systemd."""
    try:
        from src.trading.base_datos import verificar_conexion
        ok_db, msg_db = verificar_conexion()
    except Exception as e:
        ok_db, msg_db = False, str(e)

    return {
        "status":    "ok",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "database":  {"ok": ok_db, "mensaje": msg_db},
    }


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard():
    """
    Dashboard web — interfaz visual del bot de trading.
    Acceder desde el navegador: http://192.168.1.8:8000/dashboard
    """
    # Buscar el HTML relativo a este archivo
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard", "index.html"
    )
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard no encontrado</h1><p>Verificar que existe src/dashboard/index.html</p>",
            status_code=404
        )
