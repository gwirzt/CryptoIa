"""
src/trading/posicion.py — Gestión del estado de la posición abierta
Persiste en PostgreSQL y calcula P&L en tiempo real
Tablas: posicion_v2, operaciones_v2, ciclos_log
"""
import logging
from typing import Optional
from datetime import datetime
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
            CREATE TABLE IF NOT EXISTS posicion_v2 (
                id               SERIAL PRIMARY KEY,
                simbolo          VARCHAR(20) NOT NULL,
                precio_compra    DECIMAL(18,8) NOT NULL,
                cantidad         DECIMAL(18,8) NOT NULL,
                capital_usado    DECIMAL(18,2) NOT NULL,
                timestamp_compra TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ciclos           INTEGER DEFAULT 0,
                orden_id         VARCHAR(100),
                precio_maximo    DECIMAL(18,8),
                ultimo_stoploss  TIMESTAMPTZ
            )
        """))
        # Agregar columnas nuevas si la tabla ya existe (migración segura)
        for col, tipo in [
            ("precio_maximo",    "DECIMAL(18,8)"),
            ("ultimo_stoploss",  "TIMESTAMPTZ"),
            ("nivel_dca",        "INTEGER DEFAULT 0"),
            ("precio_dca_ultimo","DECIMAL(18,8)"),
            ("capital_total_dca","DECIMAL(18,2) DEFAULT 0"),
            ("cantidad_total_dca","DECIMAL(18,8) DEFAULT 0"),
        ]:
            try:
                conn.execute(text(
                    f"ALTER TABLE posicion_v2 ADD COLUMN IF NOT EXISTS {col} {tipo}"
                ))
            except Exception:
                pass

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS operaciones_v2 (
                id           SERIAL PRIMARY KEY,
                simbolo      VARCHAR(20) NOT NULL,
                tipo         VARCHAR(10) NOT NULL,
                precio       DECIMAL(18,8) NOT NULL,
                cantidad     DECIMAL(18,8) NOT NULL,
                capital      DECIMAL(18,2) NOT NULL,
                pnl_pct      DECIMAL(8,4),
                pnl_usdt     DECIMAL(18,2),
                razon_ia     TEXT,
                confianza_ia INTEGER,
                timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                orden_id     VARCHAR(100)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ciclos_log (
                id                SERIAL PRIMARY KEY,
                timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                simbolo           VARCHAR(20) NOT NULL DEFAULT 'BTC/USDT',
                precio_btc        DECIMAL(18,2),
                accion            VARCHAR(30),
                precio_compra_pos DECIMAL(18,2),
                pnl_pct           DECIMAL(8,4),
                pnl_usdt          DECIMAL(18,2),
                razon             TEXT,
                rsi               DECIMAL(6,2),
                macd_hist         DECIMAL(12,4),
                total_comprado    DECIMAL(18,2) DEFAULT 0,
                total_vendido     DECIMAL(18,2) DEFAULT 0,
                diferencia        DECIMAL(18,2) DEFAULT 0
            )
        """))

    logger.info("Base de datos inicializada (tablas v2 + ciclos_log)")


def obtener_posicion(simbolo: str) -> Optional[dict]:
    """Retorna la posición abierta para el símbolo, o None si no hay."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, simbolo, precio_compra, cantidad, capital_usado,
                   timestamp_compra, ciclos, orden_id, precio_maximo, ultimo_stoploss,
                   COALESCE(nivel_dca, 0), precio_dca_ultimo,
                   COALESCE(capital_total_dca, 0), COALESCE(cantidad_total_dca, 0)
            FROM posicion_v2
            WHERE simbolo = :simbolo
            ORDER BY id DESC LIMIT 1
        """), {"simbolo": simbolo}).fetchone()

    if row is None:
        return None

    return {
        "id":                 row[0],
        "simbolo":            row[1],
        "precio_compra":      float(row[2]),
        "cantidad":           float(row[3]),
        "capital_usado":      float(row[4]),
        "timestamp_compra":   row[5],
        "ciclos_en_posicion": row[6],
        "orden_id":           row[7],
        "precio_maximo":      float(row[8]) if row[8] is not None else float(row[2]),
        "ultimo_stoploss":    row[9],
        "nivel_dca":          int(row[10]),
        "precio_dca_ultimo":  float(row[11]) if row[11] is not None else None,
        "capital_total_dca":  float(row[12]),
        "cantidad_total_dca": float(row[13]),
    }


