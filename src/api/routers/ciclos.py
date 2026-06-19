"""
src/api/routers/ciclos.py — Historial de ciclos del bot

GET /ciclos              → últimos N ciclos (default 20)
GET /ciclos/ultimo       → último ciclo registrado
GET /ciclos/estadisticas → distribución de decisiones, RSI promedio, etc.
"""
from fastapi import APIRouter, Query
from sqlalchemy import text

router = APIRouter()


def get_engine():
    from src.trading.base_datos import get_engine as _get
    return _get()


@router.get("/")
def listar_ciclos(limit: int = Query(default=20, ge=1, le=500)):
    """Retorna los últimos N ciclos registrados."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT ciclo, timestamp, precio_btc, rsi, rsi_zona,
                       macd_cruce, bb_posicion, tendencia_ema,
                       decision_tecnico, confianza_tecnico,
                       decision_fundamental, intensidad_fundamental,
                       decision_final, stop_loss_pct, take_profit_pct,
                       tiempo_ciclo_seg, noticias_count, error
                FROM ciclos_observacion
                ORDER BY id DESC LIMIT {limit}
            """)).fetchall()

        ciclos = []
        for r in rows:
            ciclos.append({
                "ciclo":               r[0],
                "timestamp":           str(r[1]),
                "precio_btc":          float(r[2]) if r[2] else None,
                "rsi":                 float(r[3]) if r[3] else None,
                "rsi_zona":            r[4],
                "macd_cruce":          r[5],
                "bb_posicion":         r[6],
                "tendencia_ema":       r[7],
                "decision_tecnico":    r[8],
                "confianza_tecnico":   int(r[9]) if r[9] else None,
                "decision_fundamental": r[10],
                "intensidad_fundamental": int(r[11]) if r[11] else None,
                "decision_final":      r[12],
                "stop_loss_pct":       float(r[13]) if r[13] else None,
                "take_profit_pct":     float(r[14]) if r[14] else None,
                "tiempo_ciclo_seg":    float(r[15]) if r[15] else None,
                "noticias_count":      int(r[16]) if r[16] else None,
                "error":               r[17],
            })
        return {"total": len(ciclos), "ciclos": ciclos}

    except Exception as e:
        return {"error": str(e), "ciclos": []}


@router.get("/ultimo")
def ultimo_ciclo():
    """Retorna el último ciclo registrado con todos los campos."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT ciclo, timestamp, precio_btc, rsi, rsi_zona,
                       macd_cruce, bb_posicion, tendencia_ema, volumen_relativo,
                       decision_tecnico, confianza_tecnico, justificacion_tecnico,
                       decision_fundamental, intensidad_fundamental, justificacion_fundamental,
                       decision_final, stop_loss_pct, take_profit_pct, motivo_riesgo,
                       tiempo_ciclo_seg, noticias_count, error
                FROM ciclos_observacion
                ORDER BY id DESC LIMIT 1
            """)).fetchone()

        if not row:
            return {"error": "No hay ciclos registrados"}

        return {
            "ciclo":                    row[0],
            "timestamp":                str(row[1]),
            "precio_btc":               float(row[2]) if row[2] else None,
            "rsi":                      float(row[3]) if row[3] else None,
            "rsi_zona":                 row[4],
            "macd_cruce":               row[5],
            "bb_posicion":              row[6],
            "tendencia_ema":            row[7],
            "volumen_relativo":         float(row[8]) if row[8] else None,
            "decision_tecnico":         row[9],
            "confianza_tecnico":        int(row[10]) if row[10] else None,
            "justificacion_tecnico":    row[11],
            "decision_fundamental":     row[12],
            "intensidad_fundamental":   int(row[13]) if row[13] else None,
            "justificacion_fundamental": row[14],
            "decision_final":           row[15],
            "stop_loss_pct":            float(row[16]) if row[16] else None,
            "take_profit_pct":          float(row[17]) if row[17] else None,
            "motivo_riesgo":            row[18],
            "tiempo_ciclo_seg":         float(row[19]) if row[19] else None,
            "noticias_count":           int(row[20]) if row[20] else None,
            "error":                    row[21],
        }

    except Exception as e:
        return {"error": str(e)}


@router.get("/estadisticas")
def estadisticas_ciclos():
    """Estadísticas agregadas de todos los ciclos."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Distribución de decisiones finales
            dist = conn.execute(text("""
                SELECT decision_final, COUNT(*) as cantidad,
                       AVG(rsi) as rsi_promedio,
                       AVG(confianza_tecnico) as confianza_promedio
                FROM ciclos_observacion
                WHERE decision_final IS NOT NULL
                GROUP BY decision_final
                ORDER BY cantidad DESC
            """)).fetchall()

            # Totales
            totales = conn.execute(text("""
                SELECT COUNT(*) as total,
                       AVG(precio_btc) as precio_promedio,
                       MIN(precio_btc) as precio_min,
                       MAX(precio_btc) as precio_max,
                       AVG(tiempo_ciclo_seg) as tiempo_promedio_seg
                FROM ciclos_observacion
                WHERE precio_btc IS NOT NULL
            """)).fetchone()

        distribucion = []
        for r in dist:
            distribucion.append({
                "decision":          r[0],
                "cantidad":          int(r[1]),
                "rsi_promedio":      round(float(r[2]), 2) if r[2] else None,
                "confianza_promedio": round(float(r[3]), 1) if r[3] else None,
            })

        return {
            "distribucion_decisiones": distribucion,
            "totales": {
                "ciclos_totales":      int(totales[0]) if totales[0] else 0,
                "precio_promedio":     round(float(totales[1]), 2) if totales[1] else None,
                "precio_min":          round(float(totales[2]), 2) if totales[2] else None,
                "precio_max":          round(float(totales[3]), 2) if totales[3] else None,
                "tiempo_promedio_seg": round(float(totales[4]), 1) if totales[4] else None,
            }
        }

    except Exception as e:
        return {"error": str(e)}
