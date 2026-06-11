"""
src/mercado/binance_client.py — Cliente de mercado real conectado a Binance
Obtiene velas OHLCV y calcula indicadores técnicos reales.
No requiere API key (solo lectura pública).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands
from config import EXCHANGE, SIMBOLO, TEMPORALIDAD


def obtener_velas(simbolo: str = None, temporalidad: str = None, limite: int = 150) -> pd.DataFrame:
    """
    Descarga las últimas N velas de Binance y devuelve un DataFrame.
    No requiere API key — solo lectura pública.
    """
    simbolo = simbolo or SIMBOLO
    temporalidad = temporalidad or TEMPORALIDAD

    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"}
    })

    ohlcv = exchange.fetch_ohlcv(simbolo, temporalidad, limit=limite)

    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    df = df.astype(float)
    return df


def calcular_indicadores(df: pd.DataFrame, temporalidad: str = None) -> dict:
    """
    Calcula todos los indicadores técnicos sobre el DataFrame de velas.
    Devuelve un diccionario con los valores actuales (última vela).
    """
    temporalidad = temporalidad or TEMPORALIDAD
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["volume"]

    # RSI (14 períodos)
    rsi_ind = RSIIndicator(close=close, window=14)
    rsi = rsi_ind.rsi().iloc[-1]

    # MACD (12, 26, 9)
    macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    macd_val  = macd_ind.macd().iloc[-1]
    macd_sig  = macd_ind.macd_signal().iloc[-1]
    macd_hist = macd_ind.macd_diff().iloc[-1]
    macd_prev_hist = macd_ind.macd_diff().iloc[-2]
    macd_cruce = "ALCISTA" if macd_hist > 0 and macd_prev_hist <= 0 else \
                 "BAJISTA" if macd_hist < 0 and macd_prev_hist >= 0 else \
                 "POSITIVO" if macd_hist > 0 else "NEGATIVO"

    # Bandas de Bollinger (20, 2)
    bb_ind = BollingerBands(close=close, window=20, window_dev=2)
    bb_upper = bb_ind.bollinger_hband().iloc[-1]
    bb_mid   = bb_ind.bollinger_mavg().iloc[-1]
    bb_lower = bb_ind.bollinger_lband().iloc[-1]
    precio_actual = close.iloc[-1]
    bb_posicion = "SUPERIOR" if precio_actual >= bb_upper * 0.998 else \
                  "INFERIOR" if precio_actual <= bb_lower * 1.002 else "MEDIA"

    # EMA 9 y EMA 21
    ema9_ind  = EMAIndicator(close=close, window=9)
    ema21_ind = EMAIndicator(close=close, window=21)
    ema9  = ema9_ind.ema_indicator().iloc[-1]
    ema21 = ema21_ind.ema_indicator().iloc[-1]
    tendencia_ema = "ALCISTA" if ema9 > ema21 else "BAJISTA"

    # Volumen relativo (vs promedio de 20 velas)
    vol_actual  = vol.iloc[-1]
    vol_promedio = vol.iloc[-21:-1].mean()
    vol_relativo = (vol_actual / vol_promedio * 100) if vol_promedio > 0 else 100

    # Variación de precio (última vela)
    precio_anterior = close.iloc[-2]
    variacion_pct = ((precio_actual - precio_anterior) / precio_anterior) * 100

    # Tendencia general (últimas 5 velas)
    ultimas_5 = close.iloc[-5:]
    tendencia_5 = "ALCISTA" if ultimas_5.iloc[-1] > ultimas_5.iloc[0] else "BAJISTA"

    return {
        "simbolo":        SIMBOLO,
        "temporalidad":   temporalidad or TEMPORALIDAD,
        "timestamp":      datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "precio":         round(precio_actual, 2),
        "precio_anterior":round(precio_anterior, 2),
        "variacion_pct":  round(variacion_pct, 3),
        "rsi":            round(rsi, 2),
        "rsi_zona":       "SOBRECOMPRADO" if rsi > 70 else "SOBREVENDIDO" if rsi < 30 else "NEUTRAL",
        "macd":           round(macd_val, 4),
        "macd_signal":    round(macd_sig, 4),
        "macd_hist":      round(macd_hist, 4),
        "macd_cruce":     macd_cruce,
        "bb_upper":       round(bb_upper, 2),
        "bb_mid":         round(bb_mid, 2),
        "bb_lower":       round(bb_lower, 2),
        "bb_posicion":    bb_posicion,
        "ema9":           round(ema9, 2),
        "ema21":          round(ema21, 2),
        "tendencia_ema":  tendencia_ema,
        "volumen":        round(vol_actual, 4),
        "volumen_promedio": round(vol_promedio, 4),
        "volumen_relativo": round(vol_relativo, 1),
        "tendencia_5v":   tendencia_5,
    }


def formatear_reporte_para_ia(indicadores: dict) -> str:
    """
    Genera un reporte narrativo con los indicadores reales,
    listo para enviar al Agente Técnico (GPU 0).
    """
    i = indicadores
    signo = "+" if i["variacion_pct"] >= 0 else ""

    return f"""=== DATOS DE MERCADO EN TIEMPO REAL ===
Par: {i['simbolo']}
Temporalidad: {i['temporalidad']}
Timestamp: {i['timestamp']}
Precio actual: {i['precio']:,.2f} USDT ({signo}{i['variacion_pct']}% vs vela anterior)

=== INDICADORES TÉCNICOS ===
RSI (14): {i['rsi']}
  → Zona: {i['rsi_zona']}

MACD (12,26,9):
  → Línea MACD:    {i['macd']}
  → Línea Señal:   {i['macd_signal']}
  → Histograma:    {i['macd_hist']} ({i['macd_cruce']})

Bandas de Bollinger (20, 2):
  → Banda Superior: {i['bb_upper']:,.2f} USDT
  → Banda Media:    {i['bb_mid']:,.2f} USDT
  → Banda Inferior: {i['bb_lower']:,.2f} USDT
  → Posición del precio: {i['bb_posicion']}

Medias Móviles Exponenciales:
  → EMA 9:  {i['ema9']:,.2f} USDT
  → EMA 21: {i['ema21']:,.2f} USDT
  → Tendencia EMA: {i['tendencia_ema']}

Volumen:
  → Volumen actual:    {i['volumen']:,.2f}
  → Promedio 20 velas: {i['volumen_promedio']:,.2f}
  → Volumen relativo:  {i['volumen_relativo']}%

Tendencia últimas 5 velas: {i['tendencia_5v']}"""


def obtener_datos_completos(simbolo: str = None, temporalidad: str = None) -> tuple[dict, str]:
    """
    Función principal: obtiene velas, calcula indicadores y genera el reporte.
    Devuelve (indicadores_dict, reporte_texto).
    """
    df = obtener_velas(simbolo, temporalidad)
    indicadores = calcular_indicadores(df)
    reporte = formatear_reporte_para_ia(indicadores)
    return indicadores, reporte


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit("[bold cyan]📊 Test del módulo de mercado real[/bold cyan]"))
    console.print("[yellow]Conectando a Binance...[/yellow]")

    indicadores, reporte = obtener_datos_completos()

    tabla = Table(title=f"Indicadores reales — {indicadores['simbolo']}", show_header=False)
    tabla.add_column("Indicador", style="cyan")
    tabla.add_column("Valor", style="white")
    for k, v in indicadores.items():
        tabla.add_row(k, str(v))
    console.print(tabla)
    console.print(Panel(reporte, title="Reporte para IA", border_style="green"))