def calcular_pnl(posicion: dict, precio_actual: float) -> dict:
    """Calcula P&L de la posición abierta."""
    precio_compra = posicion["precio_compra"]
    cantidad      = posicion["cantidad"]
    capital_usado = posicion["capital_usado"]

    valor_actual = cantidad * precio_actual
    pnl_usdt     = valor_actual - capital_usado
    pnl_pct      = (pnl_usdt / capital_usado) * 100

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
        conn.execute(text("DELETE FROM posicion_v2 WHERE simbolo = :s"), {"s": simbolo})
        conn.execute(text("""
            INSERT INTO posicion_v2 (simbolo, precio_compra, cantidad, capital_usado, orden_id, precio_maximo)
            VALUES (:simbolo, :precio, :cantidad, :capital, :orden_id, :precio)
        """), {"simbolo": simbolo, "precio": precio, "cantidad": cantidad,
               "capital": capital, "orden_id": orden_id})
        conn.execute(text("""
            INSERT INTO operaciones_v2 (simbolo, tipo, precio, cantidad, capital, orden_id)
            VALUES (:simbolo, 'COMPRA', :precio, :cantidad, :capital, :orden_id)
        """), {"simbolo": simbolo, "precio": precio, "cantidad": cantidad,
               "capital": capital, "orden_id": orden_id})
    logger.info(f"Posición abierta: {simbolo} @ ${precio:,.2f} | {cantidad:.6f} u | ${capital:.2f}")


def cerrar_posicion(posicion: dict, precio_venta: float, razon: str, confianza: int, orden_id: str = None):
    """Cierra la posición y registra la operación."""
    pnl_info = calcular_pnl(posicion, precio_venta)

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM posicion_v2 WHERE id = :id"), {"id": posicion["id"]})
        conn.execute(text("""
            INSERT INTO operaciones_v2
                (simbolo, tipo, precio, cantidad, capital, pnl_pct, pnl_usdt, razon_ia, confianza_ia, orden_id)
            VALUES
                (:simbolo, 'VENTA', :precio, :cantidad, :capital, :pnl_pct, :pnl_usdt, :razon, :confianza, :orden_id)
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
            "UPDATE posicion_v2 SET ciclos = ciclos + 1 WHERE id = :id"
        ), {"id": posicion_id})


def actualizar_precio_maximo(posicion_id: int, precio_actual: float):
    """Actualiza el precio máximo alcanzado si el precio actual es mayor."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE posicion_v2
            SET precio_maximo = GREATEST(COALESCE(precio_maximo, precio_compra), :precio)
            WHERE id = :id
        """), {"precio": precio_actual, "id": posicion_id})


def registrar_ultimo_stoploss(simbolo: str):
    """Guarda en una tabla auxiliar el timestamp del último stop-loss para cooldown."""
    engine = get_engine()
    with engine.begin() as conn:
        # Usamos una tabla de estado simple: un registro por símbolo
        conn.execute(text("""
            INSERT INTO ciclos_log (simbolo, accion, timestamp, precio_btc, total_comprado, total_vendido, diferencia)
            VALUES (:simbolo, 'STOPLOSS_MARKER', NOW(), 0, 0, 0, 0)
        """), {"simbolo": simbolo})


def ciclos_desde_ultimo_stoploss(simbolo: str) -> int:
    """Retorna cuántos ciclos pasaron desde el último stop-loss registrado."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT COUNT(*) FROM ciclos_log
            WHERE simbolo = :simbolo
              AND accion != 'STOPLOSS_MARKER'
              AND timestamp > (
                  SELECT COALESCE(MAX(timestamp), '2000-01-01')
                  FROM ciclos_log
                  WHERE simbolo = :simbolo AND accion = 'STOPLOSS_MARKER'
              )
        """), {"simbolo": simbolo}).fetchone()
    return int(row[0]) if row else 999


def registrar_ciclo(
    simbolo: str,
    precio_btc: float,
    accion: str,
    precio_compra_pos: Optional[float],
    pnl_pct: Optional[float],
    pnl_usdt: Optional[float],
    razon: str,
    rsi: float,
    macd_hist: float,
):
    """Registra el resultado de un ciclo de 7 minutos en ciclos_log."""
    engine = get_engine()
    with engine.connect() as conn:
        # Calcular totales acumulados de operaciones
        row = conn.execute(text("""
            SELECT
                COALESCE(SUM(CASE WHEN tipo = 'COMPRA' THEN capital ELSE 0 END), 0) AS total_comprado,
                COALESCE(SUM(CASE WHEN tipo = 'VENTA'  THEN capital + COALESCE(pnl_usdt, 0) ELSE 0 END), 0) AS total_vendido
            FROM operaciones_v2
            WHERE simbolo = :simbolo
        """), {"simbolo": simbolo}).fetchone()

    total_comprado = float(row[0]) if row else 0.0
    total_vendido  = float(row[1]) if row else 0.0
    diferencia     = total_vendido - total_comprado

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ciclos_log
                (simbolo, precio_btc, accion, precio_compra_pos, pnl_pct, pnl_usdt,
                 razon, rsi, macd_hist, total_comprado, total_vendido, diferencia)
            VALUES
                (:simbolo, :precio_btc, :accion, :precio_compra_pos, :pnl_pct, :pnl_usdt,
                 :razon, :rsi, :macd_hist, :total_comprado, :total_vendido, :diferencia)
        """), {
            "simbolo":          simbolo,
            "precio_btc":       precio_btc,
            "accion":           accion,
            "precio_compra_pos": precio_compra_pos,
            "pnl_pct":          pnl_pct,
            "pnl_usdt":         pnl_usdt,
            "razon":            razon,
            "rsi":              rsi,
            "macd_hist":        macd_hist,
            "total_comprado":   total_comprado,
            "total_vendido":    total_vendido,
            "diferencia":       diferencia,
        })


