"""
tests/test_observacion.py — Modo observación 24/7 (SIN ejecutar operaciones)
Corre en bucle continuo, consulta al comité cada N minutos y registra las decisiones
en PostgreSQL (tabla ciclos_observacion) y en logs/observacion.csv como respaldo.

Ejecutar con:
    venv\Scripts\python.exe tests\test_observacion.py

Detener con: Ctrl+C
Base de datos: PostgreSQL 192.168.1.8:5432/CryptoTrade
CSV de respaldo: logs/observacion.csv
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import csv
import requests
from datetime import datetime, timezone
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.live import Live
from config import (
    SERVIDOR_IA,
    PUERTO_GPU0, MODELO_GPU0,
    PUERTO_GPU1, MODELO_GPU1,
    PUERTO_GPU2, MODELO_GPU2,
    CAPITAL_INICIAL,
    TEMPORALIDAD
)

console = Console()

# ============================================================
# CONFIGURACIÓN DEL MODO OBSERVACIÓN
# ============================================================
INTERVALO_MINUTOS   = 15       # Cada cuántos minutos consultar al comité
TIMEOUT_IA          = 90       # Segundos de espera por respuesta de IA
CSV_PATH            = "logs/observacion.csv"
CSV_HEADERS         = [
    "timestamp", "ciclo", "precio_btc", "rsi", "rsi_zona",
    "macd_cruce", "bb_posicion", "tendencia_ema", "volumen_relativo",
    "decision_tecnico", "confianza_tecnico",
    "decision_fundamental", "intensidad_fundamental",
    "decision_final", "stop_loss_pct", "take_profit_pct",
    "justificacion_tecnico", "justificacion_fundamental", "motivo_riesgo",
    "tiempo_ciclo_seg", "noticias_count", "error"
]

# Billetera hipotética para seguimiento
billetera_hipotetica = {
    "usdt":           CAPITAL_INICIAL,
    "btc":            0.0,
    "precio_compra":  0.0,
    "en_posicion":    False,
    "operaciones":    [],
    "ganancia_total": 0.0,
}


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def consultar_ia(puerto: int, modelo: str, prompt: str) -> tuple[dict | None, float, str]:
    """Consulta a una IA Ollama. Devuelve (json_dict, tiempo_seg, texto_crudo)."""
    url = f"http://{SERVIDOR_IA}:{puerto}/api/generate"
    payload = {"model": modelo, "prompt": prompt, "stream": False, "format": "json"}
    inicio = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT_IA)
        t = time.time() - inicio
        if resp.status_code != 200:
            return None, t, f"HTTP {resp.status_code}"
        texto = resp.json().get("response", "").strip()
        try:
            return json.loads(texto), t, texto
        except json.JSONDecodeError:
            i = texto.find('{')
            f = texto.rfind('}') + 1
            if i >= 0 and f > i:
                try:
                    return json.loads(texto[i:f]), t, texto
                except json.JSONDecodeError:
                    pass
        return None, t, texto
    except Exception as e:
        return None, time.time() - inicio, str(e)


def guardar_en_csv(fila: dict):
    """Guarda una fila de resultados en el CSV de observación."""
    os.makedirs("logs", exist_ok=True)
    archivo_existe = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not archivo_existe:
            writer.writeheader()
        writer.writerow({k: fila.get(k, "") for k in CSV_HEADERS})


def simular_billetera(decision: str, precio: float, sl_pct: float, tp_pct: float, ciclo: int):
    """
    Simula qué hubiera pasado si el bot hubiera operado.
    Solo actualiza la billetera hipotética, NO ejecuta operaciones reales.
    """
    global billetera_hipotetica
    b = billetera_hipotetica

    # Verificar stop-loss o take-profit si hay posición abierta
    if b["en_posicion"] and b["precio_compra"] > 0:
        precio_sl = b["precio_compra"] * (1 - b.get("sl_pct", 2.5) / 100)
        precio_tp = b["precio_compra"] * (1 + b.get("tp_pct", 5.0) / 100)

        if precio <= precio_sl:
            # Stop-loss activado
            ganancia = (precio - b["precio_compra"]) * b["btc"]
            b["usdt"] += b["btc"] * precio
            b["ganancia_total"] += ganancia
            b["operaciones"].append({
                "ciclo": ciclo, "tipo": "VENTA_SL",
                "precio": precio, "ganancia": round(ganancia, 2)
            })
            b["btc"] = 0.0
            b["en_posicion"] = False
            b["precio_compra"] = 0.0
            console.print(f"   [red]🛑 STOP-LOSS hipotético activado en ${precio:,.2f} | Pérdida: ${ganancia:,.2f}[/red]")
            return

        elif precio >= precio_tp:
            # Take-profit activado
            ganancia = (precio - b["precio_compra"]) * b["btc"]
            b["usdt"] += b["btc"] * precio
            b["ganancia_total"] += ganancia
            b["operaciones"].append({
                "ciclo": ciclo, "tipo": "VENTA_TP",
                "precio": precio, "ganancia": round(ganancia, 2)
            })
            b["btc"] = 0.0
            b["en_posicion"] = False
            b["precio_compra"] = 0.0
            console.print(f"   [green]🎯 TAKE-PROFIT hipotético activado en ${precio:,.2f} | Ganancia: ${ganancia:,.2f}[/green]")
            return

    # Ejecutar la decisión del comité
    if decision == "COMPRA" and not b["en_posicion"] and b["usdt"] > 100:
        btc_comprado = b["usdt"] / precio
        b["btc"] = btc_comprado
        b["precio_compra"] = precio
        b["sl_pct"] = sl_pct
        b["tp_pct"] = tp_pct
        b["en_posicion"] = True
        b["usdt"] = 0.0
        b["operaciones"].append({
            "ciclo": ciclo, "tipo": "COMPRA",
            "precio": precio, "btc": round(btc_comprado, 6)
        })
        console.print(f"   [green]📈 COMPRA hipotética: {btc_comprado:.6f} BTC a ${precio:,.2f}[/green]")

    elif decision == "VENTA" and b["en_posicion"]:
        ganancia = (precio - b["precio_compra"]) * b["btc"]
        b["usdt"] += b["btc"] * precio
        b["ganancia_total"] += ganancia
        b["operaciones"].append({
            "ciclo": ciclo, "tipo": "VENTA",
            "precio": precio, "ganancia": round(ganancia, 2)
        })
        b["btc"] = 0.0
        b["en_posicion"] = False
        b["precio_compra"] = 0.0
        color_g = "green" if ganancia >= 0 else "red"
        console.print(f"   [{color_g}]📉 VENTA hipotética a ${precio:,.2f} | Ganancia: ${ganancia:,.2f}[/{color_g}]")


def mostrar_estado_billetera(precio_actual: float):
    """Muestra el estado actual de la billetera hipotética."""
    b = billetera_hipotetica
    valor_total = b["usdt"] + (b["btc"] * precio_actual)
    ganancia_pct = ((valor_total - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100

    color_g = "green" if ganancia_pct >= 0 else "red"
    signo = "+" if ganancia_pct >= 0 else ""

    tabla = Table(title="💰 Billetera Hipotética (Solo Observación)", show_header=False, box=None)
    tabla.add_column("Campo", style="cyan")
    tabla.add_column("Valor", style="white")
    tabla.add_row("Capital inicial",  f"${CAPITAL_INICIAL:,.2f} USDT")
    tabla.add_row("USDT disponible",  f"${b['usdt']:,.2f} USDT")
    tabla.add_row("BTC en posición",  f"{b['btc']:.6f} BTC (${b['btc']*precio_actual:,.2f})")
    tabla.add_row("Valor total",      f"${valor_total:,.2f} USDT")
    tabla.add_row("Rendimiento",      f"[{color_g}]{signo}{ganancia_pct:.2f}%[/{color_g}]")
    tabla.add_row("Operaciones",      str(len(b["operaciones"])))
    if b["en_posicion"]:
        tabla.add_row("Posición abierta", f"Comprado a ${b['precio_compra']:,.2f}")
        sl_precio = b["precio_compra"] * (1 - b.get("sl_pct", 2.5) / 100)
        tp_precio = b["precio_compra"] * (1 + b.get("tp_pct", 5.0) / 100)
        tabla.add_row("Stop-Loss en",  f"${sl_precio:,.2f}")
        tabla.add_row("Take-Profit en", f"${tp_precio:,.2f}")
    console.print(tabla)


# ============================================================
# CICLO PRINCIPAL DE OBSERVACIÓN
# ============================================================

def ejecutar_ciclo(ciclo: int) -> dict:
    """Ejecuta un ciclo completo de observación. Devuelve el registro para el CSV."""
    inicio = time.time()
    registro = {"ciclo": ciclo, "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

    console.print(Rule(f"[bold cyan]CICLO #{ciclo} — {registro['timestamp']}[/bold cyan]"))

    # --- Datos de mercado ---
    try:
        from src.mercado.binance_client import obtener_datos_completos
        indicadores, reporte_mercado = obtener_datos_completos()
        registro["precio_btc"]       = indicadores["precio"]
        registro["rsi"]              = indicadores["rsi"]
        registro["rsi_zona"]         = indicadores["rsi_zona"]
        registro["macd_cruce"]       = indicadores["macd_cruce"]
        registro["bb_posicion"]      = indicadores["bb_posicion"]
        registro["tendencia_ema"]    = indicadores["tendencia_ema"]
        registro["volumen_relativo"] = indicadores["volumen_relativo"]
        console.print(f"[cyan]📊 BTC=${indicadores['precio']:,.2f} | RSI={indicadores['rsi']} ({indicadores['rsi_zona']}) | "
                      f"MACD={indicadores['macd_cruce']} | BB={indicadores['bb_posicion']} | EMA={indicadores['tendencia_ema']}[/cyan]")
    except Exception as e:
        console.print(f"[red]❌ Error Binance: {e}[/red]")
        registro["error"] = str(e)
        registro["tiempo_ciclo_seg"] = round(time.time() - inicio, 1)
        return registro

    # --- Noticias ---
    try:
        from src.noticias.feed_manager import obtener_resumen_noticias
        noticias, texto_noticias = obtener_resumen_noticias()
        registro["noticias_count"] = len(noticias)
        console.print(f"[yellow]📰 {len(noticias)} noticias recientes[/yellow]")
    except Exception as e:
        texto_noticias = "No se pudieron obtener noticias."
        noticias = []
        registro["noticias_count"] = 0

    # --- Prompts ---
    prompt_t = f"""Eres un analista técnico experto en criptomonedas. Analiza estos datos REALES:

{reporte_mercado}

Responde SOLO con JSON: {{"accion": "COMPRA", "confianza": 75, "justificacion": "texto breve"}}
Donde "accion" es COMPRA, VENTA o ESPERAR. Solo el JSON."""

    prompt_f = f"""Eres un analista fundamental de criptomonedas. Evalúa estas noticias REALES de Bitcoin:

{texto_noticias}

Responde SOLO con JSON: {{"impacto": "ALCISTA", "intensidad": 70, "justificacion": "texto breve"}}
Donde "impacto" es ALCISTA, BAJISTA o NEUTRAL. Solo el JSON."""

    # --- GPU 0: Agente Técnico ---
    datos_t, tiempo_t, _ = consultar_ia(PUERTO_GPU0, MODELO_GPU0, prompt_t)
    if datos_t:
        accion_t   = datos_t.get("accion", "ESPERAR")
        confianza_t = datos_t.get("confianza", 0)
        just_t     = datos_t.get("justificacion", "")
        color_t = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(accion_t, "white")
        console.print(f"[dim]🔵 GPU0 ({tiempo_t:.1f}s):[/dim] [{color_t}]{accion_t}[/{color_t}] ({confianza_t}%) — {just_t[:80]}")
    else:
        accion_t, confianza_t, just_t = "ESPERAR", 0, "Error GPU0"
        console.print("[red]❌ GPU0 sin respuesta[/red]")

    registro["decision_tecnico"]    = accion_t
    registro["confianza_tecnico"]   = confianza_t
    registro["justificacion_tecnico"] = just_t[:200]

    # --- GPU 1: Agente Fundamental ---
    datos_f, tiempo_f, _ = consultar_ia(PUERTO_GPU1, MODELO_GPU1, prompt_f)
    if datos_f:
        impacto_f   = datos_f.get("impacto", "NEUTRAL")
        intensidad_f = datos_f.get("intensidad", 0)
        just_f      = datos_f.get("justificacion", "")
        color_f = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(impacto_f, "white")
        console.print(f"[dim]🟡 GPU1 ({tiempo_f:.1f}s):[/dim] [{color_f}]{impacto_f}[/{color_f}] ({intensidad_f}%) — {just_f[:80]}")
    else:
        impacto_f, intensidad_f, just_f = "NEUTRAL", 0, "Error GPU1"
        console.print("[red]❌ GPU1 sin respuesta[/red]")

    registro["decision_fundamental"]    = impacto_f
    registro["intensidad_fundamental"]  = intensidad_f
    registro["justificacion_fundamental"] = just_f[:200]

    # --- GPU 2: Gestor de Riesgos ---
    prompt_r = f"""Eres el Gestor de Riesgos de un bot de trading. Toma la decisión final:

