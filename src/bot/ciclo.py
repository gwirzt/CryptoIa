"""
src/bot/ciclo.py — Ciclo principal del bot de trading v4
Mejoras:
  - Trailing Stop real (con precio_maximo en DB)
  - Cooldown post stop-loss
  - GUARDIA DURA: nunca vender por debajo del precio de compra + comisiones
  - TIMEOUT: fuerza salida si lleva demasiados ciclos atrapado
  - DCA: Dollar Cost Averaging — divide el capital y promedia el precio de entrada
"""
import logging
import time
from datetime import datetime

from config import (
    SIMBOLO, TEMPORALIDAD, CAPITAL_INICIAL,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    INTERVALO_MINUTOS,
    TRAILING_STOP_ACTIVACION_PCT, TRAILING_STOP_PROTECCION_PCT,
    CICLOS_MIN_EN_POSICION, CICLOS_MAX_EN_POSICION,
    PNL_MIN_PARA_VENDER_IA,
    CONFIANZA_VENTA_FORZADA, PNL_MAX_PERDIDA_IA,
    MACD_HIST_MIN_COMPRA, COOLDOWN_POST_STOPLOSS,
    COMISION_TOTAL_PCT,
    DCA_HABILITADO, DCA_NIVELES, DCA_BAJADA_PCT, DCA_CAPITAL_POR_NIVEL,
    TAKE_PROFIT_RAPIDO_PCT, CICLOS_MIN_TAKE_PROFIT,
    SOFT_STOPLOSS_PCT, CICLOS_MIN_SOFT_STOPLOSS,
)
from src.mercado.datos import obtener_velas, resumen_indicadores
from src.ia.agente import consultar_ia
from src.trading.posicion import (
    obtener_posicion, calcular_pnl, abrir_posicion,
    cerrar_posicion, incrementar_ciclos,
    actualizar_precio_maximo, registrar_ultimo_stoploss,
    ciclos_desde_ultimo_stoploss, registrar_ciclo,
    registrar_compra_dca,
)
from src.trading.ejecutor import ejecutar_compra, ejecutar_venta

logger = logging.getLogger(__name__)

# Umbral minimo de confianza para que la IA ejecute una compra
CONFIANZA_MIN_COMPRA = 50

# Compra determinista: RSI en zona de sobreventa + MACD recuperando
RSI_SOBREVENTA  = 38
RSI_SOBRECOMPRA = 72


def _precio_minimo_venta(precio_compra: float) -> float:
    """Precio minimo para no perder dinero (incluye comisiones)."""
    return precio_compra * (1 + COMISION_TOTAL_PCT / 100)


def _precio_bajo_equilibrio(precio_actual: float, precio_compra: float) -> bool:
    """True si el precio actual esta por debajo del punto de equilibrio."""
    return precio_actual < _precio_minimo_venta(precio_compra)


def _evaluar_compra_determinista(indicadores: dict) -> tuple:
    """Evalua condiciones deterministas para comprar. Retorna (bool, str)."""
    rsi  = indicadores["rsi"]
    hist = indicadores["macd_hist"]
    ema_alcista    = indicadores["ema_alcista"]
    cerca_bb_lower = indicadores["cerca_bb_lower"]

    if rsi < RSI_SOBREVENTA and hist > MACD_HIST_MIN_COMPRA:
        return True, f"Compra determinista: RSI={rsi} (sobreventa) + MACD hist={hist:.2f}"
    if cerca_bb_lower and rsi < 55 and hist > MACD_HIST_MIN_COMPRA:
        return True, f"Compra determinista: precio en BB inferior + RSI={rsi}"
    if ema_alcista and indicadores.get("macd_cruce_alcista") and rsi < RSI_SOBRECOMPRA:
        return True, f"Compra determinista: EMAs alcistas + cruce MACD alcista + RSI={rsi}"
    return False, ""


