"""
src/bot/ciclo.py — Ciclo principal del bot de trading
Mejoras v3:
  - Trailing Stop real (con precio_maximo en DB)
  - Cooldown post stop-loss
  - Filtro MACD mas estricto en compra determinista
  - IA puede vender con perdida controlada si confianza alta
  - Registro de cada ciclo en ciclos_log
  - GUARDIA DURA: nunca vender por debajo del precio de compra + comisiones (excepto stop-loss)
"""
import logging
import time
from datetime import datetime

from config import (
    SIMBOLO, TEMPORALIDAD, CAPITAL_INICIAL,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    INTERVALO_MINUTOS,
    TRAILING_STOP_ACTIVACION_PCT, TRAILING_STOP_PROTECCION_PCT,
    CICLOS_MIN_EN_POSICION, PNL_MIN_PARA_VENDER_IA,
    CONFIANZA_VENTA_FORZADA, PNL_MAX_PERDIDA_IA,
    MACD_HIST_MIN_COMPRA, COOLDOWN_POST_STOPLOSS,
    COMISION_TOTAL_PCT,
)
from src.mercado.datos import obtener_velas, resumen_indicadores
from src.ia.agente import consultar_ia
from src.trading.posicion import (
    obtener_posicion, calcular_pnl, abrir_posicion,
    cerrar_posicion, incrementar_ciclos,
    actualizar_precio_maximo, registrar_ultimo_stoploss,
    ciclos_desde_ultimo_stoploss, registrar_ciclo,
)
from src.trading.ejecutor import ejecutar_compra, ejecutar_venta

logger = logging.getLogger(__name__)

# Umbral minimo de confianza para que la IA ejecute una compra
CONFIANZA_MIN_COMPRA = 50

# Compra determinista: RSI en zona de sobreventa + MACD recuperando
RSI_SOBREVENTA  = 38   # RSI por debajo de este valor -> zona de oportunidad
RSI_SOBRECOMPRA = 72   # RSI por encima -> no comprar


def _precio_minimo_venta(precio_compra: float) -> float:
    """
    Calcula el precio minimo al que se puede vender para no perder dinero.
    Incluye las comisiones de compra + venta del exchange.
    Ejemplo: compre a $100.000, comisiones 0.2% -> minimo venta = $100.200
    """
    return precio_compra * (1 + COMISION_TOTAL_PCT / 100)


def _precio_bajo_equilibrio(precio_actual: float, precio_compra: float) -> bool:
    """
    Retorna True si el precio actual esta por debajo del punto de equilibrio
    (precio de compra + comisiones). En ese caso NO se debe vender por IA.
    """
    return precio_actual < _precio_minimo_venta(precio_compra)


