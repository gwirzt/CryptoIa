"""
src/trading/posicion.py — Gestión del estado de la posición abierta
Persiste en PostgreSQL y calcula P&L en tiempo real
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, text
from config import DB_CONNECTION_STRING, CAPITAL_INICIAL

logger = logging.getLogger(__name__)

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_CONNECTION_STRING, pool_pre_ping=True)
    return _engine


def inicializar_db():
    """Crea las tablas necesarias si no existen."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS posicion_activa (
                id              SERIAL PRIMARY KEY,
                simbolo         VARCHAR(20) NOT NULL,
                precio_compra   DECIMAL(18,8) NOT NULL,
                cantidad        DECIMAL(18,8) NOT NULL,
                capital_usado   DECIMAL(18,2) NOT NULL,
                timestamp_compra TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ciclos          INTEGER DEFAULT 0,
                orden_id        VARCHAR(100)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS operaciones (
                id              SERIAL PRIMARY KEY,
                simbolo         VARCHAR(20) NOT NULL,
                tipo            VARCHAR(10) NOT NULL,  -- COMPRA / VENTA
                precio          DECIMAL(18,8) NOT NULL,
                cantidad        DECIMAL(18,8) NOT NULL,
                capital         DECIMAL(18,2) NOT NULL,
                pnl_pct         DECIMAL(8,4),
                pnl_usdt        DECIMAL(18,2),
                razon_ia        TEXT,
                confianza_ia    INTEGER,
                timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                orden_id        VARCHAR(100)
            )
        """))
    logger.info("Base de datos inicializada")


def obtener_posicion(simbolo: str) -> Optional[dict]:
    """
    Retorna la posición abierta para el símbolo, o None si no hay.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, simbolo, precio_compra, cantidad, capital_usado,
                   timestamp_compra, ciclos, orden_id
            FROM posicion_activa
            WHERE simbolo = :simbolo
            ORDER BY id DESC LIMIT 1
        """), {"simbolo": simbolo}).fetchone()
    
    if row is None:
        return None
    
    return {
        "id":              row[0],
        "simbolo":         row[1],
        "precio_compra":   float(row[2]),
        "cantidad":        float(row[3]),
        "capital_usado":   float(row[4]),
        "timestamp_compra": row[5],
        "ciclos_en_posicion": row[6],
        "orden_id":        row[7],
    }


def calcular_pnl(posicion: dict, precio_actual: float) -> dict:
    """Calcula P&L de la posición abierta."""
    precio_compra = posicion["precio_compra"]
    cantidad = posicion["cantidad"]
    capital_usado = posicion["capital_usado"]
    
    valor_actual = cantidad * precio_actual
    pnl_usdt = valor_actual - capital_usado
    pnl_pct = (pnl_usdt / capital_usado) * 100
    
    return {
        **posicion,
        "precio_actual": precio_actual,
        "valor_actual":  round(valor_actual, 2),
        "pnl_usdt":      round(pnl_usdt, 2),
        "pnl_pct":       round(pnl_pct, 4),
    }


def abrir_posicion(simbolo: str, precio: float, cantidad: float, capital: float, orden_id: str = None):
    """Registra una nueva posición abierta."""
    engine = get_engine()
    with engine.begin() as conn:
        # Eliminar posición anterior si existe (no debería, pero por seguridad)
        conn.execute(text("DELETE FROM posicion_activa WHERE simbolo = :s"), {"s": simbolo})
        conn.execute(text("""
            INSERT INTO posicion_activa (simbolo, precio_compra, cantidad, capital_usado, orden_id)
            VALUES (:simbolo, :precio, :cantidad, :capital, :orden_id)
        """), {
            "simbolo": simbolo,
            "precio":  precio,
            "cantidad": cantidad,
            "capital": capital,
            "orden_id": orden_id,
        })
        # Registrar en historial
        conn.execute(text("""
            INSERT INTO operaciones (simbolo, tipo, precio, cantidad, capital, orden_id)
            VALUES (:simbolo, 'COMPRA', :precio, :cantidad, :capital, :orden_id)
        """), {
            "simbolo": simbolo,
            "precio":  precio,
            "cantidad": cantidad,
            "capital": capital,
            "orden_id": orden_id,
        })
    logger.info(f"Posición abierta: {simbolo} @ ${precio:,.2f} | {cantidad:.6f} unidades | ${capital:.2f}")


def cerrar_posicion(posicion: dict, precio_venta: float, razon: str, confianza: int, orden_id: str = None):
    """Cierra la posición y registra la operación."""
    pnl_info = calcular_pnl(posicion, precio_venta)
    
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM posicion_activa WHERE id = :id"), {"id": posicion["id"]})
        conn.execute(text("""
            INSERT INTO operaciones (simbolo, tipo, precio, cantidad, capital, pnl_pct, pnl_usdt, razon_ia, confianza_ia, orden_id)
            VALUES (:simbolo, 'VENTA', :precio, :cantidad, :capital, :pnl_pct, :pnl_usdt, :razon, :confianza, :orden_id)
        """), {
            "simbolo":   posicion["simbolo"],
            "precio":    precio_venta,
            "cantidad":  posicion["cantidad"],
            "capital":   posicion["capital_usado"],
            "pnl_pct":   pnl_info["pnl_pct"],
            "pnl_usdt":  pnl_info["pnl_usdt"],
            "razon":     razon,
            "confianza": confianza,
            "orden_id":  orden_id,
        })
    
    signo = "+" if pnl_info["pnl_pct"] >= 0 else ""
    logger.info(
        f"Posición cerrada: {posicion['simbolo']} @ ${precio_venta:,.2f} | "
        f"P&L: {signo}{pnl_info['pnl_pct']:.2f}% ({signo}${pnl_info['pnl_usdt']:.2f})"
    )
    return pnl_info


def incrementar_ciclos(posicion_id: int):
    """Incrementa el contador de ciclos en posición."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE posicion_activa SET ciclos = ciclos + 1 WHERE id = :id"
        ), {"id": posicion_id})


def obtener_capital_disponible(simbolo: str) -> float:
    """
    Retorna el capital disponible para operar.
    Si hay posición abierta, retorna 0.
    """
    posicion = obtener_posicion(simbolo)
    if posicion:
        return 0.0
    return CAPITAL_INICIAL


def resumen_operaciones(simbolo: str, limite: int = 10) -> list:
    """Retorna las últimas operaciones."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tipo, precio, cantidad, capital, pnl_pct, pnl_usdt, razon_ia, timestamp
            FROM operaciones
            WHERE simbolo = :simbolo
            ORDER BY timestamp DESC
            LIMIT :limite
        """), {"simbolo": simbolo, "limite": limite}).fetchall()
    
    return [
        {
            "tipo":      row[0],
            "precio":    float(row[1]),
            "cantidad":  float(row[2]),
            "capital":   float(row[3]),
            "pnl_pct":   float(row[4]) if row[4] else None,
            "pnl_usdt":  float(row[5]) if row[5] else None,
            "razon":     row[6],
            "timestamp": str(row[7]),
        }
        for row in rows
    ]
