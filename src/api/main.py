"""
src/api/main.py — API FastAPI para el dashboard de CryptoIA v2
Inicio: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
"""
import os
import sys
import requests
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Asegurar que el root del proyecto esté en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import SIMBOLO, URL_IA_TAGS, MODELO_IA
from src.mercado.datos import obtener_velas, resumen_indicadores, obtener_precio_actual
from src.trading.posicion import (
    obtener_posicion, calcular_pnl, resumen_operaciones, inicializar_db
)

app = FastAPI(title="CryptoIA v2", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos del dashboard
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard")
if os.path.exists(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")


@app.on_event("startup")
async def startup():
    inicializar_db()


@app.get("/")
async def root():
    """Sirve el dashboard."""
    index_path = os.path.join(DASHBOARD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"mensaje": "CryptoIA v2 API — Dashboard no encontrado"}


@app.get("/health")
async def health():
    """Estado general del sistema."""
    # Verificar Ollama
    ollama_ok = False
    try:
        resp = requests.get(URL_IA_TAGS, timeout=3)
        ollama_ok = resp.status_code == 200
    except Exception:
        pass

    # Verificar si el bot está corriendo (buscar proceso)
    bot_activo = False
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "run_bot.py"],
            capture_output=True, text=True
        )
        bot_activo = result.returncode == 0
    except Exception:
        pass

    return {
        "timestamp": datetime.now().isoformat(),
        "ollama":    "OK" if ollama_ok else "ERROR",
        "modelo":    MODELO_IA,
        "bot":       "ACTIVO" if bot_activo else "INACTIVO",
        "simbolo":   SIMBOLO,
    }


@app.get("/mercado")
async def mercado():
    """Precio actual e indicadores técnicos."""
    try:
        df = obtener_velas(limite=100)
        indicadores = resumen_indicadores(df)
        return {
            "ok": True,
            "timestamp": datetime.now().isoformat(),
            "data": indicadores,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/estado")
async def estado():
    """Posición actual con P&L en tiempo real."""
    try:
        posicion = obtener_posicion(SIMBOLO)
        if posicion is None:
            return {
                "ok": True,
                "en_posicion": False,
                "posicion": None,
            }

        precio_actual = obtener_precio_actual()
        posicion_pnl = calcular_pnl(posicion, precio_actual)

        return {
            "ok": True,
            "en_posicion": True,
            "posicion": {
                "simbolo":        posicion_pnl["simbolo"],
                "precio_compra":  posicion_pnl["precio_compra"],
                "precio_actual":  posicion_pnl["precio_actual"],
                "cantidad":       posicion_pnl["cantidad"],
                "capital_usado":  posicion_pnl["capital_usado"],
                "valor_actual":   posicion_pnl["valor_actual"],
                "pnl_usdt":       posicion_pnl["pnl_usdt"],
                "pnl_pct":        posicion_pnl["pnl_pct"],
                "ciclos":         posicion_pnl["ciclos_en_posicion"],
                "timestamp_compra": str(posicion_pnl["timestamp_compra"]),
            }
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/cartera")
async def cartera():
    """Balance de cartera: USDT disponible + BTC en posición + valor total + variación."""
    try:
        from config import CAPITAL_INICIAL
        posicion = obtener_posicion(SIMBOLO)
        precio_actual = obtener_precio_actual()

        # Calcular P&L acumulado de operaciones cerradas
        ops = resumen_operaciones(SIMBOLO, limite=1000)
        ventas = [o for o in ops if o["tipo"] == "VENTA" and o["pnl_usdt"] is not None]
        pnl_acumulado = sum(o["pnl_usdt"] for o in ventas)

        if posicion:
            posicion_pnl = calcular_pnl(posicion, precio_actual)
            usdt_disponible = 0.0
            btc_cantidad    = posicion["cantidad"]
            btc_valor_usdt  = posicion_pnl["valor_actual"]
            pnl_posicion    = posicion_pnl["pnl_usdt"]
            valor_total     = btc_valor_usdt + pnl_acumulado
        else:
            usdt_disponible = CAPITAL_INICIAL + pnl_acumulado
            btc_cantidad    = 0.0
            btc_valor_usdt  = 0.0
            pnl_posicion    = 0.0
            valor_total     = usdt_disponible

        variacion_total_usdt = valor_total - CAPITAL_INICIAL
        variacion_total_pct  = (variacion_total_usdt / CAPITAL_INICIAL) * 100

        return {
            "ok": True,
            "cartera": {
                "capital_inicial":       CAPITAL_INICIAL,
                "usdt_disponible":       round(usdt_disponible, 2),
                "btc_cantidad":          round(btc_cantidad, 8),
                "btc_valor_usdt":        round(btc_valor_usdt, 2),
                "pnl_posicion_actual":   round(pnl_posicion, 2),
                "pnl_operaciones_cerradas": round(pnl_acumulado, 2),
                "valor_total_usdt":      round(valor_total, 2),
                "variacion_total_usdt":  round(variacion_total_usdt, 2),
                "variacion_total_pct":   round(variacion_total_pct, 4),
                "precio_btc":            precio_actual,
                "en_posicion":          posicion is not None,
            }
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/operaciones")
async def operaciones(limite: int = 20):
    """Historial de operaciones."""
    try:
        ops = resumen_operaciones(SIMBOLO, limite=limite)
        # Calcular estadísticas
        ventas = [o for o in ops if o["tipo"] == "VENTA" and o["pnl_pct"] is not None]
        ganadas = [o for o in ventas if o["pnl_pct"] > 0]
        perdidas = [o for o in ventas if o["pnl_pct"] <= 0]
        pnl_total = sum(o["pnl_usdt"] for o in ventas if o["pnl_usdt"])

        return {
            "ok": True,
            "operaciones": ops,
            "estadisticas": {
                "total_operaciones": len(ventas),
                "ganadas":           len(ganadas),
                "perdidas":          len(perdidas),
                "win_rate":          round(len(ganadas) / len(ventas) * 100, 1) if ventas else 0,
                "pnl_total_usdt":    round(pnl_total, 2),
            }
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
