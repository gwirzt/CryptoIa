"""
src/api/routers/operaciones.py — Historial de operaciones de compra/venta

GET /operaciones          → todas las operaciones
GET /operaciones/resumen  → P&L total, win rate, mejor/peor operación
"""
from fastapi import APIRouter, Query
from sqlalchemy import text

router = APIRouter()


def get_engine():
    from src.trading.base_datos import get_engine as _get
    return _get()


@router.get("/")
def listar_operaciones(limit: int = Query(default=50, ge=1, le=500)):
    """Retorna el historial de operaciones de compra/venta."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT id, timestamp, tipo, precio_btc, cantidad_btc,
                       usdt_total, ganancia_usdt, ganancia_pct, motivo
                FROM operaciones
                ORDER BY id DESC LIMIT {limit}
            """)).fetchall()

        operaciones = []
        for r in rows:
            operaciones.append({
                "id":           r[0],
                "timestamp":    str(r[1]),
                "tipo":         r[2],
                "precio_btc":   float(r[3]) if r[3] else None,
                "cantidad_btc": float(r[4]) if r[4] else None,
                "usdt_total":   float(r[5]) if r[5] else None,
                "ganancia_usdt": float(r[6]) if r[6] else None,
                "ganancia_pct": float(r[7]) if r[7] else None,
                "motivo":       r[8],
            })

        return {"total": len(operaciones), "operaciones": operaciones}

    except Exception as e:
        return {"error": str(e), "operaciones": []}


@router.get("/resumen")
def resumen_operaciones():
    """P&L total, win rate y estadísticas de operaciones."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Solo ventas (tienen ganancia/pérdida)
            stats = conn.execute(text("""
                SELECT
                    COUNT(*) as total_ventas,
                    SUM(ganancia_usdt) as ganancia_total,
                    AVG(ganancia_usdt) as ganancia_promedio,
                    MAX(ganancia_usdt) as mejor_operacion,
                    MIN(ganancia_usdt) as peor_operacion,
                    SUM(CASE WHEN ganancia_usdt > 0 THEN 1 ELSE 0 END) as operaciones_ganadoras,
                    SUM(CASE WHEN ganancia_usdt < 0 THEN 1 ELSE 0 END) as operaciones_perdedoras
                FROM operaciones
                WHERE tipo LIKE 'VENTA%' AND ganancia_usdt IS NOT NULL
            """)).fetchone()

            total_compras = conn.execute(text(
                "SELECT COUNT(*) FROM operaciones WHERE tipo = 'COMPRA'"
            )).scalar()

        total_ventas = int(stats[0]) if stats[0] else 0
        ganadoras    = int(stats[5]) if stats[5] else 0
        win_rate     = round((ganadoras / total_ventas * 100), 1) if total_ventas > 0 else 0

        return {
            "total_compras":          int(total_compras) if total_compras else 0,
            "total_ventas":           total_ventas,
            "ganancia_total_usdt":    round(float(stats[1]), 2) if stats[1] else 0,
            "ganancia_promedio_usdt": round(float(stats[2]), 2) if stats[2] else 0,
            "mejor_operacion_usdt":   round(float(stats[3]), 2) if stats[3] else 0,
            "peor_operacion_usdt":    round(float(stats[4]), 2) if stats[4] else 0,
            "operaciones_ganadoras":  ganadoras,
            "operaciones_perdedoras": int(stats[6]) if stats[6] else 0,
            "win_rate_pct":           win_rate,
        }

    except Exception as e:
        return {"error": str(e)}