ANALISTA TÉCNICO: {accion_t} (confianza: {confianza_t}%)
ANALISTA FUNDAMENTAL: {impacto_f} (intensidad: {intensidad_f}%)
PRECIO ACTUAL BTC: ${indicadores['precio']:,.2f} USDT
MODO: Solo observación — NO se ejecutarán operaciones reales

Responde SOLO con JSON: {{"decision": "COMPRA", "stop_loss_pct": 2.5, "take_profit_pct": 5.0, "motivo": "texto breve"}}
Donde "decision" es COMPRA, VENTA o ESPERAR. Solo el JSON."""

    datos_r, tiempo_r, _ = consultar_ia(PUERTO_GPU2, MODELO_GPU2, prompt_r)
    if datos_r:
        decision_r = datos_r.get("decision", "ESPERAR")
        sl_r       = datos_r.get("stop_loss_pct", 2.5)
        tp_r       = datos_r.get("take_profit_pct", 5.0)
        motivo_r   = (datos_r.get("motivo") or datos_r.get("razon") or
                      datos_r.get("justificacion") or "Sin motivo")
        color_r = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(decision_r, "white")
        console.print(f"[dim]🔴 GPU2 ({tiempo_r:.1f}s):[/dim] [bold {color_r}]{decision_r}[/bold {color_r}] SL:-{sl_r}% TP:+{tp_r}%")
    else:
        decision_r, sl_r, tp_r, motivo_r = "ESPERAR", 2.5, 5.0, "Error GPU2"
        console.print("[red]❌ GPU2 sin respuesta[/red]")

    registro["decision_final"]    = decision_r
    registro["stop_loss_pct"]     = sl_r
    registro["take_profit_pct"]   = tp_r
    registro["motivo_riesgo"]     = str(motivo_r)[:200]

    # --- Simular billetera hipotética ---
    simular_billetera(decision_r, indicadores["precio"], float(sl_r), float(tp_r), ciclo)

    # --- Mostrar estado billetera ---
    mostrar_estado_billetera(indicadores["precio"])

    registro["tiempo_ciclo_seg"] = round(time.time() - inicio, 1)
    return registro


# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def main():
    # Inicializar base de datos al arrancar
    db_disponible = False
    try:
        from src.trading.base_datos import verificar_conexion, crear_tablas, guardar_ciclo, guardar_estado_billetera
        ok, msg = verificar_conexion()
        if ok:
            crear_tablas()
            db_disponible = True
            console.print(f"[green]✅ PostgreSQL conectado — datos se guardarán en DB + CSV[/green]")
        else:
            console.print(f"[yellow]⚠️  PostgreSQL no disponible ({msg[:60]}) — solo CSV[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Error DB: {e} — solo CSV[/yellow]")

    console.print(Panel.fit(
        "[bold cyan]👁️  MODO OBSERVACIÓN 24/7 — CryptoIA[/bold cyan]\n"
        f"Intervalo: cada [yellow]{INTERVALO_MINUTOS} minutos[/yellow] | "
        f"Temporalidad: [yellow]{TEMPORALIDAD}[/yellow]\n"
        f"DB: [yellow]{'PostgreSQL ✅' if db_disponible else 'No disponible ⚠️'}[/yellow] | "
        f"CSV: [yellow]{CSV_PATH}[/yellow]\n"
        "[bold red]⚠️  SOLO OBSERVACIÓN — No se ejecutan operaciones reales[/bold red]\n"
        "Detener con: [bold]Ctrl+C[/bold]",
        border_style="cyan"
    ))

    ciclo = 1
    proxima_ejecucion = time.time()

    while True:
        ahora = time.time()

        if ahora >= proxima_ejecucion:
            try:
                registro = ejecutar_ciclo(ciclo)

                # Guardar en CSV (siempre)
                guardar_en_csv(registro)

                # Guardar en PostgreSQL (si está disponible)
                if db_disponible:
                    try:
                        from src.trading.base_datos import guardar_ciclo, guardar_estado_billetera
                        ok_db = guardar_ciclo(registro)
                        if ok_db:
                            # También guardar estado de billetera
                            precio = registro.get("precio_btc", 0)
                            if precio:
                                guardar_estado_billetera(billetera_hipotetica, ciclo, precio, "CICLO")
                            console.print(f"[dim]💾 Guardado en PostgreSQL + CSV (ciclo #{ciclo})[/dim]")
                        else:
                            console.print(f"[dim]💾 Guardado en CSV (DB falló) (ciclo #{ciclo})[/dim]")
                    except Exception as e_db:
                        console.print(f"[yellow]⚠️  Error guardando en DB: {e_db}[/yellow]")
                        console.print(f"[dim]💾 Guardado en CSV (ciclo #{ciclo})[/dim]")
                else:
                    console.print(f"[dim]💾 Guardado en CSV (ciclo #{ciclo})[/dim]")

                ciclo += 1
            except Exception as e:
                console.print(f"[red]❌ Error en ciclo #{ciclo}: {e}[/red]")
                err_registro = {"ciclo": ciclo, "error": str(e),
                                "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
                guardar_en_csv(err_registro)
                if db_disponible:
                    try:
                        from src.trading.base_datos import guardar_ciclo
                        guardar_ciclo(err_registro)
                    except Exception:
                        pass
                ciclo += 1

            proxima_ejecucion = time.time() + (INTERVALO_MINUTOS * 60)
            tiempo_espera = INTERVALO_MINUTOS * 60
            console.print(f"\n[dim]⏳ Próximo ciclo en {INTERVALO_MINUTOS} minutos "
                          f"({datetime.fromtimestamp(proxima_ejecucion).strftime('%H:%M:%S')})[/dim]\n")

        # Mostrar cuenta regresiva cada 60 segundos
        tiempo_restante = int(proxima_ejecucion - time.time())
        if tiempo_restante > 0:
            mins = tiempo_restante // 60
            segs = tiempo_restante % 60
            console.print(f"[dim]   ⏱️  Próximo ciclo en: {mins}m {segs}s[/dim]", end="\r")
            time.sleep(min(60, tiempo_restante))
        else:
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]🛑 Modo observación detenido por el usuario.[/bold yellow]")
        console.print(f"[dim]Los registros están guardados en: {CSV_PATH}[/dim]")

        # Mostrar resumen final
        b = billetera_hipotetica
        if b["operaciones"]:
            console.print(f"\n[bold]📊 Resumen de operaciones hipotéticas:[/bold]")
            for op in b["operaciones"]:
                tipo = op["tipo"]
                color = "green" if tipo in ("VENTA_TP", "VENTA") else "red" if tipo == "VENTA_SL" else "cyan"
                ganancia_str = f" | Ganancia: ${op.get('ganancia', 0):,.2f}" if "ganancia" in op else ""
                console.print(f"   [{color}]• Ciclo #{op['ciclo']}: {tipo} a ${op['precio']:,.2f}{ganancia_str}[/{color}]")
            console.print(f"\n[bold]Ganancia total hipotética: ${b['ganancia_total']:,.2f} USDT[/bold]")
        sys.exit(0)
