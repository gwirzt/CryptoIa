"""
src/api/routers/billetera.py — Evolución del saldo y rendimiento

GET /billetera              → historial de saldos
GET /billetera/actual       → saldo actual (último registro)
GET /billetera/rendimiento  → rendimiento total y métricas
"""
from fastapi import APIRouter, Query
from sqlalchemy import text

router = APIRouter()


def get_engine():
    from src.trading.base_datos import get_engine as _get
    return _get()


@router.get("/")
def historial_billetera(limit: int = Query(default=100, ge=1, le=1000)):
    """Historial de evolución del saldo."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT timestamp, usdt, btc, valor_total_usdt,
                       ganancia_total, en_posicion, evento
                FROM billetera
                ORDER BY id DESC LIMIT {limit}
            """)).fetchall()

        historial = []
        for r in rows:
            historial.append({
                "timestamp":       str(r[0]),
                "usdt":            float(r[1]) if r[1] else 0,
                "btc":             float(r[2]) if r[2] else 0,
                "valor_total_usdt": float(r[3]) if r[3] else 0,
                "ganancia_total":  float(r[4]) if r[4] else 0,
                "en_posicion":     bool(r[5]),
                "evento":          r[6],
            })

        return {"total": len(historial), "historial": historial}

    except Exception as e:
        return {"error": str(e), "historial": []}


@router.get("/actual")
def saldo_actual():
    """Saldo actual de la billetera (último registro en DB)."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT timestamp, usdt, btc, valor_total_usdt,
                       ganancia_total, en_posicion, evento
                FROM billetera
                ORDER BY id DESC LIMIT 1
            """)).fetchone()

        if not row:
            return {"error": "No hay datos de billetera"}

        return {
            "timestamp":       str(row[0]),
            "usdt":            float(row[1]) if row[1] else 0,
            "btc":             float(row[2]) if row[2] else 0,
            "valor_total_usdt": float(row[3]) if row[3] else 0,
            "ganancia_total":  float(row[4]) if row[4] else 0,
            "en_posicion":     bool(row[5]),
            "evento":          row[6],
        }

    except Exception as e:
        return {"error": str(e)}


@router.get("/rendimiento")
def rendimiento():
    """Métricas de rendimiento: P&L, drawdown máximo, mejor/peor momento."""
    try:
        from config import CAPITAL_INICIAL
        engine = get_engine()
        with engine.connect() as conn:
            stats = conn.execute(text("""
                SELECT
                    MIN(valor_total_usdt) as valor_minimo,
                    MAX(valor_total_usdt) as valor_maximo,
                    (SELECT valor_total_usdt FROM billetera ORDER BY id DESC LIMIT 1) as valor_actual,
                    (SELECT valor_total_usdt FROM billetera ORDER BY id ASC LIMIT 1) as valor_inicial,
                    COUNT(*) as total_registros
                FROM billetera
                WHERE valor_total_usdt IS NOT NULL
            """)).fetchone()

        if not stats or not stats[2]:
            return {"error": "No hay datos suficientes"}

        valor_actual  = float(stats[2])
        valor_inicial = float(stats[3]) if stats[3] else CAPITAL_INICIAL
        valor_max     = float(stats[1]) if stats[1] else valor_actual
        valor_min     = float(stats[0]) if stats[0] else valor_actual

        rendimiento_total = ((valor_actual - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100
        drawdown_max      = ((valor_min - valor_max) / valor_max) * 100 if valor_max > 0 else 0

        return {
            "capital_inicial_usdt": CAPITAL_INICIAL,
            "valor_actual_usdt":    round(valor_actual, 2),
            "ganancia_total_usdt":  round(valor_actual - CAPITAL_INICIAL, 2),
            "rendimiento_total_pct": round(rendimiento_total, 2),
            "valor_maximo_usdt":    round(valor_max, 2),
            "valor_minimo_usdt":    round(valor_min, 2),
            "drawdown_maximo_pct":  round(drawdown_max, 2),
            "total_registros":      int(stats[4]) if stats[4] else 0,
        }

    except Exception as e:
        return {"error": str(e)}