def _evaluar_dca(posicion: dict, precio_actual: float) -> tuple:
    """
    Evalua si corresponde hacer una compra DCA.
    Retorna (bool, str) -> (hacer_dca, razon)
    """
    if not DCA_HABILITADO:
        return False, ""

    nivel_actual = posicion.get("nivel_dca", 0)
    if nivel_actual >= DCA_NIVELES - 1:
        return False, "DCA: todos los niveles agotados"

    precio_ultimo_dca = posicion.get("precio_dca_ultimo") or posicion["precio_compra"]
    caida_pct = ((precio_ultimo_dca - precio_actual) / precio_ultimo_dca) * 100

    if caida_pct >= DCA_BAJADA_PCT:
        return True, (
            f"DCA nivel {nivel_actual + 1}/{DCA_NIVELES - 1}: "
            f"precio bajo {caida_pct:.2f}% desde ultima compra ${precio_ultimo_dca:,.2f}"
        )
    return False, ""


def ejecutar_ciclo() -> dict:
    """Ejecuta un ciclo completo del bot."""
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
        # 1. Obtener datos de mercado
        df = obtener_velas(limite=100)
        indicadores = resumen_indicadores(df)
        precio_actual = indicadores["precio"]
        rsi_actual    = indicadores["rsi"]
        macd_hist     = indicadores["macd_hist"]
        resultado["precio"] = precio_actual
        logger.info(
            f"Precio: ${precio_actual:,.2f} | RSI: {rsi_actual} | "
            f"MACD hist: {macd_hist:.4f} | "
            f"Tendencia: {chr(9650) if indicadores['ema_alcista'] else chr(9660) if indicadores['ema_bajista'] else chr(8596)}"
        )

        # 2. Obtener posicion actual
        posicion = obtener_posicion(SIMBOLO)
        posicion_con_pnl = None
        precio_compra_pos = None

        if posicion:
            posicion_con_pnl  = calcular_pnl(posicion, precio_actual)
            precio_compra_pos = posicion["precio_compra"]
            resultado["pnl_pct"] = posicion_con_pnl["pnl_pct"]
            signo = "+" if posicion_con_pnl["pnl_pct"] >= 0 else ""

            precio_min_venta = _precio_minimo_venta(precio_compra_pos)
            bajo_equilibrio  = _precio_bajo_equilibrio(precio_actual, precio_compra_pos)
            ciclos_actual    = posicion_con_pnl["ciclos_en_posicion"]

            logger.info(
                f"Posicion abierta @ ${posicion['precio_compra']:,.2f} | "
                f"Maximo: ${posicion['precio_maximo']:,.2f} | "
                f"P&L: {signo}{posicion_con_pnl['pnl_pct']:.2f}% ({signo}${posicion_con_pnl['pnl_usdt']:.2f}) | "
                f"Min. venta: ${precio_min_venta:,.2f} | "
                f"Ciclos: {ciclos_actual}/{CICLOS_MAX_EN_POSICION} | "
                f"{'BAJO EQUILIBRIO' if bajo_equilibrio else 'Sobre equilibrio'}"
            )

            # Actualizar precio maximo
            actualizar_precio_maximo(posicion["id"], precio_actual)
            precio_maximo = max(posicion["precio_maximo"], precio_actual)

            # 2a. Stop-Loss determinista (unica excepcion que vende con perdida)
            if posicion_con_pnl["pnl_pct"] <= -STOP_LOSS_PCT:
                logger.warning(f"STOP-LOSS: {posicion_con_pnl['pnl_pct']:.2f}% <= -{STOP_LOSS_PCT}%")
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Stop-Loss automatico ({posicion_con_pnl['pnl_pct']:.2f}%)", 100
                    )
                    registrar_ultimo_stoploss(SIMBOLO)
                    resultado["accion"] = "VENTA_STOP_LOSS"
                    resultado["razon"]  = f"Stop-Loss: {pnl['pnl_pct']:.2f}%"
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "VENTA_STOP_LOSS",
                        precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                        resultado["razon"], rsi_actual, macd_hist,
                    )
                return resultado

            # 2a+. TAKE-PROFIT RAPIDO: capturar ganancias antes del timeout
            #       Si P&L >= 0.5% y los indicadores sugieren que el precio puede caer
            if (posicion_con_pnl["pnl_pct"] >= TAKE_PROFIT_RAPIDO_PCT and
                    ciclos_actual >= CICLOS_MIN_TAKE_PROFIT):
                rsi_alto = rsi_actual > 60
                macd_bajista = macd_hist < 0
                muchos_ciclos = ciclos_actual >= CICLOS_MAX_EN_POSICION // 2
                ema_bajista = indicadores.get("ema_bajista", False)

                if rsi_alto or macd_bajista or muchos_ciclos or ema_bajista:
                    motivo_tp = []
                    if rsi_alto:      motivo_tp.append(f"RSI={rsi_actual}")
                    if macd_bajista:  motivo_tp.append(f"MACD={macd_hist:.2f}")
                    if muchos_ciclos: motivo_tp.append(f"ciclos={ciclos_actual}")
                    if ema_bajista:   motivo_tp.append("EMA bajista")

                    logger.info(
                        f"TAKE-PROFIT RAPIDO: P&L={posicion_con_pnl['pnl_pct']:.2f}% >= "
                        f"{TAKE_PROFIT_RAPIDO_PCT}% | Señales: {', '.join(motivo_tp)}"
                    )
                    orden = ejecutar_venta(posicion, precio_actual)
                    if orden["ok"]:
                        pnl = cerrar_posicion(
                            posicion, orden["precio"],
                            f"Take-Profit rapido ({posicion_con_pnl['pnl_pct']:.2f}%) - {', '.join(motivo_tp)}", 100
                        )
                        resultado["accion"] = "VENTA_TP_RAPIDO"
                        resultado["razon"]  = f"TP rapido: {pnl['pnl_pct']:.2f}% ({', '.join(motivo_tp)})"
                        registrar_ciclo(
                            SIMBOLO, precio_actual, "VENTA_TP_RAPIDO",
                            precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                            resultado["razon"], rsi_actual, macd_hist,
                        )
                    return resultado

            # 2a++. SOFT STOP-LOSS: cortar pérdidas antes del stop-loss duro
            #        Si P&L <= -0.8% y los indicadores confirman tendencia bajista
            if (posicion_con_pnl["pnl_pct"] <= -SOFT_STOPLOSS_PCT and
                    ciclos_actual >= CICLOS_MIN_SOFT_STOPLOSS):
                macd_bajista = macd_hist < 0
                rsi_bajo = rsi_actual < 45
                ema_bajista = indicadores.get("ema_bajista", False)

                # Necesita al menos 2 señales bajistas para activarse
                senales_bajistas = sum([macd_bajista, rsi_bajo, ema_bajista])
                if senales_bajistas >= 2:
                    motivo_sl = []
                    if macd_bajista: motivo_sl.append(f"MACD={macd_hist:.2f}")
                    if rsi_bajo:     motivo_sl.append(f"RSI={rsi_actual}")
                    if ema_bajista:  motivo_sl.append("EMA bajista")

                    logger.warning(
                        f"SOFT STOP-LOSS: P&L={posicion_con_pnl['pnl_pct']:.2f}% <= "
                        f"-{SOFT_STOPLOSS_PCT}% | Señales bajistas: {', '.join(motivo_sl)}"
                    )
                    orden = ejecutar_venta(posicion, precio_actual)
                    if orden["ok"]:
                        pnl = cerrar_posicion(
                            posicion, orden["precio"],
                            f"Soft stop-loss ({posicion_con_pnl['pnl_pct']:.2f}%) - {', '.join(motivo_sl)}", 100
                        )
                        registrar_ultimo_stoploss(SIMBOLO)
                        resultado["accion"] = "VENTA_SOFT_SL"
                        resultado["razon"]  = f"Soft SL: {pnl['pnl_pct']:.2f}% ({', '.join(motivo_sl)})"
                        registrar_ciclo(
                            SIMBOLO, precio_actual, "VENTA_SOFT_SL",
                            precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                            resultado["razon"], rsi_actual, macd_hist,
                        )
                    return resultado

            # 2b. TIMEOUT: demasiados ciclos atrapado -> forzar salida
            if ciclos_actual >= CICLOS_MAX_EN_POSICION:
                logger.warning(
                    f"TIMEOUT: {ciclos_actual} ciclos en posicion >= maximo {CICLOS_MAX_EN_POSICION}. "
                    f"Forzando venta para liberar capital. P&L: {signo}{posicion_con_pnl['pnl_pct']:.2f}%"
                )
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Timeout: {ciclos_actual} ciclos en posicion (max={CICLOS_MAX_EN_POSICION})", 100
                    )
                    resultado["accion"] = "VENTA_TIMEOUT"
                    resultado["razon"]  = f"Timeout {ciclos_actual} ciclos: {pnl['pnl_pct']:.2f}%"
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "VENTA_TIMEOUT",
                        precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                        resultado["razon"], rsi_actual, macd_hist,
                    )
                return resultado

            # 2c. Trailing Stop
            ganancia_desde_compra = ((precio_maximo - posicion["precio_compra"]) / posicion["precio_compra"]) * 100
            caida_desde_maximo    = ((precio_maximo - precio_actual) / precio_maximo) * 100

            if (ganancia_desde_compra >= TRAILING_STOP_ACTIVACION_PCT and
                    caida_desde_maximo >= TRAILING_STOP_PROTECCION_PCT):
                if bajo_equilibrio:
                    logger.info(
                        f"TRAILING STOP activado pero precio ${precio_actual:,.2f} < "
                        f"minimo rentable ${precio_min_venta:,.2f} -> ESPERAR recuperacion"
                    )
                    resultado["accion"] = "ESPERAR"
                    resultado["razon"]  = (
                        f"Trailing Stop bloqueado: precio bajo equilibrio "
                        f"(actual=${precio_actual:,.2f} < min=${precio_min_venta:,.2f})"
                    )
                    incrementar_ciclos(posicion["id"])
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "ESPERAR",
                        precio_compra_pos, posicion_con_pnl["pnl_pct"], posicion_con_pnl["pnl_usdt"],
                        resultado["razon"], rsi_actual, macd_hist,
                    )
                    return resultado

                logger.info(
                    f"TRAILING STOP: maximo=${precio_maximo:,.2f} (+{ganancia_desde_compra:.2f}%) "
                    f"-> cayo {caida_desde_maximo:.2f}% desde el maximo"
                )
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Trailing Stop (max=${precio_maximo:,.2f}, caida={caida_desde_maximo:.2f}%)", 100
                    )
                    resultado["accion"] = "VENTA_TRAILING_STOP"
                    resultado["razon"]  = f"Trailing Stop: {pnl['pnl_pct']:.2f}%"
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "VENTA_TRAILING_STOP",
                        precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                        resultado["razon"], rsi_actual, macd_hist,
                    )
                return resultado

            # 2d. Take-Profit determinista
            if posicion_con_pnl["pnl_pct"] >= TAKE_PROFIT_PCT:
                logger.info(f"TAKE-PROFIT: {posicion_con_pnl['pnl_pct']:.2f}% >= {TAKE_PROFIT_PCT}%")
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(
                        posicion, orden["precio"],
                        f"Take-Profit automatico ({posicion_con_pnl['pnl_pct']:.2f}%)", 100
                    )
                    resultado["accion"] = "VENTA_TAKE_PROFIT"
                    resultado["razon"]  = f"Take-Profit: {pnl['pnl_pct']:.2f}%"
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "VENTA_TAKE_PROFIT",
                        precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                        resultado["razon"], rsi_actual, macd_hist,
                    )
                return resultado

            # 2e. DCA: evaluar si corresponde comprar mas
            hacer_dca, razon_dca = _evaluar_dca(posicion, precio_actual)
            if hacer_dca:
                logger.info(f"DCA: {razon_dca}")
                orden = ejecutar_compra(precio_actual, DCA_CAPITAL_POR_NIVEL)
                if orden["ok"]:
                    registrar_compra_dca(posicion["id"], orden["precio"], orden["cantidad"], orden["capital"])
                    resultado["accion"] = "COMPRA_DCA"
                    resultado["razon"]  = razon_dca
                    logger.info(
                        f"COMPRA DCA @ ${orden['precio']:,.2f} | "
                        f"Capital: ${orden['capital']:.2f} | {razon_dca}"
                    )
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "COMPRA_DCA",
                        precio_compra_pos, posicion_con_pnl["pnl_pct"], posicion_con_pnl["pnl_usdt"],
                        razon_dca, rsi_actual, macd_hist,
                    )
                    return resultado

            # Incrementar ciclos en posicion
            incrementar_ciclos(posicion["id"])

        # 3. Compra determinista (sin IA, sin posicion)
        if posicion is None:
            ciclos_post_sl = ciclos_desde_ultimo_stoploss(SIMBOLO)
            if ciclos_post_sl < COOLDOWN_POST_STOPLOSS:
                logger.info(
                    f"Cooldown post stop-loss: {ciclos_post_sl}/{COOLDOWN_POST_STOPLOSS} ciclos -> ESPERAR"
                )
                resultado["razon"] = f"Cooldown post stop-loss ({ciclos_post_sl}/{COOLDOWN_POST_STOPLOSS} ciclos)"
                registrar_ciclo(
                    SIMBOLO, precio_actual, "ESPERAR", None, None, None,
                    resultado["razon"], rsi_actual, macd_hist,
                )
                return resultado

            # Capital de compra: si DCA habilitado, usar capital por nivel; si no, capital total
            capital_compra = DCA_CAPITAL_POR_NIVEL if DCA_HABILITADO else CAPITAL_INICIAL

            comprar_det, razon_det = _evaluar_compra_determinista(indicadores)
            if comprar_det:
                logger.info(f"{razon_det}")
                orden = ejecutar_compra(precio_actual, capital_compra)
                if orden["ok"]:
                    abrir_posicion(SIMBOLO, orden["precio"], orden["cantidad"],
                                   orden["capital"], orden.get("orden_id"))
                    resultado["accion"] = "COMPRA_DETERMINISTA"
                    resultado["razon"]  = razon_det
                    logger.info(f"COMPRA DETERMINISTA @ ${orden['precio']:,.2f} | Capital: ${orden['capital']:.2f}")
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "COMPRA_DETERMINISTA",
                        orden["precio"], 0.0, 0.0,
                        razon_det, rsi_actual, macd_hist,
                    )
                return resultado

        # 4. Consultar IA
        decision_ia = consultar_ia(
            indicadores=indicadores,
            posicion=posicion_con_pnl,
            simbolo=SIMBOLO,
            temporalidad=TEMPORALIDAD,
        )
        logger.info(
            f"IA -> {decision_ia['decision']} ({decision_ia['confianza']}%) | {decision_ia['razon']}"
        )

        decision  = decision_ia["decision"]
        confianza = decision_ia["confianza"]
        razon     = decision_ia["razon"]

        # 5. Ejecutar decision de la IA
        if decision == "COMPRAR" and posicion is None:
            rsi = indicadores["rsi"]
            capital_compra = DCA_CAPITAL_POR_NIVEL if DCA_HABILITADO else CAPITAL_INICIAL
            if rsi >= RSI_SOBRECOMPRA:
                logger.info(f"IA dice COMPRAR pero RSI={rsi} sobrecomprado -> ESPERAR")
                resultado["razon"] = f"RSI sobrecomprado ({rsi}), ignorando senal de compra"
            elif confianza >= CONFIANZA_MIN_COMPRA:
                orden = ejecutar_compra(precio_actual, capital_compra)
                if orden["ok"]:
                    abrir_posicion(SIMBOLO, orden["precio"], orden["cantidad"],
                                   orden["capital"], orden.get("orden_id"))
                    resultado["accion"] = "COMPRA_IA"
                    resultado["razon"]  = razon
                    logger.info(f"COMPRA IA @ ${orden['precio']:,.2f} (confianza: {confianza}%)")
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "COMPRA_IA",
                        orden["precio"], 0.0, 0.0,
                        razon, rsi_actual, macd_hist,
                    )
                    return resultado
            else:
                logger.info(f"Confianza insuficiente: {confianza}% < {CONFIANZA_MIN_COMPRA}%")
                resultado["razon"] = f"Confianza baja: {confianza}%"

        elif decision == "VENDER" and posicion is not None:
            pnl_actual = posicion_con_pnl["pnl_pct"]

            # GUARDIA DURA: nunca vender por debajo del punto de equilibrio (excepto stop-loss y timeout)
            precio_min_venta = _precio_minimo_venta(posicion["precio_compra"])
            if _precio_bajo_equilibrio(precio_actual, posicion["precio_compra"]):
                logger.info(
                    f"VENTA BLOQUEADA: precio ${precio_actual:,.2f} < equilibrio ${precio_min_venta:,.2f}. "
                    f"Esperando recuperacion."
                )
                resultado["accion"] = "ESPERAR"
                resultado["razon"]  = (
                    f"Venta bloqueada: precio ${precio_actual:,.2f} < equilibrio "
                    f"${precio_min_venta:,.2f}. Esperando recuperacion."
                )
                registrar_ciclo(
                    SIMBOLO, precio_actual, "ESPERAR",
                    precio_compra_pos, pnl_actual, posicion_con_pnl["pnl_usdt"],
                    resultado["razon"], rsi_actual, macd_hist,
                )
                return resultado

            ciclos_actual = posicion_con_pnl["ciclos_en_posicion"]
            if ciclos_actual < CICLOS_MIN_EN_POSICION:
                logger.info(
                    f"IA dice VENDER pero solo {ciclos_actual} ciclos en posicion "
                    f"(minimo {CICLOS_MIN_EN_POSICION}) -> ESPERAR"
                )
                resultado["accion"] = "ESPERAR"
                resultado["razon"]  = f"Muy pronto para vender ({ciclos_actual} ciclos)"

            elif pnl_actual < PNL_MIN_PARA_VENDER_IA:
                if confianza >= CONFIANZA_VENTA_FORZADA and pnl_actual >= PNL_MAX_PERDIDA_IA:
                    logger.info(
                        f"IA dice VENDER con alta confianza ({confianza}%) y P&L={pnl_actual:.2f}% -> EJECUTAR"
                    )
                    orden = ejecutar_venta(posicion, precio_actual)
                    if orden["ok"]:
                        pnl = cerrar_posicion(posicion, orden["precio"], razon, confianza, orden.get("orden_id"))
                        resultado["accion"] = "VENTA_IA"
                        resultado["pnl_pct"] = pnl["pnl_pct"]
                        resultado["razon"]   = razon
                        signo = "+" if pnl["pnl_pct"] >= 0 else ""
                        logger.info(f"VENTA IA (forzada) @ ${orden['precio']:,.2f} | P&L: {signo}{pnl['pnl_pct']:.2f}%")
                        registrar_ciclo(
                            SIMBOLO, precio_actual, "VENTA_IA",
                            precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                            razon, rsi_actual, macd_hist,
                        )
                        return resultado
                else:
                    logger.info(
                        f"IA dice VENDER pero P&L={pnl_actual:.2f}% < {PNL_MIN_PARA_VENDER_IA}% "
                        f"y confianza={confianza}% < {CONFIANZA_VENTA_FORZADA}% -> ESPERAR"
                    )
                    resultado["accion"] = "ESPERAR"
                    resultado["razon"]  = f"P&L insuficiente ({pnl_actual:.2f}%) y confianza baja ({confianza}%)"

            else:
                orden = ejecutar_venta(posicion, precio_actual)
                if orden["ok"]:
                    pnl = cerrar_posicion(posicion, orden["precio"], razon, confianza, orden.get("orden_id"))
                    resultado["accion"] = "VENTA_IA"
                    resultado["pnl_pct"] = pnl["pnl_pct"]
                    resultado["razon"]   = razon
                    signo = "+" if pnl["pnl_pct"] >= 0 else ""
                    logger.info(f"VENTA IA @ ${orden['precio']:,.2f} | P&L: {signo}{pnl['pnl_pct']:.2f}%")
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "VENTA_IA",
                        precio_compra_pos, pnl["pnl_pct"], pnl["pnl_usdt"],
                        razon, rsi_actual, macd_hist,
                    )
                    return resultado

        else:
            resultado["accion"] = "ESPERAR"
            resultado["razon"]  = razon
            logger.info(f"-> ESPERAR | {razon}")

        # 6. Registrar ciclo
        registrar_ciclo(
            SIMBOLO, precio_actual, resultado["accion"],
            precio_compra_pos,
            posicion_con_pnl["pnl_pct"] if posicion_con_pnl else None,
            posicion_con_pnl["pnl_usdt"] if posicion_con_pnl else None,
            resultado["razon"],
            rsi_actual, macd_hist,
        )

    except Exception as e:
        logger.error(f"Error en ciclo: {e}", exc_info=True)
        resultado["error"] = str(e)

    return resultado


