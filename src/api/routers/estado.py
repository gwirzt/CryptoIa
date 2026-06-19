"""
src/api/routers/estado.py — Estado actual del bot

GET /estado        → estado completo del bot (último ciclo + saldo)
GET /estado/agentes → estado de los 3 Ollamas (responden o no)
"""
from fastapi import APIRouter
from sqlalchemy import text
import requests
import time

router = APIRouter()


def get_db():
    from src.trading.base_datos import get_engine
    return get_engine()


@router.get("/")
def obtener_estado():
    """
    Estado actual del bot: último ciclo registrado + saldo de billetera.
    """
    try:
        engine = get_db()
        with engine.connect() as conn:
            # Último ciclo
            row_ciclo = conn.execute(text("""
                SELECT ciclo, timestamp, precio_btc, rsi, rsi_zona,
                       decision_final, tiempo_ciclo_seg, error
                FROM ciclos_observacion
                ORDER BY id DESC LIMIT 1
            """)).fetchone()

            # Último estado de billetera
            row_billetera = conn.execute(text("""
                SELECT usdt, btc, valor_total_usdt, ganancia_total,
                       en_posicion, timestamp
                FROM billetera
                ORDER BY id DESC LIMIT 1
            """)).fetchone()

            # Conteo total de ciclos
            total_ciclos = conn.execute(text(
                "SELECT COUNT(*) FROM ciclos_observacion"
            )).scalar()

        resultado = {
            "bot_activo": True,
            "total_ciclos": total_ciclos,
        }

        if row_ciclo:
            resultado["ultimo_ciclo"] = {
                "ciclo":           row_ciclo[0],
                "timestamp":       str(row_ciclo[1]),
                "precio_btc":      float(row_ciclo[2]) if row_ciclo[2] else None,
                "rsi":             float(row_ciclo[3]) if row_ciclo[3] else None,
                "rsi_zona":        row_ciclo[4],
                "decision_final":  row_ciclo[5],
                "tiempo_ciclo_seg": float(row_ciclo[6]) if row_ciclo[6] else None,
                "error":           row_ciclo[7],
            }

        if row_billetera:
            resultado["billetera"] = {
                "usdt":            float(row_billetera[0]) if row_billetera[0] else 0,
                "btc":             float(row_billetera[1]) if row_billetera[1] else 0,
                "valor_total_usdt": float(row_billetera[2]) if row_billetera[2] else 0,
                "ganancia_total":  float(row_billetera[3]) if row_billetera[3] else 0,
                "en_posicion":     bool(row_billetera[4]),
                "timestamp":       str(row_billetera[5]),
            }

        return resultado

    except Exception as e:
        return {"bot_activo": False, "error": str(e)}


@router.get("/agentes")
def estado_agentes():
    """
    Verifica si los 3 agentes Ollama están respondiendo.
    """
    from config import SERVIDOR_IA, PUERTO_GPU0, PUERTO_GPU1, PUERTO_GPU2
    from config import MODELO_GPU0, MODELO_GPU1, MODELO_GPU2

    agentes = [
        {"nombre": "Técnico",     "puerto": PUERTO_GPU0, "modelo": MODELO_GPU0},
        {"nombre": "Fundamental", "puerto": PUERTO_GPU1, "modelo": MODELO_GPU1},
        {"nombre": "Riesgo",      "puerto": PUERTO_GPU2, "modelo": MODELO_GPU2},
    ]

    resultados = []
    for ag in agentes:
        inicio = time.time()
        try:
            resp = requests.get(
                f"http://{SERVIDOR_IA}:{ag['puerto']}/api/tags",
                timeout=5
            )
            ok = resp.status_code == 200
            modelos = [m["name"] for m in resp.json().get("models", [])] if ok else []
        except Exception as ex:
            ok = False
            modelos = []
            str(ex)

        resultados.append({
            "nombre":    ag["nombre"],
            "puerto":    ag["puerto"],
            "modelo":    ag["modelo"],
            "online":    ok,
            "modelos":   modelos,
            "latencia_ms": round((time.time() - inicio) * 1000),
        })

    todos_ok = all(r["online"] for r in resultados)
    return {
        "todos_online": todos_ok,
        "agentes": resultados,
    }
