"""
src/ia/agente.py — Agente único de trading con contexto completo
Recibe indicadores técnicos + posición actual + P&L y decide COMPRAR/VENDER/ESPERAR
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
    
    posicion: None si no hay posición abierta, o dict con:
        - precio_compra: float
        - cantidad: float
        - pnl_pct: float  (positivo = ganancia, negativo = pérdida)
        - pnl_usdt: float
        - ciclos_en_posicion: int
    """
    precio_actual = indicadores["precio"]
    rsi = indicadores["rsi"]
    macd = indicadores["macd"]
    macd_signal = indicadores["macd_signal"]
    macd_hist = indicadores["macd_hist"]
    ema9 = indicadores["ema9"]
    ema21 = indicadores["ema21"]
    ema50 = indicadores["ema50"]
    bb_upper = indicadores["bb_upper"]
    bb_lower = indicadores["bb_lower"]

    # Resumen de velas
    velas_str = ""
    for v in indicadores.get("ultimas_velas", []):
        velas_str += f"  {v['tiempo']}: {v['dir']} open={v['open']} close={v['close']}\n"

    # Sección de posición
    if posicion:
        precio_compra = posicion["precio_compra"]
        pnl_pct = posicion["pnl_pct"]
        pnl_usdt = posicion["pnl_usdt"]
        ciclos = posicion.get("ciclos_en_posicion", 0)
        signo = "+" if pnl_pct >= 0 else ""
        posicion_str = f"""
=== POSICIÓN ABIERTA ===
Precio de compra:  ${precio_compra:,.2f}
Precio actual:     ${precio_actual:,.2f}
P&L actual:        {signo}{pnl_pct:.2f}% ({signo}${pnl_usdt:.2f} USDT)
Ciclos en posición: {ciclos}

IMPORTANTE: Tenés una posición abierta. Tu decisión principal es si VENDER o MANTENER.
- Si el P&L es positivo y los indicadores se deterioran → considerá VENDER para asegurar ganancia
- Si el P&L es negativo y la tendencia sigue bajando → considerá VENDER para limitar pérdida
- Si la tendencia es alcista y el P&L es positivo → podés MANTENER (responder ESPERAR)
"""
    else:
        posicion_str = """
=== SIN POSICIÓN ABIERTA ===
No tenés ninguna compra activa. Tu decisión principal es si COMPRAR o ESPERAR.
- Solo recomendá COMPRAR si los indicadores son claramente alcistas
- En caso de duda, recomendá ESPERAR
"""

    prompt = f"""Sos un trader experto en criptomonedas. Analizá la siguiente situación de mercado y tomá una decisión.

=== MERCADO: {simbolo} | Temporalidad: {temporalidad} ===

PRECIO ACTUAL: ${precio_actual:,.2f}

=== INDICADORES TÉCNICOS ===
RSI (14):        {rsi} {"⚠️ SOBRECOMPRADO" if rsi > 70 else "⚠️ SOBREVENDIDO" if rsi < 30 else "✓ neutral"}
MACD:            {macd:.4f}
MACD Signal:     {macd_signal:.4f}
MACD Histograma: {macd_hist:.4f} {"▲ alcista" if macd_hist > 0 else "▼ bajista"}
EMA 9:           ${ema9:,.2f}
EMA 21:          ${ema21:,.2f}
EMA 50:          ${ema50:,.2f}
Tendencia EMAs:  {"▲ ALCISTA (9>21>50)" if indicadores.get("ema_alcista") else "▼ BAJISTA (9<21<50)" if indicadores.get("ema_bajista") else "↔ MIXTA"}
BB Superior:     ${bb_upper:,.2f}
BB Inferior:     ${bb_lower:,.2f}
Precio vs BB:    {"⚠️ Cerca del techo" if indicadores.get("cerca_bb_upper") else "⚠️ Cerca del piso" if indicadores.get("cerca_bb_lower") else "✓ dentro de bandas"}

=== ÚLTIMAS 3 VELAS ===
{velas_str}
{posicion_str}

=== TU RESPUESTA (JSON estricto, sin texto adicional) ===
Respondé ÚNICAMENTE con este JSON:
{{
  "decision": "COMPRAR" | "VENDER" | "ESPERAR",
  "confianza": <número entre 0 y 100>,
  "razon": "<explicación breve en español, máximo 2 oraciones>"
}}

Reglas:
- "VENDER" solo es válido si hay posición abierta
- "COMPRAR" solo es válido si NO hay posición abierta
- Sé conservador: ante la duda, ESPERAR
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
    
    Retorna dict con:
        - decision: "COMPRAR" | "VENDER" | "ESPERAR"
        - confianza: int (0-100)
        - razon: str
        - error: str (solo si hubo error)
    """
    prompt = construir_prompt(indicadores, posicion, simbolo, temporalidad)
    
    payload = {
        "model": MODELO_IA,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.1,   # baja temperatura = respuestas más deterministas
            "num_predict": 200,
        }
    }
    
    try:
        resp = requests.post(URL_IA, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        texto = data.get("response", "").strip()
        
        # Extraer JSON de la respuesta
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
    # Buscar el bloque JSON
    inicio = texto.find("{")
    fin = texto.rfind("}") + 1
    if inicio >= 0 and fin > inicio:
        try:
            data = json.loads(texto[inicio:fin])
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
