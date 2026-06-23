"""
config.py — Configuración centralizada CryptoIA v2
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Base de datos ──────────────────────────────────────────────────────────────
DB_SERVER   = os.getenv("DB_SERVER",   "192.168.1.6")
DB_PORT     = os.getenv("DB_PORT",     "5432")
DB_DATABASE = os.getenv("DB_DATABASE", "CryptoTrade")
DB_USER     = os.getenv("DB_USER",     "Crypto")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_CONNECTION_STRING = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_SERVER}:{DB_PORT}/{DB_DATABASE}"
)

# ── Ollama ─────────────────────────────────────────────────────────────────────
SERVIDOR_IA  = os.getenv("SERVIDOR_IA", "192.168.1.6")
PUERTO_IA    = int(os.getenv("PUERTO_GPU0", 11434))
MODELO_IA    = os.getenv("MODELO_GPU0", "qwen2.5:7b")
URL_IA       = f"http://{SERVIDOR_IA}:{PUERTO_IA}/api/generate"
URL_IA_TAGS  = f"http://{SERVIDOR_IA}:{PUERTO_IA}/api/tags"

# ── Binance ────────────────────────────────────────────────────────────────────
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET  = os.getenv("BINANCE_SECRET", "")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
MODO_REAL       = os.getenv("MODO_REAL", "false").lower() == "true"

# ── Trading ────────────────────────────────────────────────────────────────────
EXCHANGE          = os.getenv("EXCHANGE", "binance")
SIMBOLO           = os.getenv("SIMBOLO", "BTC/USDT")
TEMPORALIDAD      = os.getenv("TEMPORALIDAD", "5m")
CAPITAL_INICIAL   = float(os.getenv("CAPITAL_INICIAL", 10000))
INTERVALO_MINUTOS = int(os.getenv("INTERVALO_MINUTOS", 7))

# ── Gestión de riesgo ──────────────────────────────────────────────────────────
STOP_LOSS_PCT       = float(os.getenv("STOP_LOSS_PCT", 2.5))
TAKE_PROFIT_PCT     = float(os.getenv("TAKE_PROFIT_PCT", 5.0))
MAX_OPERACIONES_DIA = int(os.getenv("MAX_OPERACIONES_DIA", 5))
COOLDOWN_MINUTOS    = int(os.getenv("COOLDOWN_MINUTOS", 15))

# Trailing stop
TRAILING_STOP_ACTIVACION_PCT = float(os.getenv("TRAILING_STOP_ACTIVACION_PCT", 2.0))
TRAILING_STOP_PROTECCION_PCT = float(os.getenv("TRAILING_STOP_PROTECCION_PCT", 0.5))

# ── Zona horaria ───────────────────────────────────────────────────────────────
TIMEZONE  = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")
LOG_NIVEL = os.getenv("LOG_NIVEL", "INFO")
LOG_DIR   = "logs"
