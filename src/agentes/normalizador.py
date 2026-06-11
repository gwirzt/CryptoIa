"""
src/agentes/normalizador.py — Normaliza las respuestas de las IAs
Los modelos a veces responden en inglés o con variantes del texto esperado.
Este módulo estandariza las respuestas a los valores válidos del sistema.
"""

# Mapeo de variantes a valores canónicos para ACCION
MAPA_ACCION = {
    # Español
    "compra":   "COMPRA",
    "comprar":  "COMPRA",
    "buy":      "COMPRA",
    "long":     "COMPRA",
    "venta":    "VENTA",
    "vender":   "VENTA",
    "sell":     "VENTA",
    "short":    "VENTA",
    "esperar":  "ESPERAR",
    "espera":   "ESPERAR",
    "wait":     "ESPERAR",
    "hold":     "ESPERAR",
    "neutral":  "ESPERAR",
    "esporte":  "ESPERAR",   # error frecuente del modelo
    "esper":    "ESPERAR",
    "esperrar": "ESPERAR",
    "mantener": "ESPERAR",
    "mantén":   "ESPERAR",
    "no operar":"ESPERAR",
}

# Mapeo de variantes a valores canónicos para IMPACTO
MAPA_IMPACTO = {
    "alcista":  "ALCISTA",
    "bullish":  "ALCISTA",
    "positivo": "ALCISTA",
    "positive": "ALCISTA",
    "bajista":  "BAJISTA",
    "bearish":  "BAJISTA",
    "negativo": "BAJISTA",
    "negative": "BAJISTA",
    "neutral":  "NEUTRAL",
    "sideways": "NEUTRAL",
    "lateral":  "NEUTRAL",
}

# Mapeo de variantes a valores canónicos para DECISION (igual que ACCION)
MAPA_DECISION = MAPA_ACCION


def normalizar_accion(valor: str) -> str:
    """Normaliza el campo 'accion' de la respuesta del Agente Técnico."""
    if not valor:
        return "ESPERAR"
    clave = valor.strip().lower()
    return MAPA_ACCION.get(clave, "ESPERAR")


def normalizar_impacto(valor: str) -> str:
    """Normaliza el campo 'impacto' de la respuesta del Agente Fundamental."""
    if not valor:
        return "NEUTRAL"
    clave = valor.strip().lower()
    return MAPA_IMPACTO.get(clave, "NEUTRAL")


def normalizar_decision(valor: str) -> str:
    """Normaliza el campo 'decision' de la respuesta del Gestor de Riesgos."""
    if not valor:
        return "ESPERAR"
    clave = valor.strip().lower()
    return MAPA_DECISION.get(clave, "ESPERAR")


def normalizar_respuesta_tecnico(datos: dict) -> dict:
    """Normaliza todos los campos de la respuesta del Agente Técnico."""
    if not datos:
        return {"accion": "ESPERAR", "confianza": 0, "justificacion": "Sin respuesta"}
    datos["accion"] = normalizar_accion(datos.get("accion", "ESPERAR"))
    datos["confianza"] = max(0, min(100, int(datos.get("confianza", 0))))
    datos["justificacion"] = str(datos.get("justificacion", ""))[:500]
    return datos


def normalizar_respuesta_fundamental(datos: dict) -> dict:
    """Normaliza todos los campos de la respuesta del Agente Fundamental."""
    if not datos:
        return {"impacto": "NEUTRAL", "intensidad": 0, "justificacion": "Sin respuesta"}
    datos["impacto"] = normalizar_impacto(datos.get("impacto", "NEUTRAL"))
    datos["intensidad"] = max(0, min(100, int(datos.get("intensidad", 0))))
    datos["justificacion"] = str(datos.get("justificacion", ""))[:500]
    return datos


def normalizar_respuesta_riesgo(datos: dict) -> dict:
    """Normaliza todos los campos de la respuesta del Gestor de Riesgos."""
    if not datos:
        return {"decision": "ESPERAR", "stop_loss_pct": 2.5, "take_profit_pct": 5.0, "motivo": "Sin respuesta"}
    datos["decision"] = normalizar_decision(datos.get("decision", "ESPERAR"))
    # Acepta "motivo", "razon", "reason", "justificacion"
    motivo = (datos.get("motivo") or datos.get("razon") or
              datos.get("reason") or datos.get("justificacion") or "Sin motivo")
    datos["motivo"] = str(motivo)[:500]
    try:
        datos["stop_loss_pct"] = float(datos.get("stop_loss_pct", 2.5))
    except (ValueError, TypeError):
        datos["stop_loss_pct"] = 2.5
    try:
        datos["take_profit_pct"] = float(datos.get("take_profit_pct", 5.0))
    except (ValueError, TypeError):
        datos["take_profit_pct"] = 5.0
    return datos