def obtener_ciclos_log(simbolo: str, fecha: Optional[str] = None, limite: int = 200) -> list:
    """Retorna el historial de ciclos. Si fecha es None, usa hoy."""
    engine = get_engine()
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT timestamp, precio_btc, accion, precio_compra_pos,
                   pnl_pct, pnl_usdt, razon, rsi, macd_hist,
                   total_comprado, total_vendido, diferencia
            FROM ciclos_log
            WHERE simbolo = :simbolo
              AND accion != 'STOPLOSS_MARKER'
              AND DATE(timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires') = :fecha::date
            ORDER BY timestamp DESC
            LIMIT :limite
        """), {"simbolo": simbolo, "fecha": fecha, "limite": limite}).fetchall()

    return [
        {
            "timestamp":        str(row[0]),
            "precio_btc":       float(row[1]) if row[1] else None,
            "accion":           row[2],
            "precio_compra_pos": float(row[3]) if row[3] else None,
            "pnl_pct":          float(row[4]) if row[4] is not None else None,
            "pnl_usdt":         float(row[5]) if row[5] is not None else None,
            "razon":            row[6],
            "rsi":              float(row[7]) if row[7] else None,
            "macd_hist":        float(row[8]) if row[8] else None,
            "total_comprado":   float(row[9]) if row[9] else 0.0,
            "total_vendido":    float(row[10]) if row[10] else 0.0,
            "diferencia":       float(row[11]) if row[11] else 0.0,
        }
        for row in rows
    ]


def obtener_ciclos_log_rango(simbolo: str, fecha_desde: str, fecha_hasta: str, limite: int = 5000) -> list:
    """
    Retorna el historial de ciclos entre dos fechas (inclusive).
    fecha_desde y fecha_hasta en formato 'YYYY-MM-DD'.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT timestamp, precio_btc, accion, precio_compra_pos,
                   pnl_pct, pnl_usdt, razon, rsi, macd_hist,
                   total_comprado, total_vendido, diferencia
            FROM ciclos_log
            WHERE simbolo = :simbolo
              AND accion != 'STOPLOSS_MARKER'
              AND DATE(timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires') >= :fecha_desde::date
              AND DATE(timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires') <= :fecha_hasta::date
            ORDER BY timestamp ASC
            LIMIT :limite
        """), {"simbolo": simbolo, "fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta, "limite": limite}).fetchall()

    return [
        {
            "timestamp":        str(row[0]),
            "precio_btc":       float(row[1]) if row[1] else None,
            "accion":           row[2],
            "precio_compra_pos": float(row[3]) if row[3] else None,
            "pnl_pct":          float(row[4]) if row[4] is not None else None,
            "pnl_usdt":         float(row[5]) if row[5] is not None else None,
            "razon":            row[6],
            "rsi":              float(row[7]) if row[7] else None,
            "macd_hist":        float(row[8]) if row[8] else None,
            "total_comprado":   float(row[9]) if row[9] else 0.0,
            "total_vendido":    float(row[10]) if row[10] else 0.0,
            "diferencia":       float(row[11]) if row[11] else 0.0,
        }
        for row in rows
    ]


def obtener_capital_disponible(simbolo: str) -> float:
    """Retorna el capital disponible. 0 si hay posición abierta."""
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
            FROM operaciones_v2
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
            "pnl_pct":   float(row[4]) if row[4] is not None else None,
            "pnl_usdt":  float(row[5]) if row[5] is not None else None,
            "razon":     row[6],
            "timestamp": str(row[7]),
        }
        for row in rows
    ]


def registrar_compra_dca(posicion_id: int, precio_dca: float, cantidad_dca: float, capital_dca: float):
    """
    Registra una compra DCA sobre una posición existente.
    Actualiza:
      - nivel_dca: incrementa en 1
      - precio_dca_ultimo: precio de esta compra DCA
      - precio_compra: promedio ponderado entre la posición original y el DCA
      - cantidad: suma la cantidad nueva
      - capital_usado: suma el capital nuevo
      - capital_total_dca / cantidad_total_dca: acumulados DCA
    """
    engine = get_engine()
    with engine.begin() as conn:
        # Leer estado actual para calcular el nuevo precio promedio
        row = conn.execute(text("""
            SELECT precio_compra, cantidad, capital_usado,
                   COALESCE(capital_total_dca, 0), COALESCE(cantidad_total_dca, 0)
            FROM posicion_v2 WHERE id = :id
        """), {"id": posicion_id}).fetchone()

        if row is None:
            logger.error(f"registrar_compra_dca: posicion {posicion_id} no encontrada")
            return

        precio_orig   = float(row[0])
        cantidad_orig = float(row[1])
        capital_orig  = float(row[2])
        cap_dca_acum  = float(row[3])
        cant_dca_acum = float(row[4])

        # Nuevo precio promedio ponderado
        capital_total  = capital_orig + capital_dca
        cantidad_total = cantidad_orig + cantidad_dca
        precio_promedio = capital_total / cantidad_total

        conn.execute(text("""
            UPDATE posicion_v2 SET
                precio_compra      = :precio_promedio,
                cantidad           = :cantidad_total,
                capital_usado      = :capital_total,
                nivel_dca          = COALESCE(nivel_dca, 0) + 1,
                precio_dca_ultimo  = :precio_dca,
                capital_total_dca  = :cap_dca_nuevo,
                cantidad_total_dca = :cant_dca_nuevo
            WHERE id = :id
        """), {
            "precio_promedio": precio_promedio,
            "cantidad_total":  cantidad_total,
            "capital_total":   capital_total,
            "precio_dca":      precio_dca,
            "cap_dca_nuevo":   cap_dca_acum + capital_dca,
            "cant_dca_nuevo":  cant_dca_acum + cantidad_dca,
            "id":              posicion_id,
        })

        # Registrar en operaciones_v2 como COMPRA_DCA
        conn.execute(text("""
            INSERT INTO operaciones_v2 (simbolo, tipo, precio, cantidad, capital)
            SELECT simbolo, 'COMPRA_DCA', :precio, :cantidad, :capital
            FROM posicion_v2 WHERE id = :id
        """), {
            "precio":   precio_dca,
            "cantidad": cantidad_dca,
            "capital":  capital_dca,
            "id":       posicion_id,
        })

    logger.info(
        f"DCA registrado: +{cantidad_dca:.6f} u @ ${precio_dca:,.2f} | "
        f"Nuevo precio promedio: ${precio_promedio:,.2f} | Capital total: ${capital_total:,.2f}"
    )