def _evaluar_compra_determinista(indicadores: dict) -> tuple:
    """
    Evalua si hay condiciones deterministas para comprar.
    Retorna (bool, str) -> (comprar, razon)
    """
    rsi  = indicadores["rsi"]
    hist = indicadores["macd_hist"]
    ema_alcista    = indicadores["ema_alcista"]
    cerca_bb_lower = indicadores["cerca_bb_lower"]

    # Condicion 1: RSI en sobreventa + MACD no en caida libre
    if rsi < RSI_SOBREVENTA and hist > MACD_HIST_MIN_COMPRA:
        return True, f"Compra determinista: RSI={rsi} (sobreventa) + MACD hist={hist:.2f}"

    # Condicion 2: Precio cerca del piso de Bollinger + RSI no sobrecomprado
    if cerca_bb_lower and rsi < 55 and hist > MACD_HIST_MIN_COMPRA:
        return True, f"Compra determinista: precio en BB inferior + RSI={rsi}"

    # Condicion 3: EMAs alcistas + MACD cruce alcista reciente
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

            # Calcular precio minimo de venta rentable (incluye comisiones)
            precio_min_venta = _precio_minimo_venta(precio_compra_pos)
            bajo_equilibrio  = _precio_bajo_equilibrio(precio_actual, precio_compra_pos)

            logger.info(
                f"Posicion abierta @ ${posicion['precio_compra']:,.2f} | "
                f"Maximo: ${posicion['precio_maximo']:,.2f} | "
                f"P&L: {signo}{posicion_con_pnl['pnl_pct']:.2f}% ({signo}${posicion_con_pnl['pnl_usdt']:.2f}) | "
                f"Min. venta rentable: ${precio_min_venta:,.2f} | "
                f"{'BAJO EQUILIBRIO' if bajo_equilibrio else 'Sobre equilibrio'}"
            )

            # Actualizar precio maximo
            actualizar_precio_maximo(posicion["id"], precio_actual)
            precio_maximo = max(posicion["precio_maximo"], precio_actual)

            # 2a. Stop-Loss determinista
            # El stop-loss es la UNICA excepcion que puede vender con perdida
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

            # 2b. Trailing Stop
            ganancia_desde_compra = ((precio_maximo - posicion["precio_compra"]) / posicion["precio_compra"]) * 100
            caida_desde_maximo    = ((precio_maximo - precio_actual) / precio_maximo) * 100

            if (ganancia_desde_compra >= TRAILING_STOP_ACTIVACION_PCT and
                    caida_desde_maximo >= TRAILING_STOP_PROTECCION_PCT):
                # Guardia: el trailing stop solo actua si el precio sigue siendo rentable
                if bajo_equilibrio:
                    logger.info(
                        f"TRAILING STOP activado pero precio ${precio_actual:,.2f} < "
                        f"minimo rentable ${precio_min_venta:,.2f} -> ESPERAR recuperacion"
                    )
                    resultado["accion"] = "ESPERAR"
                    resultado["razon"]  = (
                        f"Trailing Stop bloqueado: precio bajo punto de equilibrio "
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

            # 2c. Take-Profit determinista
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

            # Incrementar ciclos en posicion
            incrementar_ciclos(posicion["id"])

        # 3. Compra determinista (sin IA)
        if posicion is None:
            # Cooldown post stop-loss
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

            comprar_det, razon_det = _evaluar_compra_determinista(indicadores)
            if comprar_det:
                logger.info(f"{razon_det}")
                orden = ejecutar_compra(precio_actual, CAPITAL_INICIAL)
                if orden["ok"]:
                    abrir_posicion(SIMBOLO, orden["precio"], orden["cantidad"],
                                   orden["capital"], orden.get("orden_id"))
                    resultado["accion"] = "COMPRA_DETERMINISTA"
                    resultado["razon"]  = razon_det
                    logger.info(f"COMPRA DETERMINISTA @ ${orden['precio']:,.2f}")
                    registrar_ciclo(
                        SIMBOLO, precio_actual, "COMPRA_DETERMINISTA",
                        orden["precio"], 0.0, 0.0,
                        razon_det, rsi_actual, macd_hist,
                    )
                return resultado

        # 4. Consultar IA con contexto completo
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
            if rsi >= RSI_SOBRECOMPRA:
                logger.info(f"IA dice COMPRAR pero RSI={rsi} sobrecomprado -> ESPERAR")
                resultado["razon"] = f"RSI sobrecomprado ({rsi}), ignorando senal de compra"
            elif confianza >= CONFIANZA_MIN_COMPRA:
                orden = ejecutar_compra(precio_actual, CAPITAL_INICIAL)
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
            ciclos_actual = posicion_con_pnl["ciclos_en_posicion"]
            pnl_actual    = posicion_con_pnl["pnl_pct"]

            # ================================================================
            # GUARDIA DURA: nunca vender por debajo del punto de equilibrio
            # La unica excepcion es el stop-loss (ya manejado en seccion 2a)
            # Si compramos a $100 y el precio esta en $99, NO vendemos.
            # Esperamos a que suba al menos a precio_compra + comisiones.
            # ================================================================
            precio_min_venta = _precio_minimo_venta(posicion["precio_compra"])
            if _precio_bajo_equilibrio(precio_actual, posicion["precio_compra"]):
                logger.info(
                    f"VENTA BLOQUEADA por guardia de equilibrio: "
                    f"precio actual ${precio_actual:,.2f} < minimo rentable ${precio_min_venta:,.2f} "
                    f"(compre a ${posicion['precio_compra']:,.2f} + {COMISION_TOTAL_PCT}% comisiones). "
                    f"Esperando que el precio suba antes de vender."
                )
                resultado["accion"] = "ESPERAR"
                resultado["razon"]  = (
                    f"Venta bloqueada: precio ${precio_actual:,.2f} < punto de equilibrio "
                    f"${precio_min_venta:,.2f} (compra ${posicion['precio_compra']:,.2f} + comisiones). "
                    f"Esperando recuperacion."
                )
                registrar_ciclo(
                    SIMBOLO, precio_actual, "ESPERAR",
                    precio_compra_pos, pnl_actual, posicion_con_pnl["pnl_usdt"],
                    resultado["razon"], rsi_actual, macd_hist,
                )
                return resultado

            # Proteccion 1: minimo de ciclos en posicion antes de vender
            if ciclos_actual < CICLOS_MIN_EN_POSICION:
                logger.info(
                    f"IA dice VENDER pero solo {ciclos_actual} ciclos en posicion "
                    f"(minimo {CICLOS_MIN_EN_POSICION}) -> ESPERAR"
                )
                resultado["accion"] = "ESPERAR"
                resultado["razon"]  = f"Muy pronto para vender ({ciclos_actual} ciclos)"

            # Proteccion 2: venta con perdida — solo si confianza muy alta y perdida controlada
            elif pnl_actual < PNL_MIN_PARA_VENDER_IA:
                if confianza >= CONFIANZA_VENTA_FORZADA and pnl_actual >= PNL_MAX_PERDIDA_IA:
                    # IA muy segura + perdida pequena -> permitir salida anticipada
                    logger.info(
                        f"IA dice VENDER con alta confianza ({confianza}%) y P&L={pnl_actual:.2f}% "
                        f"(perdida controlada) -> EJECUTAR"
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

        # 6. Registrar ciclo (ESPERAR o accion sin retorno anticipado)
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

    logger.info("CryptoIA Bot v3 iniciando...")
    logger.info(f"   Simbolo:              {SIMBOLO}")
    logger.info(f"   Temporalidad:         {TEMPORALIDAD}")
    logger.info(f"   Intervalo:            {INTERVALO_MINUTOS} minutos")
    logger.info(f"   Capital:              ${CAPITAL_INICIAL:,.2f}")
    logger.info(f"   Stop-Loss:            {STOP_LOSS_PCT}%")
    logger.info(f"   Take-Profit:          {TAKE_PROFIT_PCT}%")
    logger.info(f"   Trailing activacion:  +{TRAILING_STOP_ACTIVACION_PCT}%")
    logger.info(f"   Trailing proteccion:  -{TRAILING_STOP_PROTECCION_PCT}% desde maximo")
    logger.info(f"   Ciclos min posicion:  {CICLOS_MIN_EN_POSICION}")
    logger.info(f"   MACD min compra:      {MACD_HIST_MIN_COMPRA}")
    logger.info(f"   Cooldown stop-loss:   {COOLDOWN_POST_STOPLOSS} ciclos")
    logger.info(f"   Confianza min compra: {CONFIANZA_MIN_COMPRA}%")
    logger.info(f"   RSI sobreventa:       < {RSI_SOBREVENTA}")
    logger.info(f"   Comision total:       {COMISION_TOTAL_PCT}% (guardia de equilibrio activa)")

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
