"""
src/trading/ejecutor.py — Ejecuta órdenes en Binance (real o paper trading)
"""
import logging
from config import MODO_REAL, CAPITAL_INICIAL, SIMBOLO, BINANCE_API_KEY, BINANCE_SECRET, BINANCE_TESTNET

logger = logging.getLogger(__name__)


def ejecutar_compra(precio: float, capital: float) -> dict:
    """
    Ejecuta una orden de compra.
    En MODO_REAL=False simula la orden (paper trading).
    Retorna dict con: precio, cantidad, capital, orden_id, modo
    """
    cantidad = capital / precio

    if not MODO_REAL:
        logger.info(f"[PAPER] COMPRA simulada: {cantidad:.6f} @ ${precio:,.2f} = ${capital:.2f}")
        return {
            "precio":    precio,
            "cantidad":  cantidad,
            "capital":   capital,
            "orden_id":  f"PAPER_{int(precio)}",
            "modo":      "paper",
            "ok":        True,
        }

    # Orden real en Binance
    try:
        import ccxt
        exchange_class = getattr(ccxt, "binance")
        params = {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET,
            "enableRateLimit": True,
        }
        if BINANCE_TESTNET:
            params["options"] = {"defaultType": "spot"}
            params["urls"] = {"api": {"public": "https://testnet.binance.vision/api",
                                       "private": "https://testnet.binance.vision/api"}}
        exchange = exchange_class(params)

        simbolo_ccxt = SIMBOLO  # "BTC/USDT"
        orden = exchange.create_market_buy_order(simbolo_ccxt, cantidad)
        precio_real = float(orden.get("average", precio))
        cantidad_real = float(orden.get("filled", cantidad))

        logger.info(f"[REAL] COMPRA ejecutada: {cantidad_real:.6f} @ ${precio_real:,.2f} | ID: {orden['id']}")
        return {
            "precio":    precio_real,
            "cantidad":  cantidad_real,
            "capital":   precio_real * cantidad_real,
            "orden_id":  str(orden["id"]),
            "modo":      "real",
            "ok":        True,
        }
    except Exception as e:
        logger.error(f"Error ejecutando compra real: {e}")
        return {"ok": False, "error": str(e)}


def ejecutar_venta(posicion: dict, precio: float) -> dict:
    """
    Ejecuta una orden de venta.
    En MODO_REAL=False simula la orden (paper trading).
    """
    cantidad = posicion["cantidad"]

    if not MODO_REAL:
        logger.info(f"[PAPER] VENTA simulada: {cantidad:.6f} @ ${precio:,.2f} = ${cantidad * precio:.2f}")
        return {
            "precio":    precio,
            "cantidad":  cantidad,
            "orden_id":  f"PAPER_{int(precio)}",
            "modo":      "paper",
            "ok":        True,
        }

    # Orden real en Binance
    try:
        import ccxt
        exchange_class = getattr(ccxt, "binance")
        params = {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET,
            "enableRateLimit": True,
        }
        if BINANCE_TESTNET:
            params["options"] = {"defaultType": "spot"}
            params["urls"] = {"api": {"public": "https://testnet.binance.vision/api",
                                       "private": "https://testnet.binance.vision/api"}}
        exchange = exchange_class(params)

        simbolo_ccxt = SIMBOLO
        orden = exchange.create_market_sell_order(simbolo_ccxt, cantidad)
        precio_real = float(orden.get("average", precio))
        cantidad_real = float(orden.get("filled", cantidad))

        logger.info(f"[REAL] VENTA ejecutada: {cantidad_real:.6f} @ ${precio_real:,.2f} | ID: {orden['id']}")
        return {
            "precio":    precio_real,
            "cantidad":  cantidad_real,
            "orden_id":  str(orden["id"]),
            "modo":      "real",
            "ok":        True,
        }
    except Exception as e:
        logger.error(f"Error ejecutando venta real: {e}")
        return {"ok": False, "error": str(e)}
