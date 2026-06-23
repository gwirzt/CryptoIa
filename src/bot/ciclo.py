"""
src/bot/ciclo.py — Ciclo principal del bot de trading
Lógica: obtener mercado → consultar IA con contexto completo → ejecutar decisión
"""
import logging
import time
from datetime import datetime

from config import (
    SIMBOLO, TEMPORALIDAD, CAPITAL_INICIAL,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    TRAILING_STOP_ACTIVACION_PCT, TRAILING_STOP_PROTECCION_PCT,
    INTERVALO_MINUTOS,
)
from src.mercado.datos import obtener_velas, resumen_indicadores
from src.ia.agente import consultar_ia
from src.trading.posicion import (
    obtener_posicion, calcular_pnl, abrir_posicion,
    cerrar_posicion, incrementar_ciclos,
)
from src.trading.ejecutor import ejecutar_compra, ejecutar_venta

logger = logging.getLogger(__name__)


def ejecutar_ciclo() -> dict:
    """
    Ejecuta un ciclo completo del bot.
    Retorna un dict con el resultado del ciclo.
    """
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{'='*60}")
    logger.info(f"CICLO {ahora} | {SIMBOLO} {TEMPORALIDAD}")
    logger.info(f"{'='*60}")

    resultado = {
        "timestamp":  ahora,
        "simbolo":    SIMBOLO,
        "accion":     "ESPERAR",
        "precio":     None,
        "pnl_pct":    None,
        "razon":      "",
        "error":      None,
    }

    try:
        # ── 1. Obtener datos de mercado ────────────────────────────────────────
        df = obtener_velas(limite=100)
        indicadores = resumen_indicadores(df)
        precio_actual = indicadores["precio"]
        resultado["precio"] = precio_actual
        logger.info(f"Precio: ${precio_actual:,.2f} | RSI: {indicadores['rsi']} | MACD hist: {indicadores['macd_hist']:.4f}")

        # ── 2. Obtener posición actual ─────────────────────────────────────────
        posicion = obtener_posicion(SIMBOLO)
        posicion_con_pnl = None

        if posicion:
            posicion_con_pnl = calcular_pnl(posicion, precio_actual)
            resultado["pnl_pct"] = posicion_con_pnl["pnl_pct"]
            signo = "+" if posicion_con_pnl["pnl_pct"] >= 0 else ""
            logger.info(
                f"Posición abierta @ ${posicion['precio_compra']:,.2f} | "
                f"P&L: {signo}{posicion_con_pnl['pnl_pct']:.2f}% ({signo}${posicion_con_pnl['pnl_usdt']:.2f})"
            )

            # ── 2a. Stop-Loss determinista (sin IA) ───────────────────────────
            if posicion_con_pnl["pnl_pct"] <= -STOP_LOSS_PCT:
                logger.warning(f"STOP-LOSS activado: {posicion_con_pnl['pnl_pct']:.2f}% <= -{STOP_LOSS_PCT}%")
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Stop-Loss automático ({posicion_con_pnl['pnl_pct']:.2f}%)", 100
                    )
                    resultado["accion"] = "VENTA_STOP_LOSS"
                    resultado["razon"]  = f"Stop-Loss: {pnl['pnl_pct']:.2f}%"
                return resultado

            # ── 2b. Take-Profit determinista (sin IA) ─────────────────────────
            if posicion_con_pnl["pnl_pct"] >= TAKE_PROFIT_PCT:
                logger.info(f"TAKE-PROFIT activado: {posicion_con_pnl['pnl_pct']:.2f}% >= {TAKE_PROFIT_PCT}%")
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Take-Profit automático ({posicion_con_pnl['pnl_pct']:.2f}%)", 100
                    )
                    resultado["accion"] = "VENTA_TAKE_PROFIT"
                    resultado["razon"]  = f"Take-Profit: {pnl['pnl_pct']:.2f}%"
                return resultado

            # Incrementar ciclos en posición
            incrementar_ciclos(posicion["id"])

        # ── 3. Consultar IA con contexto completo ─────────────────────────────
        decision_ia = consultar_ia(
            indicadores=indicadores,
            posicion=posicion_con_pnl,
            simbolo=SIMBOLO,
            temporalidad=TEMPORALIDAD,
        )
        logger.info(
            f"IA → {decision_ia['decision']} ({decision_ia['confianza']}%) | {decision_ia['razon']}"
        )

        # ── 4. Ejecutar decisión ───────────────────────────────────────────────
        decision = decision_ia["decision"]
        confianza = decision_ia["confianza"]
        razon = decision_ia["razon"]

        if decision == "COMPRAR" and posicion is None:
            # Solo comprar si la IA tiene suficiente confianza
            if confianza >= 55:
                orden = ejecutar_compra(precio_actual, CAPITAL_INICIAL)
                if orden["ok"]:
                    abrir_posicion(
                        SIMBOLO,
                        orden["precio"],
                        orden["cantidad"],
                        orden["capital"],
                        orden.get("orden_id"),
                    )
                    resultado["accion"] = "COMPRA"
                    resultado["razon"]  = razon
                    logger.info(f"✅ COMPRA ejecutada @ ${orden['precio']:,.2f}")
            else:
                logger.info(f"Confianza insuficiente para comprar: {confianza}% < 55%")
                resultado["razon"] = f"Confianza baja: {confianza}%"

        elif decision == "VENDER" and posicion is not None:
            orden = ejecutar_venta(posicion, precio_actual)
            if orden["ok"]:
                pnl = cerrar_posicion(posicion, orden["precio"], razon, confianza, orden.get("orden_id"))
                resultado["accion"] = "VENTA_IA"
                resultado["pnl_pct"] = pnl["pnl_pct"]
                resultado["razon"]   = razon
                signo = "+" if pnl["pnl_pct"] >= 0 else ""
                logger.info(f"✅ VENTA ejecutada @ ${orden['precio']:,.2f} | P&L: {signo}{pnl['pnl_pct']:.2f}%")

        else:
            resultado["accion"] = "ESPERAR"
            resultado["razon"]  = razon
            logger.info(f"→ ESPERAR | {razon}")

    except Exception as e:
        logger.error(f"Error en ciclo: {e}", exc_info=True)
        resultado["error"] = str(e)

    return resultado


def iniciar_bot():
    """Inicia el bot en bucle continuo."""
    from src.trading.posicion import inicializar_db
    
    logger.info("🤖 CryptoIA Bot v2 iniciando...")
    logger.info(f"   Símbolo:      {SIMBOLO}")
    logger.info(f"   Temporalidad: {TEMPORALIDAD}")
    logger.info(f"   Intervalo:    {INTERVALO_MINUTOS} minutos")
    logger.info(f"   Capital:      ${CAPITAL_INICIAL:,.2f}")
    logger.info(f"   Stop-Loss:    {STOP_LOSS_PCT}%")
    logger.info(f"   Take-Profit:  {TAKE_PROFIT_PCT}%")
    
    inicializar_db()
    
    intervalo_seg = INTERVALO_MINUTOS * 60
    
    while True:
        try:
            resultado = ejecutar_ciclo()
            logger.info(f"Ciclo completado: {resultado['accion']} | Próximo en {INTERVALO_MINUTOS} min")
        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario")
            break
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
        
        time.sleep(intervalo_seg)
