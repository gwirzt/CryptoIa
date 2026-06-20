"""
src/api/routers/cuenta.py — Estado real de la cuenta Binance (Testnet o Producción)

GET /cuenta/testnet  → saldo real, precio, órdenes recientes, configuración activa
GET /cuenta/config   → configuración de trading activa (SL, TP, trailing, etc.)

Conecta directamente a Binance via BinanceTrader.
Cachea la respuesta 30 segundos para no saturar la API de Binance.
"""
import time
from fastapi import APIRouter

router = APIRouter()

# Cache simple en memoria
_cache = {"data": None, "ts": 0}
_cache_config = {"data": None, "ts": 0}
CACHE_TTL = 30  # segundos


@router.get("/testnet")
def estado_cuenta_testnet():
    """
    Retorna el estado real de la cuenta Binance (Testnet o Producción según .env).
    Incluye: saldo USDT/BTC, precio actual, valor total, rendimiento,
    comisiones acumuladas, trailing stop activo y últimas órdenes.
    Cachea la respuesta 30 segundos.
    """
    global _cache

    # Devolver caché si es reciente
    if _cache["data"] and (time.time() - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    try:
        from config import (
            BINANCE_API_KEY, BINANCE_SECRET,
            BINANCE_TESTNET, MODO_REAL, SIMBOLO,
            CAPITAL_INICIAL,
            STOP_LOSS_PCT, TAKE_PROFIT_PCT,
            TRAILING_STOP_ACTIVACION_PCT, TRAILING_STOP_PROTECCION_PCT,
            VENTA_DEFENSIVA_PNL_MIN_PCT,
            INTERVALO_MINUTOS, TEMPORALIDAD,
        )
        from src.trading.binance_trader import BinanceTrader

        # Verificar credenciales
        if not BINANCE_API_KEY or BINANCE_API_KEY == "TU_BINANCE_API_KEY_AQUI":
            return {
                "ok": False,
                "error": "BINANCE_API_KEY no configurada en .env",
                "entorno": "TESTNET" if BINANCE_TESTNET else "PRODUCCIÓN",
            }

        trader = BinanceTrader(
            api_key   = BINANCE_API_KEY,
            secret    = BINANCE_SECRET,
            testnet   = BINANCE_TESTNET,
            modo_real = MODO_REAL,
            simbolo   = SIMBOLO,
        )

        ok_init, msg_init = trader.inicializar()
        if not ok_init:
            return {
                "ok": False,
                "error": msg_init,
                "entorno": "TESTNET" if BINANCE_TESTNET else "PRODUCCIÓN",
            }

        # Precio actual
        ok_p, precio = trader.obtener_precio()
        precio = precio if ok_p and precio > 0 else None

        # Saldo
        ok_s, saldo = trader.obtener_saldo()
        usdt = saldo.get("usdt", 0.0) if ok_s else 0.0
        btc  = saldo.get("btc",  0.0) if ok_s else 0.0
        total_usdt = (usdt + btc * precio) if precio else usdt

        rendimiento_pct = ((total_usdt - CAPITAL_INICIAL) / CAPITAL_INICIAL * 100) if CAPITAL_INICIAL > 0 else 0

        # Últimas órdenes
        ok_o, ordenes_raw = trader.obtener_ordenes_recientes(limit=10)
        ordenes = []
        if ok_o and ordenes_raw:
            for o in ordenes_raw:
                precio_o = o.get("precio") or 0
                cant     = o.get("cantidad") or 0
                costo    = o.get("costo") or (float(cant) * float(precio_o) if cant and precio_o else 0)
                ordenes.append({
                    "tipo":       str(o.get("tipo", "?")),
                    "estado":     str(o.get("estado", "?")),
                    "precio":     float(precio_o) if precio_o else None,
                    "cantidad_btc": float(cant) if cant else None,
                    "total_usdt": float(costo) if costo else None,
                    "timestamp":  str(o.get("timestamp", ""))[:19].replace("T", " "),
                })

        resultado = {
            "ok":           True,
            "timestamp":    time.strftime("%Y-%m-%d %H:%M:%S"),
            "entorno":      "TESTNET" if BINANCE_TESTNET else "PRODUCCIÓN",
            "modo":         "REAL" if MODO_REAL else "DRY-RUN",
            "simbolo":      SIMBOLO,
            "capital_inicial": CAPITAL_INICIAL,
            "cuenta": {
                "usdt":             round(usdt, 4),
                "btc":              round(btc, 8),
                "precio_btc":       round(precio, 2) if precio else None,
                "valor_total_usdt": round(total_usdt, 2),
                "rendimiento_pct":  round(rendimiento_pct, 4),
                "saldo_ok":         ok_s,
            },
            "config": {
                "stop_loss_pct":               STOP_LOSS_PCT,
                "take_profit_pct":             TAKE_PROFIT_PCT,
                "trailing_activacion_pct":     TRAILING_STOP_ACTIVACION_PCT,
                "trailing_proteccion_pct":     TRAILING_STOP_PROTECCION_PCT,
                "venta_defensiva_pnl_min_pct": VENTA_DEFENSIVA_PNL_MIN_PCT,
                "intervalo_minutos":           INTERVALO_MINUTOS,
                "temporalidad":                TEMPORALIDAD,
            },
            "ordenes_recientes": ordenes,
        }

        _cache["data"] = resultado
        _cache["ts"]   = time.time()
        return resultado

    except Exception as e:
        return {
            "ok":    False,
            "error": str(e),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


@router.get("/config")
def configuracion_activa():
    """
    Retorna la configuración de trading activa (sin conectar a Binance).
    Útil para mostrar en el dashboard sin latencia.
    """
    global _cache_config

    if _cache_config["data"] and (time.time() - _cache_config["ts"]) < 60:
        return _cache_config["data"]

    try:
        from config import (
            BINANCE_TESTNET, MODO_REAL, SIMBOLO,
            CAPITAL_INICIAL, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
            TRAILING_STOP_ACTIVACION_PCT, TRAILING_STOP_PROTECCION_PCT,
            VENTA_DEFENSIVA_PNL_MIN_PCT,
            INTERVALO_MINUTOS, TEMPORALIDAD, CICLOS_MAX_EN_POSICION,
        )

        resultado = {
            "ok": True,
            "entorno":      "TESTNET" if BINANCE_TESTNET else "PRODUCCIÓN",
            "modo":         "REAL" if MODO_REAL else "DRY-RUN",
            "simbolo":      SIMBOLO,
            "capital_inicial":             CAPITAL_INICIAL,
            "stop_loss_pct":               STOP_LOSS_PCT,
            "take_profit_pct":             TAKE_PROFIT_PCT,
            "trailing_activacion_pct":     TRAILING_STOP_ACTIVACION_PCT,
            "trailing_proteccion_pct":     TRAILING_STOP_PROTECCION_PCT,
            "venta_defensiva_pnl_min_pct": VENTA_DEFENSIVA_PNL_MIN_PCT,
            "intervalo_minutos":           INTERVALO_MINUTOS,
            "temporalidad":                TEMPORALIDAD,
            "ciclos_max_en_posicion":      CICLOS_MAX_EN_POSICION,
        }

        _cache_config["data"] = resultado
        _cache_config["ts"]   = time.time()
        return resultado

    except Exception as e:
        return {"ok": False, "error": str(e)}
