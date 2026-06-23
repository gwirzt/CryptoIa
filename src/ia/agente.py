"""
src/ia/agente.py — Agente único de trading con contexto completo
Recibe indicadores técnicos + posición actual + P&L y decide COMPRAR/VENDER/ESPERAR
El prompt está orientado al negocio real: precio de compra, ganancia/pérdida en USDT, etc.
"""
import json
import requests
import logging
from typing import Optional
from config import URL_IA, MODELO_IA

logger = logging.getLogger(__name__)


def construir_prompt(
    indicadores: dict,
    posicion: Optional[dict],
    simbolo: str,
    temporalidad: str,
) -> str:
    """
    Construye el prompt completo para la IA.
    El prompt está orientado al negocio: la IA sabe cuánto pagó, cuánto vale ahora,
    y cuánto ganaría o perdería si vende en este momento.
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

    # Interpretación de indicadores
    rsi_estado = "SOBRECOMPRADO ⚠️" if rsi > 70 else "SOBREVENDIDO 🟢" if rsi < 30 else f"neutral ({rsi})"
    tend_emas  = "▲ ALCISTA" if indicadores.get("ema_alcista") else "▼ BAJISTA" if indicadores.get("ema_bajista") else "↔ MIXTA"
    macd_dir   = "▲ alcista (presión compradora)" if macd_hist > 0 else "▼ bajista (presión vendedora)"
    bb_pos     = "cerca del TECHO (posible resistencia)" if indicadores.get("cerca_bb_upper") else \
                 "cerca del PISO (posible soporte)" if indicadores.get("cerca_bb_lower") else \
                 "dentro de las bandas"

    # Últimas velas
    velas_str = ""
    for v in indicadores.get("ultimas_velas", []):
        cambio = round(v["close"] - v["open"], 2)
        signo  = "+" if cambio >= 0 else ""
        velas_str += f"  {v['tiempo'][-8:-3]}: {v['dir']} ${v['open']:,.0f} → ${v['close']:,.0f} ({signo}${cambio})\n"

    # ── Sección de posición (el corazón del prompt) ────────────────────────────
    if posicion:
        precio_compra  = posicion["precio_compra"]
        cantidad       = posicion["cantidad"]
        capital_usado  = posicion["capital_usado"]
        valor_actual   = posicion.get("valor_actual", cantidad * precio_actual)
        pnl_pct        = posicion["pnl_pct"]
        pnl_usdt       = posicion["pnl_usdt"]
        ciclos         = posicion.get("ciclos_en_posicion", 0)
        tiempo_min     = ciclos * 7  # cada ciclo = 7 minutos

        signo = "+" if pnl_pct >= 0 else ""
        estado_pnl = "GANANDO" if pnl_pct > 0 else "PERDIENDO" if pnl_pct < 0 else "en punto de equilibrio"

        posicion_str = f"""
╔══════════════════════════════════════════════════════╗
║  POSICIÓN ABIERTA — ANÁLISIS DE NEGOCIO              ║
╚══════════════════════════════════════════════════════╝

  Invertí:          ${capital_usado:,.2f} USDT
  Compré:           {cantidad:.6f} {simbolo.split('/')[0]} a ${precio_compra:,.2f}
  Precio actual:    ${precio_actual:,.2f}
  Valor actual:     ${valor_actual:,.2f} USDT
  
  Resultado ahora:  {signo}{pnl_pct:.3f}% → {signo}${pnl_usdt:.2f} USDT ({estado_pnl})
  Tiempo en posición: {tiempo_min} minutos ({ciclos} ciclos)

  Si VENDO AHORA:   recupero ${valor_actual:,.2f} USDT ({signo}${pnl_usdt:.2f} vs lo invertido)

PREGUNTA CLAVE: ¿Conviene vender ahora o esperar que suba más?
- Si los indicadores sugieren que el precio va a BAJAR → VENDER para asegurar/limitar pérdida
- Si los indicadores sugieren que el precio va a SUBIR → ESPERAR (mantener posición)
- Si hay incertidumbre pero estoy ganando → evaluar si la ganancia actual justifica el riesgo
"""
    else:
        posicion_str = f"""
╔══════════════════════════════════════════════════════╗
║  SIN POSICIÓN — EVALUANDO ENTRADA AL MERCADO         ║
╚══════════════════════════════════════════════════════╝

  Capital disponible: $10,000 USDT
  Si COMPRO AHORA:    obtengo {10000/precio_actual:.6f} {simbolo.split('/')[0]} a ${precio_actual:,.2f}

PREGUNTA CLAVE: ¿Es buen momento para comprar?
- Solo comprar si hay señales técnicas CLARAS de que el precio va a subir
- En zona de soporte (BB inferior, RSI bajo) → puede ser buena entrada
- En zona de resistencia (BB superior, RSI alto) → esperar corrección
"""

    prompt = f"""Sos un trader profesional de criptomonedas. Tu objetivo es MAXIMIZAR la ganancia en USDT.

═══════════════════════════════════════════════════════
  MERCADO: {simbolo} | Temporalidad: {temporalidad}
═══════════════════════════════════════════════════════

PRECIO ACTUAL: ${precio_actual:,.2f}

INDICADORES TÉCNICOS:
  RSI (14):        {rsi_estado}
  MACD Histograma: {macd_hist:.4f} → {macd_dir}
  Tendencia EMAs:  {tend_emas} (EMA9=${ema9:,.0f} | EMA21=${ema21:,.0f} | EMA50=${ema50:,.0f})
  Bollinger:       Superior=${bb_upper:,.0f} | Medio=${bb_mid:,.0f} | Inferior=${bb_lower:,.0f}
  Precio está:     {bb_pos}
  Cruce MACD:      {"▲ ALCISTA reciente" if indicadores.get("macd_cruce_alcista") else "▼ BAJISTA reciente" if indicadores.get("macd_cruce_bajista") else "sin cruce reciente"}

ÚLTIMAS 3 VELAS ({temporalidad}):
{velas_str}
{posicion_str}

═══════════════════════════════════════════════════════
  TU DECISIÓN (JSON estricto, sin texto adicional)
═══════════════════════════════════════════════════════
{{
  "decision": "COMPRAR" | "VENDER" | "ESPERAR",
  "confianza": <número 0-100 que refleja tu certeza>,
  "razon": "<razonamiento concreto en 1-2 oraciones, mencionando precio de compra y P&L si hay posición>"
}}

REGLAS ESTRICTAS:
- "VENDER" solo si hay posición abierta
- "COMPRAR" solo si NO hay posición abierta  
- Ante la duda → ESPERAR
- La razón debe ser específica (mencionar números concretos)
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
    Consulta a Ollama y retorna la decisión de la IA.
    Retorna dict con: decision, confianza, razon, [error]
    """
    prompt = construir_prompt(indicadores, posicion, simbolo, temporalidad)

    payload = {
        "model":  MODELO_IA,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.1,   # baja temperatura = respuestas más deterministas
            "num_predict": 250,
        }
    }

    try:
        resp = requests.post(URL_IA, json=payload, timeout=timeout)
        resp.raise_for_status()
        data  = resp.json()
        texto = data.get("response", "").strip()

        resultado = _parsear_respuesta(texto)
        logger.info(f"IA → {resultado['decision']} ({resultado['confianza']}%) | {resultado['razon']}")
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
                "razon":     str(data.get("razon", "Sin razón")),
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
