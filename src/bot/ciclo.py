"""
src/bot/ciclo.py — Ciclo principal del bot de trading
Lógica: obtener mercado → compra determinista → consultar IA → ejecutar decisión
"""
import logging
import time
from datetime import datetime

from config import (
    SIMBOLO, TEMPORALIDAD, CAPITAL_INICIAL,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
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

# Umbral mínimo de confianza para que la IA ejecute una compra
CONFIANZA_MIN_COMPRA = 50

# Compra determinista: RSI en zona de sobreventa + MACD recuperando
RSI_SOBREVENTA      = 38   # RSI por debajo de este valor → zona de oportunidad
RSI_SOBRECOMPRA     = 72   # RSI por encima → no comprar
MACD_HIST_MIN       = -50  # No comprar si el histograma es muy negativo (caída libre)

# Protección de posición: no vender demasiado rápido
CICLOS_MIN_EN_POSICION = 3   # Mínimo de ciclos antes de que la IA pueda vender (21 min)
PNL_MIN_PARA_VENDER_IA = 0.3 # La IA solo puede vender si P&L >= 0.3% (ganancia mínima)
                              # El stop-loss determinista ignora este límite


def _evaluar_compra_determinista(indicadores: dict) -> tuple:
    """
    Evalúa si hay condiciones deterministas para comprar.
    Retorna (bool, str) → (comprar, razon)
    """
    rsi  = indicadores["rsi"]
    hist = indicadores["macd_hist"]
    ema_alcista = indicadores["ema_alcista"]
    cerca_bb_lower = indicadores["cerca_bb_lower"]

    # Condición 1: RSI en sobreventa + MACD recuperando (hist > mínimo)
    if rsi < RSI_SOBREVENTA and hist > MACD_HIST_MIN:
        return True, f"Compra determinista: RSI={rsi} (sobreventa) + MACD hist={hist:.2f}"

    # Condición 2: Precio cerca del piso de Bollinger + RSI no sobrecomprado
    if cerca_bb_lower and rsi < 55 and hist > MACD_HIST_MIN:
        return True, f"Compra determinista: precio en BB inferior + RSI={rsi}"

    # Condición 3: EMAs alcistas + MACD cruce alcista reciente
    if ema_alcista and indicadores.get("macd_cruce_alcista") and rsi < RSI_SOBRECOMPRA:
        return True, f"Compra determinista: EMAs alcistas + cruce MACD alcista + RSI={rsi}"

    return False, ""


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
        "timestamp": ahora,
        "simbolo":   SIMBOLO,
        "accion":    "ESPERAR",
        "precio":    None,
        "pnl_pct":   None,
        "razon":     "",
        "error":     None,
    }

    try:
        # ── 1. Obtener datos de mercado ────────────────────────────────────────
        df = obtener_velas(limite=100)
        indicadores = resumen_indicadores(df)
        precio_actual = indicadores["precio"]
        resultado["precio"] = precio_actual
        logger.info(
            f"Precio: ${precio_actual:,.2f} | RSI: {indicadores['rsi']} | "
            f"MACD hist: {indicadores['macd_hist']:.4f} | "
            f"Tendencia: {'▲' if indicadores['ema_alcista'] else '▼' if indicadores['ema_bajista'] else '↔'}"
        )

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

            # ── 2a. Stop-Loss determinista ────────────────────────────────────
            if posicion_con_pnl["pnl_pct"] <= -STOP_LOSS_PCT:
                logger.warning(f"⛔ STOP-LOSS: {posicion_con_pnl['pnl_pct']:.2f}% <= -{STOP_LOSS_PCT}%")
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Stop-Loss automático ({posicion_con_pnl['pnl_pct']:.2f}%)", 100
                    )
                    resultado["accion"] = "VENTA_STOP_LOSS"
                    resultado["razon"]  = f"Stop-Loss: {pnl['pnl_pct']:.2f}%"
                return resultado

            # ── 2b. Take-Profit determinista ──────────────────────────────────
            if posicion_con_pnl["pnl_pct"] >= TAKE_PROFIT_PCT:
                logger.info(f"🎯 TAKE-PROFIT: {posicion_con_pnl['pnl_pct']:.2f}% >= {TAKE_PROFIT_PCT}%")
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

        # ── 3. Compra determinista (sin IA) ───────────────────────────────────
        if posicion is None:
            comprar_det, razon_det = _evaluar_compra_determinista(indicadores)
            if comprar_det:
                logger.info(f"📊 {razon_det}")
                orden = ejecutar_compra(precio_actual, CAPITAL_INICIAL)
                if orden["ok"]:
                    abrir_posicion(SIMBOLO, orden["precio"], orden["cantidad"],
                                   orden["capital"], orden.get("orden_id"))
                    resultado["accion"] = "COMPRA_DETERMINISTA"
                    resultado["razon"]  = razon_det
                    logger.info(f"✅ COMPRA DETERMINISTA @ ${orden['precio']:,.2f}")
                return resultado

        # ── 4. Consultar IA con contexto completo ─────────────────────────────
        decision_ia = consultar_ia(
            indicadores=indicadores,
            posicion=posicion_con_pnl,
            simbolo=SIMBOLO,
            temporalidad=TEMPORALIDAD,
        )
        logger.info(
            f"IA → {decision_ia['decision']} ({decision_ia['confianza']}%) | {decision_ia['razon']}"
        )

        decision  = decision_ia["decision"]
        confianza = decision_ia["confianza"]
        razon     = decision_ia["razon"]

        # ── 5. Ejecutar decisión de la IA ─────────────────────────────────────
        if decision == "COMPRAR" and posicion is None:
            rsi = indicadores["rsi"]
            # No comprar si RSI sobrecomprado
            if rsi >= RSI_SOBRECOMPRA:
                logger.info(f"⚠️  IA dice COMPRAR pero RSI={rsi} sobrecomprado → ESPERAR")
                resultado["razon"] = f"RSI sobrecomprado ({rsi}), ignorando señal de compra"
            elif confianza >= CONFIANZA_MIN_COMPRA:
                orden = ejecutar_compra(precio_actual, CAPITAL_INICIAL)
                if orden["ok"]:
                    abrir_posicion(SIMBOLO, orden["precio"], orden["cantidad"],
                                   orden["capital"], orden.get("orden_id"))
                    resultado["accion"] = "COMPRA_IA"
                    resultado["razon"]  = razon
                    logger.info(f"✅ COMPRA IA @ ${orden['precio']:,.2f} (confianza: {confianza}%)")
            else:
                logger.info(f"Confianza insuficiente: {confianza}% < {CONFIANZA_MIN_COMPRA}%")
                resultado["razon"] = f"Confianza baja: {confianza}%"

        elif decision == "VENDER" and posicion is not None:
            ciclos_actual = posicion_con_pnl["ciclos_en_posicion"]
            pnl_actual    = posicion_con_pnl["pnl_pct"]

            # Protección 1: mínimo de ciclos en posición antes de vender
            if ciclos_actual < CICLOS_MIN_EN_POSICION:
                logger.info(
                    f"⏳ IA dice VENDER pero solo {ciclos_actual} ciclos en posición "
                    f"(mínimo {CICLOS_MIN_EN_POSICION}) → ESPERAR"
                )
                resultado["accion"] = "ESPERAR"
                resultado["razon"]  = f"Muy pronto para vender ({ciclos_actual} ciclos)"

            # Protección 2: no vender con pérdida pequeña (el stop-loss ya cubre pérdidas grandes)
            elif pnl_actual < PNL_MIN_PARA_VENDER_IA:
                logger.info(
                    f"⚠️  IA dice VENDER pero P&L={pnl_actual:.2f}% < {PNL_MIN_PARA_VENDER_IA}% mínimo → ESPERAR"
                )
                resultado["accion"] = "ESPERAR"
                resultado["razon"]  = f"P&L insuficiente para vender ({pnl_actual:.2f}%)"

            else:
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(posicion, orden["precio"], razon, confianza, orden.get("orden_id"))
                    resultado["accion"] = "VENTA_IA"
                    resultado["pnl_pct"] = pnl["pnl_pct"]
                    resultado["razon"]   = razon
                    signo = "+" if pnl["pnl_pct"] >= 0 else ""
                    logger.info(f"✅ VENTA IA @ ${orden['precio']:,.2f} | P&L: {signo}{pnl['pnl_pct']:.2f}%")

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
    logger.info(f"   Símbolo:         {SIMBOLO}")
    logger.info(f"   Temporalidad:    {TEMPORALIDAD}")
    logger.info(f"   Intervalo:       {INTERVALO_MINUTOS} minutos")
    logger.info(f"   Capital:         ${CAPITAL_INICIAL:,.2f}")
    logger.info(f"   Stop-Loss:       {STOP_LOSS_PCT}%")
    logger.info(f"   Take-Profit:     {TAKE_PROFIT_PCT}%")
    logger.info(f"   Confianza mín:   {CONFIANZA_MIN_COMPRA}%")
    logger.info(f"   RSI sobreventa:  < {RSI_SOBREVENTA}")

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
