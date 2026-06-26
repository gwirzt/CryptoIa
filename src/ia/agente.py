"""
src/ia/agente.py — Agente unico de trading con contexto completo
Recibe indicadores tecnicos + posicion actual + P&L y decide COMPRAR/VENDER/ESPERAR
El prompt esta orientado al negocio real: precio de compra, ganancia/perdida en USDT, etc.
MEJORA: el prompt incluye el precio minimo de venta (punto de equilibrio con comisiones)
y una regla explicita de NO vender por debajo de ese precio.
"""
import json
import requests
import logging
from typing import Optional
from config import URL_IA, MODELO_IA, COMISION_TOTAL_PCT

logger = logging.getLogger(__name__)


def construir_prompt(
    indicadores: dict,
    posicion: Optional[dict],
    simbolo: str,
    temporalidad: str,
) -> str:
    """
    Construye el prompt completo para la IA.
    El prompt esta orientado al negocio: la IA sabe cuanto pago, cuanto vale ahora,
    y cuanto ganaria o perderia si vende en este momento.
    Incluye el precio minimo de venta rentable (precio_compra + comisiones).
    """
    precio_actual = indicadores["precio"]
    rsi           = indicadores["rsi"]
    macd_hist     = indicadores["macd_hist"]
    ema9          = indicadores["ema9"]
    ema21         = indicadores["ema21"]
    ema50         = indicadores["ema50"]
    bb_upper      = indicadores["bb_upper"]
    bb_lower      = indicadores["bb_lower"]
    bb_mid        = indicadores["bb_mid"]

    # Interpretacion de indicadores
    rsi_estado = "SOBRECOMPRADO" if rsi > 70 else "SOBREVENDIDO" if rsi < 30 else f"neutral ({rsi})"
    tend_emas  = "ALCISTA" if indicadores.get("ema_alcista") else "BAJISTA" if indicadores.get("ema_bajista") else "MIXTA"
    macd_dir   = "alcista (presion compradora)" if macd_hist > 0 else "bajista (presion vendedora)"
    bb_pos     = "cerca del TECHO (posible resistencia)" if indicadores.get("cerca_bb_upper") else \
                 "cerca del PISO (posible soporte)" if indicadores.get("cerca_bb_lower") else \
                 "dentro de las bandas"

    # Ultimas velas
    velas_str = ""
    for v in indicadores.get("ultimas_velas", []):
        cambio = round(v["close"] - v["open"], 2)
        signo  = "+" if cambio >= 0 else ""
        velas_str += f"  {v['tiempo'][-8:-3]}: {v['dir']} ${v['open']:,.0f} -> ${v['close']:,.0f} ({signo}${cambio})\n"

    # Seccion de posicion (el corazon del prompt)
    if posicion:
        precio_compra  = posicion["precio_compra"]
        cantidad       = posicion["cantidad"]
        capital_usado  = posicion["capital_usado"]
        valor_actual   = posicion.get("valor_actual", cantidad * precio_actual)
        pnl_pct        = posicion["pnl_pct"]
        pnl_usdt       = posicion["pnl_usdt"]
        ciclos         = posicion.get("ciclos_en_posicion", 0)
        tiempo_min     = ciclos * 7  # cada ciclo = 7 minutos

        # Calcular precio minimo de venta rentable (incluye comisiones de compra + venta)
        precio_minimo_venta = precio_compra * (1 + COMISION_TOTAL_PCT / 100)
        bajo_equilibrio     = precio_actual < precio_minimo_venta
        diferencia_equilibrio = precio_actual - precio_minimo_venta

        signo = "+" if pnl_pct >= 0 else ""
        estado_pnl = "GANANDO" if pnl_pct > 0 else "PERDIENDO" if pnl_pct < 0 else "en punto de equilibrio"

        if bajo_equilibrio:
            alerta_equilibrio = (
                f"  ATENCION: precio actual ${precio_actual:,.2f} esta ${abs(diferencia_equilibrio):,.2f} "
                f"POR DEBAJO del punto de equilibrio.\n"
                f"  Si vendes ahora PERDERIAS dinero real (precio + comisiones).\n"
                f"  DEBES ESPERAR a que el precio suba al menos a ${precio_minimo_venta:,.2f}"
            )
        else:
            alerta_equilibrio = (
                f"  El precio actual esta ${diferencia_equilibrio:,.2f} POR ENCIMA del punto de equilibrio.\n"
                f"  Puedes vender con ganancia real si los indicadores lo justifican."
            )

        posicion_str = f"""
╔══════════════════════════════════════════════════════╗
║  POSICION ABIERTA — ANALISIS DE NEGOCIO              ║
╚══════════════════════════════════════════════════════╝

  Inverte:           ${capital_usado:,.2f} USDT
  Compre:            {cantidad:.6f} {simbolo.split('/')[0]} a ${precio_compra:,.2f}
  Precio actual:     ${precio_actual:,.2f}
  Valor actual:      ${valor_actual:,.2f} USDT
  
  Resultado ahora:   {signo}{pnl_pct:.3f}% -> {signo}${pnl_usdt:.2f} USDT ({estado_pnl})
  Tiempo en posicion: {tiempo_min} minutos ({ciclos} ciclos)

  PUNTO DE EQUILIBRIO (precio_compra + {COMISION_TOTAL_PCT}% comisiones):
  Precio minimo para no perder: ${precio_minimo_venta:,.2f}
{alerta_equilibrio}

  Si VENDO AHORA:    recupero ${valor_actual:,.2f} USDT ({signo}${pnl_usdt:.2f} vs lo invertido)

PREGUNTA CLAVE: Conviene vender ahora o esperar que suba mas?
- Si el precio esta POR DEBAJO de ${precio_minimo_venta:,.2f} -> ESPERAR (vender ahora = perder dinero real)
- Si los indicadores sugieren que el precio va a BAJAR mas y ya estoy sobre el equilibrio -> VENDER
- Si los indicadores sugieren que el precio va a SUBIR -> ESPERAR (mantener posicion)
- Si hay incertidumbre pero estoy ganando -> evaluar si la ganancia actual justifica el riesgo
"""
    else:
        posicion_str = f"""
╔══════════════════════════════════════════════════════╗
║  SIN POSICION — EVALUANDO ENTRADA AL MERCADO         ║
╚══════════════════════════════════════════════════════╝

  Capital disponible: $10,000 USDT
  Si COMPRO AHORA:    obtengo {10000/precio_actual:.6f} {simbolo.split('/')[0]} a ${precio_actual:,.2f}

PREGUNTA CLAVE: Es buen momento para comprar?
- Solo comprar si hay senales tecnicas CLARAS de que el precio va a subir
- En zona de soporte (BB inferior, RSI bajo) -> puede ser buena entrada
- En zona de resistencia (BB superior, RSI alto) -> esperar correccion
"""

    prompt = f"""Sos un trader profesional de criptomonedas. Tu objetivo es MAXIMIZAR la ganancia en USDT.

═══════════════════════════════════════════════════════
  MERCADO: {simbolo} | Temporalidad: {temporalidad}
═══════════════════════════════════════════════════════

PRECIO ACTUAL: ${precio_actual:,.2f}

INDICADORES TECNICOS:
  RSI (14):        {rsi_estado}
  MACD Histograma: {macd_hist:.4f} -> {macd_dir}
  Tendencia EMAs:  {tend_emas} (EMA9=${ema9:,.0f} | EMA21=${ema21:,.0f} | EMA50=${ema50:,.0f})
  Bollinger:       Superior=${bb_upper:,.0f} | Medio=${bb_mid:,.0f} | Inferior=${bb_lower:,.0f}
  Precio esta:     {bb_pos}
  Cruce MACD:      {"ALCISTA reciente" if indicadores.get("macd_cruce_alcista") else "BAJISTA reciente" if indicadores.get("macd_cruce_bajista") else "sin cruce reciente"}

ULTIMAS 3 VELAS ({temporalidad}):
{velas_str}
{posicion_str}

═══════════════════════════════════════════════════════
  TU DECISION (JSON estricto, sin texto adicional)
═══════════════════════════════════════════════════════
{{
  "decision": "COMPRAR" | "VENDER" | "ESPERAR",
  "confianza": <numero 0-100 que refleja tu certeza>,
  "razon": "<razonamiento concreto en 1-2 oraciones, mencionando precio de compra y P&L si hay posicion>"
}}

REGLAS ESTRICTAS:
- "VENDER" solo si hay posicion abierta
- "COMPRAR" solo si NO hay posicion abierta
- Ante la duda -> ESPERAR
- La razon debe ser especifica (mencionar numeros concretos)
- NUNCA sugerir VENDER si el precio actual esta por debajo del punto de equilibrio (precio_compra + comisiones)
- Si el precio esta bajo el punto de equilibrio y los indicadores son bajistas -> ESPERAR recuperacion, NO vender
- Solo el Stop-Loss automatico del sistema puede cerrar una posicion con perdida real
- Recorda: vender por debajo del punto de equilibrio = perder dinero real aunque el P&L parezca pequeno
"""
    return prompt


