"""
config.py — Configuración centralizada del proyecto CryptoIA
Lee todas las variables del archivo .env y las expone como constantes.
"""
import os
from dotenv import load_dotenv

# Carga el archivo .env desde la raíz del proyecto
load_dotenv()

# ==============================================================================
# BASE DE DATOS — PostgreSQL
# ==============================================================================
DB_SERVER   = os.getenv("DB_SERVER",   "192.168.1.8")
DB_PORT     = os.getenv("DB_PORT",     "5432")
DB_DATABASE = os.getenv("DB_DATABASE", "CryptoIA")
DB_USER     = os.getenv("DB_USER",     "Crypto")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Cadena de conexión SQLAlchemy para PostgreSQL
DB_CONNECTION_STRING = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_SERVER}:{DB_PORT}/{DB_DATABASE}"
)

# ==============================================================================
# APIs EXTERNAS
# ==============================================================================
GOOGLE_API_KEY = os.getenv("API_KEY", "")

# ==============================================================================
# BINANCE — API para trading real / testnet
# ==============================================================================
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET     = os.getenv("BINANCE_SECRET", "")
BINANCE_TESTNET    = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

# MODO_REAL: false = paper trading (sin órdenes reales), true = órdenes reales en Binance
MODO_REAL          = os.getenv("MODO_REAL", "false").lower() == "true"

# ==============================================================================
# SERVIDOR DE IAs — Ollama en 192.168.1.8
# ==============================================================================
SERVIDOR_IA  = os.getenv("SERVIDOR_IA", "192.168.1.8")
PUERTO_GPU0  = int(os.getenv("PUERTO_GPU0", 11431))
PUERTO_GPU1  = int(os.getenv("PUERTO_GPU1", 11432))
PUERTO_GPU2  = int(os.getenv("PUERTO_GPU2", 11433))

MODELO_GPU0  = os.getenv("MODELO_GPU0", "qwen2.5:3b")
MODELO_GPU1  = os.getenv("MODELO_GPU1", "qwen2.5:3b")
MODELO_GPU2  = os.getenv("MODELO_GPU2", "qwen2.5:3b")

# URLs completas de cada agente Ollama
URL_GPU0 = f"http://{SERVIDOR_IA}:{PUERTO_GPU0}/api/generate"
URL_GPU1 = f"http://{SERVIDOR_IA}:{PUERTO_GPU1}/api/generate"
URL_GPU2 = f"http://{SERVIDOR_IA}:{PUERTO_GPU2}/api/generate"

# URL para verificar que Ollama está vivo (endpoint de salud)
URL_GPU0_HEALTH = f"http://{SERVIDOR_IA}:{PUERTO_GPU0}/api/tags"
URL_GPU1_HEALTH = f"http://{SERVIDOR_IA}:{PUERTO_GPU1}/api/tags"
URL_GPU2_HEALTH = f"http://{SERVIDOR_IA}:{PUERTO_GPU2}/api/tags"

# ==============================================================================
# PARÁMETROS DE TRADING
# ==============================================================================
EXCHANGE        = os.getenv("EXCHANGE", "binance")
SIMBOLO         = os.getenv("SIMBOLO", "BTC/USDT")
TEMPORALIDAD    = os.getenv("TEMPORALIDAD", "15m")
CAPITAL_INICIAL = float(os.getenv("CAPITAL_INICIAL", 10000))

# Gestión de riesgo (valores por defecto, ajustables)
STOP_LOSS_PCT            = float(os.getenv("STOP_LOSS_PCT", 2.5))      # -2.5%
TAKE_PROFIT_PCT          = float(os.getenv("TAKE_PROFIT_PCT", 5.0))    # +5.0%
MAX_OPERACIONES_DIA      = int(os.getenv("MAX_OPERACIONES_DIA", 5))
COOLDOWN_MINUTOS         = int(os.getenv("COOLDOWN_MINUTOS", 15))
INTERVALO_CICLO_SEG      = int(os.getenv("INTERVALO_CICLO_SEG", 60))   # 60 segundos entre ciclos
INTERVALO_MINUTOS        = int(os.getenv("INTERVALO_MINUTOS", 15))     # minutos entre ciclos del bot
CICLOS_MAX_EN_POSICION   = int(os.getenv("CICLOS_MAX_EN_POSICION", 8)) # máx ciclos en posición antes de forzar evaluación

# ==============================================================================
# ZONA HORARIA
# ==============================================================================
TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires")

# ==============================================================================
# LOGGING
# ==============================================================================
LOG_DIR   = "logs"
LOG_NIVEL = os.getenv("LOG_NIVEL", "INFO")   # DEBUG, INFO, WARNING, ERROR


# ==============================================================================
# VERIFICACIÓN RÁPIDA (ejecutar este archivo directamente para ver la config)
# ==============================================================================
if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    console = Console()
    tabla = Table(title="⚙️  Configuración Cargada — CryptoIA", show_header=True)
    tabla.add_column("Variable", style="cyan", no_wrap=True)
    tabla.add_column("Valor", style="green")

    tabla.add_row("DB_SERVER",      DB_SERVER)
    tabla.add_row("DB_DATABASE",    DB_DATABASE)
    tabla.add_row("DB_USER",        DB_USER)
    tabla.add_row("DB_PASSWORD",    "***" if DB_PASSWORD else "⚠️  NO DEFINIDA")
    tabla.add_row("GOOGLE_API_KEY", "***" if GOOGLE_API_KEY else "⚠️  NO DEFINIDA")
    tabla.add_row("URL_GPU0",       URL_GPU0)
    tabla.add_row("URL_GPU1",       URL_GPU1)
    tabla.add_row("URL_GPU2",       URL_GPU2)
    tabla.add_row("MODELO_GPU0",    MODELO_GPU0)
    tabla.add_row("MODELO_GPU1",    MODELO_GPU1)
    tabla.add_row("MODELO_GPU2",    MODELO_GPU2)
    tabla.add_row("EXCHANGE",       EXCHANGE)
    tabla.add_row("SIMBOLO",        SIMBOLO)
    tabla.add_row("TEMPORALIDAD",   TEMPORALIDAD)
    tabla.add_row("CAPITAL_INICIAL",str(CAPITAL_INICIAL))
    tabla.add_row("STOP_LOSS_PCT",  f"{STOP_LOSS_PCT}%")
    tabla.add_row("TAKE_PROFIT_PCT",f"{TAKE_PROFIT_PCT}%")

    console.print(tabla)
