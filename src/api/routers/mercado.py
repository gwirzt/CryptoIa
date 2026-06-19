"""
src/api/routers/mercado.py — Datos de mercado en tiempo real

GET /mercado/actual  → precio BTC actual + indicadores técnicos
GET /mercado/agentes → estado de los 3 Ollamas
"""
from fastapi import APIRouter
import requests
import time

router = APIRouter()


@router.get("/actual")
def mercado_actual():
    """
    Obtiene el precio actual de BTC y los indicadores técnicos en tiempo real.
    Llama directamente a Binance via ccxt.
    """
    try:
        from src.mercado.binance_client import obtener_datos_completos
        indicadores, reporte = obtener_datos_completos()
        return {
            "ok":      True,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "precio_btc":       float(indicadores["precio"]),
            "rsi":              float(indicadores["rsi"]),
            "rsi_zona":         indicadores["rsi_zona"],
            "macd_cruce":       indicadores["macd_cruce"],
            "bb_posicion":      indicadores["bb_posicion"],
            "tendencia_ema":    indicadores["tendencia_ema"],
            "volumen_relativo": float(indicadores["volumen_relativo"]),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/agentes")
def estado_agentes():
    """
    Verifica el estado de los 3 agentes Ollama (online/offline + modelos cargados).
    """
    from config import SERVIDOR_IA, PUERTO_GPU0, PUERTO_GPU1, PUERTO_GPU2
    from config import MODELO_GPU0, MODELO_GPU1, MODELO_GPU2

    agentes_config = [
        {"nombre": "Técnico",     "puerto": PUERTO_GPU0, "modelo": MODELO_GPU0, "rol": "Análisis técnico (RSI, MACD, Bollinger)"},
        {"nombre": "Fundamental", "puerto": PUERTO_GPU1, "modelo": MODELO_GPU1, "rol": "Análisis de noticias y sentimiento"},
        {"nombre": "Riesgo",      "puerto": PUERTO_GPU2, "modelo": MODELO_GPU2, "rol": "Decisión final y gestión de riesgo"},
    ]

    resultados = []
    for ag in agentes_config:
        inicio = time.time()
        try:
            resp = requests.get(
                f"http://{SERVIDOR_IA}:{ag['puerto']}/api/tags",
                timeout=5
            )
            ok = resp.status_code == 200
            data = resp.json() if ok else {}
            modelos = [m["name"] for m in data.get("models", [])]
            modelo_activo = ag["modelo"] in modelos
        except Exception:
            ok = False
            modelos = []
            modelo_activo = False

        latencia = round((time.time() - inicio) * 1000)
        resultados.append({
            "nombre":        ag["nombre"],
            "rol":           ag["rol"],
            "puerto":        ag["puerto"],
            "modelo":        ag["modelo"],
            "online":        ok,
            "modelo_activo": modelo_activo,
            "modelos":       modelos,
            "latencia_ms":   latencia,
        })

    todos_ok = all(r["online"] for r in resultados)
    return {
        "servidor":     f"192.168.1.8",
        "todos_online": todos_ok,
        "timestamp":    time.strftime("%Y-%m-%d %H:%M:%S"),
        "agentes":      resultados,
    }