def iniciar_bot():
    """Inicia el bot en bucle continuo."""
    from src.trading.posicion import inicializar_db

    logger.info("CryptoIA Bot v4 iniciando...")
    logger.info(f"   Simbolo:              {SIMBOLO}")
    logger.info(f"   Temporalidad:         {TEMPORALIDAD}")
    logger.info(f"   Intervalo:            {INTERVALO_MINUTOS} minutos")
    logger.info(f"   Capital:              ${CAPITAL_INICIAL:,.2f}")
    logger.info(f"   Stop-Loss:            {STOP_LOSS_PCT}%")
    logger.info(f"   Take-Profit:          {TAKE_PROFIT_PCT}%")
    logger.info(f"   Trailing activacion:  +{TRAILING_STOP_ACTIVACION_PCT}%")
    logger.info(f"   Trailing proteccion:  -{TRAILING_STOP_PROTECCION_PCT}% desde maximo")
    logger.info(f"   Ciclos min posicion:  {CICLOS_MIN_EN_POSICION}")
    logger.info(f"   Ciclos max posicion:  {CICLOS_MAX_EN_POSICION} (~{CICLOS_MAX_EN_POSICION * INTERVALO_MINUTOS} min timeout)")
    logger.info(f"   MACD min compra:      {MACD_HIST_MIN_COMPRA}")
    logger.info(f"   Cooldown stop-loss:   {COOLDOWN_POST_STOPLOSS} ciclos")
    logger.info(f"   Confianza min compra: {CONFIANZA_MIN_COMPRA}%")
    logger.info(f"   Comision total:       {COMISION_TOTAL_PCT}% (guardia de equilibrio activa)")
    logger.info(f"   TP rapido:            +{TAKE_PROFIT_RAPIDO_PCT}% (min {CICLOS_MIN_TAKE_PROFIT} ciclos)")
    logger.info(f"   Soft stop-loss:       -{SOFT_STOPLOSS_PCT}% (min {CICLOS_MIN_SOFT_STOPLOSS} ciclos, 2+ señales bajistas)")
    logger.info(f"   DCA:                  {'ACTIVADO' if DCA_HABILITADO else 'desactivado'}")
    if DCA_HABILITADO:
        logger.info(f"   DCA niveles:          {DCA_NIVELES} (${DCA_CAPITAL_POR_NIVEL:,.2f} por nivel)")
        logger.info(f"   DCA bajada:           {DCA_BAJADA_PCT}% para activar siguiente nivel")

    inicializar_db()

    intervalo_seg = INTERVALO_MINUTOS * 60

    while True:
        try:
            resultado = ejecutar_ciclo()
            logger.info(f"Ciclo completado: {resultado['accion']} | Proximo en {INTERVALO_MINUTOS} min")
        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario")
            break
        except Exception as e:
            logger.error(f"Error inesperado: {e}")

        time.sleep(intervalo_seg)
