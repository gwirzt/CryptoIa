"""
run_bot.py — Punto de entrada del bot CryptoIA v2
Uso: python run_bot.py
"""
import sys
import os
import logging
from config import LOG_DIR, LOG_NIVEL

# ── Logging ────────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_NIVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"{LOG_DIR}/bot.log", encoding="utf-8"),
    ]
)

if __name__ == "__main__":
    from src.bot.ciclo import iniciar_bot
    iniciar_bot()
