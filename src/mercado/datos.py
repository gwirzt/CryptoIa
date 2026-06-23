"""
src/mercado/datos.py — Obtiene velas OHLCV y calcula indicadores técnicos
Sin dependencias externas de TA — todo calculado con pandas puro
"""
import ccxt
import pandas as pd
from config import EXCHANGE, SIMBOLO, TEMPORALIDAD, BINANCE_API_KEY, BINANCE_SECRET, BINANCE_TESTNET


def get_exchange(con_auth: bool = False) -> ccxt.Exchange:
    """
    Crea y retorna la instancia del exchange.
    con_auth=False → solo datos públicos (velas, precio) sin API key
    con_auth=True  → con credenciales para órdenes
    """
    exchange_class = getattr(ccxt, EXCHANGE)
    if con_auth:
        params = {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET,
            "enableRateLimit": True,
        }
        if BINANCE_TESTNET:
            params["options"] = {"defaultType": "spot"}
            params["urls"] = {
                "api": {
                    "public":  "https://testnet.binance.vision/api",
                    "private": "https://testnet.binance.vision/api",
                }
            }
    else:
        # Sin credenciales — solo endpoints públicos (producción)
        params = {"enableRateLimit": True}
    return exchange_class(params)


# ── Funciones de indicadores (pandas puro) ─────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def _bbands(series: pd.Series, period=20, std=2):
    mid = series.rolling(period).mean()
    sigma = series.rolling(period).std()
    upper = mid + std * sigma
    lower = mid - std * sigma
    return upper, mid, lower


def obtener_velas(limite: int = 100) -> pd.DataFrame:
    """
    Descarga las últimas `limite` velas OHLCV y calcula indicadores.
    """
    exchange = get_exchange()
    ohlcv = exchange.fetch_ohlcv(SIMBOLO, TEMPORALIDAD, limit=limite)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    # RSI
    df["rsi"] = _rsi(df["close"], 14)

    # MACD
    df["macd"], df["macd_signal"], df["macd_hist"] = _macd(df["close"])

    # EMAs
    df["ema9"]  = _ema(df["close"], 9)
    df["ema21"] = _ema(df["close"], 21)
    df["ema50"] = _ema(df["close"], 50)

    # Bollinger Bands
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = _bbands(df["close"])

    return df.dropna()


def obtener_precio_actual() -> float:
    """Retorna el precio actual del símbolo."""
    exchange = get_exchange()
    ticker = exchange.fetch_ticker(SIMBOLO)
    return float(ticker["last"])


def resumen_indicadores(df: pd.DataFrame) -> dict:
    """Retorna un dict con los valores más recientes de los indicadores."""
    ultima = df.iloc[-1]
    anterior = df.iloc[-2]
    return {
        "precio":       round(float(ultima["close"]), 2),
        "rsi":          round(float(ultima["rsi"]), 1),
        "macd":         round(float(ultima["macd"]), 4),
        "macd_signal":  round(float(ultima["macd_signal"]), 4),
        "macd_hist":    round(float(ultima["macd_hist"]), 4),
        "ema9":         round(float(ultima["ema9"]), 2),
        "ema21":        round(float(ultima["ema21"]), 2),
        "ema50":        round(float(ultima["ema50"]), 2),
        "bb_upper":     round(float(ultima["bb_upper"]), 2),
        "bb_lower":     round(float(ultima["bb_lower"]), 2),
        "bb_mid":       round(float(ultima["bb_mid"]), 2),
        # Tendencia EMAs
        "ema_alcista":  bool(ultima["ema9"] > ultima["ema21"] > ultima["ema50"]),
        "ema_bajista":  bool(ultima["ema9"] < ultima["ema21"] < ultima["ema50"]),
        # MACD
        "macd_positivo": bool(ultima["macd"] > ultima["macd_signal"]),
        "macd_cruce_alcista": bool(
            ultima["macd"] > ultima["macd_signal"] and
            anterior["macd"] <= anterior["macd_signal"]
        ),
        "macd_cruce_bajista": bool(
            ultima["macd"] < ultima["macd_signal"] and
            anterior["macd"] >= anterior["macd_signal"]
        ),
        # Bollinger
        "cerca_bb_upper": bool(ultima["close"] > ultima["bb_upper"] * 0.99),
        "cerca_bb_lower": bool(ultima["close"] < ultima["bb_lower"] * 1.01),
        # Últimas 3 velas
        "ultimas_velas": [
            {
                "tiempo": str(df.index[-3]),
                "open":  round(float(df.iloc[-3]["open"]), 2),
                "close": round(float(df.iloc[-3]["close"]), 2),
                "dir":   "▲" if df.iloc[-3]["close"] > df.iloc[-3]["open"] else "▼"
            },
            {
                "tiempo": str(df.index[-2]),
                "open":  round(float(df.iloc[-2]["open"]), 2),
                "close": round(float(df.iloc[-2]["close"]), 2),
                "dir":   "▲" if df.iloc[-2]["close"] > df.iloc[-2]["open"] else "▼"
            },
            {
                "tiempo": str(df.index[-1]),
                "open":  round(float(ultima["open"]), 2),
                "close": round(float(ultima["close"]), 2),
                "dir":   "▲" if ultima["close"] > ultima["open"] else "▼"
            },
        ]
    }