def consultar_ia(
    indicadores: dict,
    posicion: Optional[dict],
    simbolo: str,
    temporalidad: str,
    timeout: int = 120,
) -> dict:
    """
    Consulta a Ollama y retorna la decision de la IA.
    Retorna dict con: decision, confianza, razon, [error]
    """
    prompt = construir_prompt(indicadores, posicion, simbolo, temporalidad)

    payload = {
        "model":  MODELO_IA,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.1,   # baja temperatura = respuestas mas deterministas
            "num_predict": 250,
        }
    }

    try:
        resp = requests.post(URL_IA, json=payload, timeout=timeout)
        resp.raise_for_status()
        data  = resp.json()
        texto = data.get("response", "").strip()

        resultado = _parsear_respuesta(texto)
        logger.info(f"IA -> {resultado['decision']} ({resultado['confianza']}%) | {resultado['razon']}")
        return resultado

    except requests.exceptions.Timeout:
        logger.error("Timeout consultando IA")
        return {"decision": "ESPERAR", "confianza": 0, "razon": "Timeout IA", "error": "timeout"}
    except Exception as e:
        logger.error(f"Error consultando IA: {e}")
        return {"decision": "ESPERAR", "confianza": 0, "razon": str(e), "error": str(e)}


def _parsear_respuesta(texto: str) -> dict:
    """Extrae el JSON de la respuesta del modelo."""
    inicio = texto.find("{")
    fin    = texto.rfind("}") + 1
    if inicio >= 0 and fin > inicio:
        try:
            data     = json.loads(texto[inicio:fin])
            decision = str(data.get("decision", "ESPERAR")).upper().strip()
            if decision not in ("COMPRAR", "VENDER", "ESPERAR"):
                decision = "ESPERAR"
            return {
                "decision":  decision,
                "confianza": int(data.get("confianza", 50)),
                "razon":     str(data.get("razon", "Sin razon")),
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: buscar palabras clave
    texto_upper = texto.upper()
    if "COMPRAR" in texto_upper:
        decision = "COMPRAR"
    elif "VENDER" in texto_upper:
        decision = "VENDER"
    else:
        decision = "ESPERAR"

    return {
        "decision":  decision,
        "confianza": 50,
        "razon":     texto[:200] if texto else "Respuesta no parseable",
    }
