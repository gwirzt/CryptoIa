"""
src/trading/binance_trader.py — Cliente Binance para trading real y testnet

Maneja todas las operaciones reales con Binance via ccxt:
  - Compra/venta de mercado (market orders)
  - Consulta de saldos reales
  - Precio actual spot
  - Historial de órdenes

Modos de operación:
  BINANCE_TESTNET=true  → usa testnet.binance.vision (dinero ficticio)
  BINANCE_TESTNET=false → usa binance.com (¡dinero real!)
  MODO_REAL=false       → simula sin ejecutar (dry-run)
  MODO_REAL=true        → ejecuta órdenes reales

Uso:
    from src.trading.binance_trader import BinanceTrader
    trader = BinanceTrader()
    ok, saldo = trader.obtener_saldo()
    ok, orden = trader.comprar(usdt_amount=1000)
    ok, orden = trader.vender_todo()
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BinanceTrader:
    """
    Cliente de trading para Binance (real o testnet).
    Encapsula todas las operaciones de compra/venta via ccxt.
    """

    def __init__(self, api_key: str = "", secret: str = "",
                 testnet: bool = True, modo_real: bool = False,
                 simbolo: str = "BTC/USDT"):
        """
        Inicializa el cliente Binance.

        Args:
            api_key:   API Key de Binance (real o testnet)
            secret:    Secret de Binance (real o testnet)
            testnet:   True = testnet.binance.vision, False = binance.com
            modo_real: True = ejecuta órdenes reales, False = dry-run (simula)
            simbolo:   Par de trading (ej: "BTC/USDT")
        """
        self.api_key   = api_key
        self.secret    = secret
        self.testnet   = testnet
        self.modo_real = modo_real
        self.simbolo   = simbolo
        self.exchange  = None
        self._inicializado = False

        # Extraer monedas del símbolo (BTC/USDT → base=BTC, quote=USDT)
        partes = simbolo.split("/")
        self.moneda_base  = partes[0] if len(partes) == 2 else "BTC"   # BTC
        self.moneda_quote = partes[1] if len(partes) == 2 else "USDT"  # USDT

    def inicializar(self) -> tuple[bool, str]:
        """
        Inicializa la conexión con Binance via ccxt.
        Retorna (ok: bool, mensaje: str)
        """
        try:
            import ccxt
        except ImportError:
            return False, "ccxt no instalado. Ejecutar: pip install ccxt"

        try:
            config = {
                "apiKey": self.api_key,
                "secret": self.secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                    "adjustForTimeDifference": True,
                },
            }

            if self.testnet:
                # Binance Testnet
                config["urls"] = {
                    "api": {
                        "public":  "https://testnet.binance.vision/api",
                        "private": "https://testnet.binance.vision/api",
                    }
                }
                self.exchange = ccxt.binance(config)
                self.exchange.set_sandbox_mode(True)
                entorno = "TESTNET"
            else:
                # Binance producción
                self.exchange = ccxt.binance(config)
                entorno = "PRODUCCIÓN"

            # Cargar mercados
            self.exchange.load_markets()
            self._inicializado = True

            modo_str = "REAL" if self.modo_real else "DRY-RUN (simulación)"
            msg = f"Binance {entorno} conectado — Modo: {modo_str}"
            logger.info(msg)
            return True, msg

        except Exception as e:
            msg = f"Error conectando a Binance: {e}"
            logger.error(msg)
            return False, msg

    def _verificar_init(self) -> tuple[bool, str]:
        """Verifica que el cliente esté inicializado."""
        if not self._inicializado or self.exchange is None:
            ok, msg = self.inicializar()
            if not ok:
                return False, msg
        return True, "OK"

    # =========================================================================
    # CONSULTAS (no ejecutan órdenes)
    # =========================================================================

    def obtener_saldo(self) -> tuple[bool, dict]:
        """
        Obtiene el saldo real de la cuenta Binance.
        Retorna (ok, {"usdt": float, "btc": float, "total_usdt": float})
        """
        ok, msg = self._verificar_init()
        if not ok:
            return False, {"error": msg}

        try:
            balance = self.exchange.fetch_balance()
            usdt = float(balance.get(self.moneda_quote, {}).get("free", 0))
            btc  = float(balance.get(self.moneda_base,  {}).get("free", 0))

            # Obtener precio actual para calcular valor total
            precio = self._obtener_precio_raw()
            total_usdt = usdt + (btc * precio) if precio else usdt

            return True, {
                "usdt":        round(usdt, 4),
                "btc":         round(btc, 8),
                "total_usdt":  round(total_usdt, 2),
                "precio_btc":  round(precio, 2) if precio else None,
            }
        except Exception as e:
            logger.error(f"Error obteniendo saldo: {e}")
            return False, {"error": str(e)}

    def _obtener_precio_raw(self) -> Optional[float]:
        """Obtiene el precio actual del par (uso interno)."""
        try:
            ticker = self.exchange.fetch_ticker(self.simbolo)
            return float(ticker.get("last") or ticker.get("close") or 0)
        except Exception:
            return None

    def obtener_precio(self) -> tuple[bool, float]:
        """
        Obtiene el precio actual del par de trading.
        Retorna (ok, precio_float)
        """
        ok, msg = self._verificar_init()
        if not ok:
            return False, 0.0

        try:
            ticker = self.exchange.fetch_ticker(self.simbolo)
            precio = float(ticker.get("last") or ticker.get("close") or 0)
            return True, precio
        except Exception as e:
            logger.error(f"Error obteniendo precio: {e}")
            return False, 0.0

    def obtener_ordenes_recientes(self, limit: int = 10) -> tuple[bool, list]:
        """
        Obtiene las últimas N órdenes ejecutadas.
        Retorna (ok, lista_de_ordenes)
        """
        ok, msg = self._verificar_init()
        if not ok:
            return False, []

        try:
            ordenes = self.exchange.fetch_orders(self.simbolo, limit=limit)
            resultado = []
            for o in ordenes:
                resultado.append({
                    "id":        o.get("id"),
                    "tipo":      o.get("side", "").upper(),   # BUY / SELL
                    "estado":    o.get("status"),
                    "precio":    o.get("average") or o.get("price"),
                    "cantidad":  o.get("filled"),
                    "costo":     o.get("cost"),
                    "timestamp": o.get("datetime"),
                })
            return True, resultado
        except Exception as e:
            logger.error(f"Error obteniendo órdenes: {e}")
            return False, []

    # =========================================================================
    # ÓRDENES (ejecutan operaciones reales si modo_real=True)
    # =========================================================================

    def comprar(self, usdt_amount: float) -> tuple[bool, dict]:
        """
        Ejecuta una orden de compra de mercado.

        Args:
            usdt_amount: Cantidad en USDT a invertir (ej: 10000)

        Retorna:
            (ok, {"orden_id", "btc_comprado", "precio_promedio", "costo_usdt", "comision"})

        Si modo_real=False → simula la compra sin ejecutar nada en Binance.
        """
        ok, msg = self._verificar_init()
        if not ok:
            return False, {"error": msg}

        if usdt_amount < 10:
            return False, {"error": f"Monto mínimo de compra: $10 USDT (recibido: ${usdt_amount})"}

        # Obtener precio actual para calcular cantidad de BTC
        ok_p, precio = self.obtener_precio()
        if not ok_p or precio <= 0:
            return False, {"error": "No se pudo obtener el precio actual"}

        btc_estimado = usdt_amount / precio

        if not self.modo_real:
            # ── DRY-RUN: simular sin ejecutar ──
            logger.info(f"[DRY-RUN] COMPRA simulada: ${usdt_amount:.2f} USDT → ~{btc_estimado:.6f} BTC @ ${precio:,.2f}")
            return True, {
                "orden_id":        "DRY-RUN",
                "btc_comprado":    round(btc_estimado * 0.999, 8),  # simular 0.1% comisión
                "precio_promedio": precio,
                "costo_usdt":      usdt_amount,
                "comision_usdt":   round(usdt_amount * 0.001, 4),
                "modo":            "DRY-RUN",
            }

        # ── REAL: ejecutar orden en Binance ──
        try:
            # Binance acepta órdenes de compra por monto en USDT (quoteOrderQty)
            orden = self.exchange.create_order(
                symbol    = self.simbolo,
                type      = "market",
                side      = "buy",
                amount    = None,
                params    = {"quoteOrderQty": usdt_amount},
            )

            btc_comprado    = float(orden.get("filled", 0))
            precio_promedio = float(orden.get("average") or orden.get("price") or precio)
            costo           = float(orden.get("cost", usdt_amount))
            comision        = float(orden.get("fee", {}).get("cost", 0)) if orden.get("fee") else 0

            logger.info(
                f"COMPRA REAL ejecutada: {btc_comprado:.6f} BTC @ ${precio_promedio:,.2f} "
                f"(costo: ${costo:.2f}, comisión: ${comision:.4f})"
            )

            return True, {
                "orden_id":        orden.get("id"),
                "btc_comprado":    round(btc_comprado, 8),
                "precio_promedio": round(precio_promedio, 2),
                "costo_usdt":      round(costo, 2),
                "comision_usdt":   round(comision, 4),
                "modo":            "REAL",
            }

        except Exception as e:
            logger.error(f"Error ejecutando compra: {e}")
            return False, {"error": str(e)}

    def vender_todo(self) -> tuple[bool, dict]:
        """
        Vende TODO el saldo disponible de la moneda base (BTC).

        Retorna:
            (ok, {"orden_id", "btc_vendido", "precio_promedio", "usdt_obtenido", "comision"})

        Si modo_real=False → simula la venta sin ejecutar nada en Binance.
        """
        ok, msg = self._verificar_init()
        if not ok:
            return False, {"error": msg}

        # Obtener saldo real de BTC
        ok_s, saldo = self.obtener_saldo()
        if not ok_s:
            return False, {"error": f"No se pudo obtener saldo: {saldo.get('error')}"}

        btc_disponible = saldo.get("btc", 0)

        if btc_disponible < 0.00001:
            return False, {"error": f"Saldo BTC insuficiente: {btc_disponible:.8f} BTC"}

        # Obtener precio actual
        ok_p, precio = self.obtener_precio()
        if not ok_p or precio <= 0:
            return False, {"error": "No se pudo obtener el precio actual"}

        usdt_estimado = btc_disponible * precio

        if not self.modo_real:
            # ── DRY-RUN: simular sin ejecutar ──
            logger.info(f"[DRY-RUN] VENTA simulada: {btc_disponible:.6f} BTC → ~${usdt_estimado:.2f} USDT @ ${precio:,.2f}")
            return True, {
                "orden_id":        "DRY-RUN",
                "btc_vendido":     btc_disponible,
                "precio_promedio": precio,
                "usdt_obtenido":   round(usdt_estimado * 0.999, 2),  # simular 0.1% comisión
                "comision_usdt":   round(usdt_estimado * 0.001, 4),
                "modo":            "DRY-RUN",
            }

        # ── REAL: ejecutar orden en Binance ──
        try:
            # Redondear al step size del mercado para evitar errores
            mercado = self.exchange.market(self.simbolo)
            step    = float(mercado.get("precision", {}).get("amount", 0.00001))
            if step > 0:
                btc_a_vender = (btc_disponible // step) * step
            else:
                btc_a_vender = btc_disponible

            orden = self.exchange.create_order(
                symbol = self.simbolo,
                type   = "market",
                side   = "sell",
                amount = btc_a_vender,
            )

            btc_vendido     = float(orden.get("filled", btc_a_vender))
            precio_promedio = float(orden.get("average") or orden.get("price") or precio)
            usdt_obtenido   = float(orden.get("cost", usdt_estimado))
            comision        = float(orden.get("fee", {}).get("cost", 0)) if orden.get("fee") else 0

            logger.info(
                f"VENTA REAL ejecutada: {btc_vendido:.6f} BTC @ ${precio_promedio:,.2f} "
                f"(obtenido: ${usdt_obtenido:.2f}, comisión: ${comision:.4f})"
            )

            return True, {
                "orden_id":        orden.get("id"),
                "btc_vendido":     round(btc_vendido, 8),
                "precio_promedio": round(precio_promedio, 2),
                "usdt_obtenido":   round(usdt_obtenido, 2),
                "comision_usdt":   round(comision, 4),
                "modo":            "REAL",
            }

        except Exception as e:
            logger.error(f"Error ejecutando venta: {e}")
            return False, {"error": str(e)}

    def estado(self) -> dict:
        """
        Retorna un resumen del estado del trader.
        """
        return {
            "testnet":    self.testnet,
            "modo_real":  self.modo_real,
            "simbolo":    self.simbolo,
            "inicializado": self._inicializado,
            "entorno":    "TESTNET" if self.testnet else "PRODUCCIÓN",
            "modo":       "REAL" if self.modo_real else "DRY-RUN",
        }


# ==============================================================================
# Factory function — crea el trader desde config.py
# ==============================================================================

def crear_trader() -> BinanceTrader:
    """
    Crea y retorna un BinanceTrader configurado desde las variables de entorno.
    Uso:
        from src.trading.binance_trader import crear_trader
        trader = crear_trader()
        trader.inicializar()
    """
    from config import (
        BINANCE_API_KEY, BINANCE_SECRET,
        BINANCE_TESTNET, MODO_REAL, SIMBOLO
    )
    return BinanceTrader(
        api_key   = BINANCE_API_KEY,
        secret    = BINANCE_SECRET,
        testnet   = BINANCE_TESTNET,
        modo_real = MODO_REAL,
        simbolo   = SIMBOLO,
    )
