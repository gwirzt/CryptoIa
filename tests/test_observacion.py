"""
tests/test_observacion.py — Paper Trading 24/7 con billetera virtual
Corre en bucle continuo, consulta al comité cada N minutos y simula
operaciones de compra/venta con una billetera virtual.

Las IAs reciben contexto de la posición actual para poder recomendar VENTA.
Stop-Loss y Take-Profit automáticos actúan como red de seguridad.

Ejecutar con:
    python tests/test_observacion.py
    nohup python3 tests/test_observacion.py > logs/bot.log 2>&1 &

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
from zoneinfo import ZoneInfo
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from config import (
    SERVIDOR_IA,
    PUERTO_GPU0, MODELO_GPU0,
    PUERTO_GPU1, MODELO_GPU1,
    PUERTO_GPU2, MODELO_GPU2,
    CAPITAL_INICIAL,
    TEMPORALIDAD,
    INTERVALO_MINUTOS,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TIMEZONE,
)

console = Console()

# Zona horaria Argentina
try:
    TZ_BA = ZoneInfo(TIMEZONE)
except Exception:
    TZ_BA = timezone.utc

# ============================================================
# CONFIGURACIÓN
# ============================================================
TIMEOUT_IA  = 90
CSV_PATH    = "logs/observacion.csv"
CSV_HEADERS = [
    "timestamp", "ciclo", "precio_btc", "rsi", "rsi_zona",
    "macd_cruce", "bb_posicion", "tendencia_ema", "volumen_relativo",
    "decision_tecnico", "confianza_tecnico",
    "decision_fundamental", "intensidad_fundamental",
    "decision_final", "stop_loss_pct", "take_profit_pct",
    "justificacion_tecnico", "justificacion_fundamental", "motivo_riesgo",
    "tiempo_ciclo_seg", "noticias_count", "error",
    # Campos de billetera
    "billetera_usdt", "billetera_btc", "billetera_valor_total",
    "billetera_rendimiento_pct", "billetera_en_posicion",
]

# ============================================================
# BILLETERA VIRTUAL (paper trading)
# ============================================================
billetera = {
    "usdt":           CAPITAL_INICIAL,
    "btc":            0.0,
    "precio_compra":  0.0,
    "sl_pct":         STOP_LOSS_PCT,
    "tp_pct":         TAKE_PROFIT_PCT,
    "en_posicion":    False,
    "operaciones":    [],
    "ganancia_total": 0.0,
}


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def ahora_ba() -> datetime:
    """Retorna datetime actual en zona horaria Buenos Aires."""
    return datetime.now(TZ_BA)


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


def valor_total_billetera(precio_btc: float) -> float:
    """Calcula el valor total de la billetera en USDT."""
    return billetera["usdt"] + (billetera["btc"] * precio_btc)


def rendimiento_pct(precio_btc: float) -> float:
    """Calcula el rendimiento porcentual respecto al capital inicial."""
    vt = valor_total_billetera(precio_btc)
    return ((vt - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100


def ejecutar_compra(precio: float, ciclo: int, motivo: str = ""):
    """Ejecuta una compra virtual con todo el capital disponible."""
    global billetera
    if billetera["en_posicion"] or billetera["usdt"] < 10:
        return False
    btc_comprado = billetera["usdt"] / precio
    billetera["btc"] = btc_comprado
    billetera["precio_compra"] = precio
    billetera["en_posicion"] = True
    billetera["usdt"] = 0.0
    billetera["operaciones"].append({
        "ciclo": ciclo, "tipo": "COMPRA",
        "precio": precio, "btc": round(btc_comprado, 6),
        "motivo": motivo,
        "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
    })
    console.print(f"   [bold green]📈 COMPRA: {btc_comprado:.6f} BTC a ${precio:,.2f} USDT[/bold green]")
    console.print(f"   [dim]   Motivo: {motivo[:80]}[/dim]")
    return True


def ejecutar_venta(precio: float, ciclo: int, tipo: str = "VENTA", motivo: str = ""):
    """Ejecuta una venta virtual de todo el BTC en posición."""
    global billetera
    if not billetera["en_posicion"] or billetera["btc"] <= 0:
        return False
    usdt_obtenido = billetera["btc"] * precio
    ganancia = usdt_obtenido - (billetera["btc"] * billetera["precio_compra"])
    ganancia_pct = ((precio - billetera["precio_compra"]) / billetera["precio_compra"]) * 100
    billetera["usdt"] = usdt_obtenido
    billetera["ganancia_total"] += ganancia
    billetera["operaciones"].append({
        "ciclo": ciclo, "tipo": tipo,
        "precio": precio, "ganancia": round(ganancia, 2),
        "ganancia_pct": round(ganancia_pct, 2),
        "motivo": motivo,
        "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
    })
    billetera["btc"] = 0.0
    billetera["en_posicion"] = False
    billetera["precio_compra"] = 0.0

    color = "green" if ganancia >= 0 else "red"
    signo = "+" if ganancia >= 0 else ""
    console.print(f"   [bold {color}]📉 {tipo}: ${precio:,.2f} | "
                  f"P&L: {signo}${ganancia:,.2f} ({signo}{ganancia_pct:.2f}%)[/bold {color}]")
    console.print(f"   [dim]   Motivo: {motivo[:80]}[/dim]")
    return True


def verificar_sl_tp(precio: float, ciclo: int) -> str | None:
    """
    Verifica si se activó Stop-Loss o Take-Profit automático.
    Retorna 'SL', 'TP' o None.
    """
    if not billetera["en_posicion"] or billetera["precio_compra"] <= 0:
        return None

    precio_compra = billetera["precio_compra"]
    sl_precio = precio_compra * (1 - billetera["sl_pct"] / 100)
    tp_precio = precio_compra * (1 + billetera["tp_pct"] / 100)

    if precio <= sl_precio:
        motivo = (f"Stop-Loss automático: precio ${precio:,.2f} ≤ SL ${sl_precio:,.2f} "
                  f"(-{billetera['sl_pct']}% desde compra)")
        console.print(f"   [bold red]🛑 STOP-LOSS activado en ${precio:,.2f} "
                      f"(SL era ${sl_precio:,.2f})[/bold red]")
        ejecutar_venta(precio, ciclo, "VENTA_SL", motivo)
        return "SL"

    if precio >= tp_precio:
        motivo = (f"Take-Profit automático: precio ${precio:,.2f} ≥ TP ${tp_precio:,.2f} "
                  f"(+{billetera['tp_pct']}% desde compra)")
        console.print(f"   [bold green]🎯 TAKE-PROFIT activado en ${precio:,.2f} "
                      f"(TP era ${tp_precio:,.2f})[/bold green]")
        ejecutar_venta(precio, ciclo, "VENTA_TP", motivo)
        return "TP"

    return None


def mostrar_billetera(precio_actual: float):
    """Muestra el estado actual de la billetera virtual."""
    vt = valor_total_billetera(precio_actual)
    rend = rendimiento_pct(precio_actual)
    color_r = "green" if rend >= 0 else "red"
    signo = "+" if rend >= 0 else ""

    tabla = Table(title="💰 Billetera Virtual (Paper Trading)", show_header=False, box=None,
                  padding=(0, 1))
    tabla.add_column("Campo", style="cyan", width=22)
    tabla.add_column("Valor", style="white")

    tabla.add_row("Capital inicial",  f"${CAPITAL_INICIAL:,.2f} USDT")
    tabla.add_row("USDT disponible",  f"${billetera['usdt']:,.2f} USDT")
    tabla.add_row("BTC en posición",
                  f"{billetera['btc']:.6f} BTC (${billetera['btc']*precio_actual:,.2f})")
    tabla.add_row("Valor total",      f"${vt:,.2f} USDT")
    tabla.add_row("Rendimiento",      f"[{color_r}]{signo}{rend:.2f}%[/{color_r}]")
    tabla.add_row("Operaciones",      str(len(billetera["operaciones"])))
    tabla.add_row("Ganancia acum.",   f"${billetera['ganancia_total']:,.2f} USDT")

    if billetera["en_posicion"]:
        pc = billetera["precio_compra"]
        sl_p = pc * (1 - billetera["sl_pct"] / 100)
        tp_p = pc * (1 + billetera["tp_pct"] / 100)
        pnl_actual = (precio_actual - pc) / pc * 100
        color_pnl = "green" if pnl_actual >= 0 else "red"
        tabla.add_row("─" * 22, "─" * 20)
        tabla.add_row("Posición abierta", f"Comprado a ${pc:,.2f}")
        tabla.add_row("P&L actual",
                      f"[{color_pnl}]{'+' if pnl_actual >= 0 else ''}{pnl_actual:.2f}%[/{color_pnl}]")
        tabla.add_row("Stop-Loss",    f"[red]${sl_p:,.2f}[/red] (-{billetera['sl_pct']}%)")
        tabla.add_row("Take-Profit",  f"[green]${tp_p:,.2f}[/green] (+{billetera['tp_pct']}%)")

    console.print(tabla)


def contexto_posicion_para_ia() -> str:
    """Genera el texto de contexto de posición actual para incluir en los prompts."""
    if billetera["en_posicion"]:
        pc = billetera["precio_compra"]
        return (
            f"POSICIÓN ACTUAL: EN POSICIÓN (comprado a ${pc:,.2f} USDT)\n"
            f"Stop-Loss configurado: -{billetera['sl_pct']}% (${pc*(1-billetera['sl_pct']/100):,.2f})\n"
            f"Take-Profit configurado: +{billetera['tp_pct']}% (${pc*(1+billetera['tp_pct']/100):,.2f})\n"
            f"Operaciones realizadas: {len(billetera['operaciones'])}"
        )
    else:
        capital = billetera["usdt"]
        return (
            f"POSICIÓN ACTUAL: SIN POSICIÓN (disponible ${capital:,.2f} USDT para comprar)\n"
            f"Operaciones realizadas: {len(billetera['operaciones'])}"
        )


# ============================================================
# CICLO PRINCIPAL DE OBSERVACIÓN
# ============================================================

def ejecutar_ciclo(ciclo: int) -> dict:
    """Ejecuta un ciclo completo de paper trading. Devuelve el registro para CSV/DB."""
    inicio = time.time()
    ts = ahora_ba().strftime("%Y-%m-%d %H:%M:%S")
    registro = {"ciclo": ciclo, "timestamp": ts}

    console.print(Rule(f"[bold cyan]CICLO #{ciclo} — {ts}[/bold cyan]"))

    # --- Datos de mercado ---
    try:
        from src.mercado.binance_client import obtener_datos_completos
        indicadores, reporte_mercado = obtener_datos_completos()
        precio = float(indicadores["precio"])
        registro["precio_btc"]       = precio
        registro["rsi"]              = float(indicadores["rsi"])
        registro["rsi_zona"]         = indicadores["rsi_zona"]
        registro["macd_cruce"]       = indicadores["macd_cruce"]
        registro["bb_posicion"]      = indicadores["bb_posicion"]
        registro["tendencia_ema"]    = indicadores["tendencia_ema"]
        registro["volumen_relativo"] = float(indicadores["volumen_relativo"])
        console.print(
            f"[cyan]📊 BTC=${precio:,.2f} | RSI={indicadores['rsi']:.1f} ({indicadores['rsi_zona']}) | "
            f"MACD={indicadores['macd_cruce']} | BB={indicadores['bb_posicion']} | "
            f"EMA={indicadores['tendencia_ema']}[/cyan]"
        )
    except Exception as e:
        console.print(f"[red]❌ Error Binance: {e}[/red]")
        registro["error"] = str(e)
        registro["tiempo_ciclo_seg"] = round(time.time() - inicio, 1)
        return registro

    # --- Verificar Stop-Loss / Take-Profit ANTES de consultar IAs ---
    sl_tp_activado = verificar_sl_tp(precio, ciclo)

    # --- Noticias ---
    try:
        from src.noticias.feed_manager import obtener_resumen_noticias
        noticias, texto_noticias = obtener_resumen_noticias()
        registro["noticias_count"] = len(noticias)
        console.print(f"[yellow]📰 {len(noticias)} noticias recientes[/yellow]")
    except Exception:
        texto_noticias = "No se pudieron obtener noticias."
        noticias = []
        registro["noticias_count"] = 0

    # --- Contexto de posición para las IAs ---
    ctx_posicion = contexto_posicion_para_ia()

    # --- Prompt Agente Técnico ---
    prompt_t = f"""Eres un analista técnico experto en criptomonedas. Analiza estos datos REALES de BTC/USDT:

{reporte_mercado}

{ctx_posicion}

Tu tarea: recomendar si COMPRAR, VENDER o ESPERAR.
- Si hay posición abierta y los indicadores se deterioran → recomienda VENTA
- Si no hay posición y los indicadores son alcistas → recomienda COMPRA
- Si la situación es incierta → recomienda ESPERAR

Responde SOLO con JSON válido:
{{"accion": "COMPRA", "confianza": 75, "justificacion": "texto breve"}}
Donde "accion" es exactamente COMPRA, VENTA o ESPERAR."""

    # --- Prompt Agente Fundamental ---
    prompt_f = f"""Eres un analista fundamental de criptomonedas. Evalúa estas noticias REALES de Bitcoin:

{texto_noticias}

{ctx_posicion}

Evalúa el impacto de las noticias en el precio de Bitcoin.

Responde SOLO con JSON válido:
{{"impacto": "ALCISTA", "intensidad": 70, "justificacion": "texto breve"}}
Donde "impacto" es exactamente ALCISTA, BAJISTA o NEUTRAL."""

    # --- GPU 0: Agente Técnico ---
    datos_t, tiempo_t, _ = consultar_ia(PUERTO_GPU0, MODELO_GPU0, prompt_t)
    if datos_t:
        accion_t    = datos_t.get("accion", "ESPERAR").upper()
        if accion_t not in ("COMPRA", "VENTA", "ESPERAR"):
            accion_t = "ESPERAR"
        confianza_t = int(datos_t.get("confianza", 50))
        just_t      = str(datos_t.get("justificacion", ""))
        color_t = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(accion_t, "white")
        console.print(f"[dim]🔵 GPU0 ({tiempo_t:.1f}s):[/dim] [{color_t}]{accion_t}[/{color_t}] "
                      f"({confianza_t}%) — {just_t[:80]}")
    else:
        accion_t, confianza_t, just_t = "ESPERAR", 0, "Error GPU0"
        console.print("[red]❌ GPU0 sin respuesta[/red]")

    registro["decision_tecnico"]      = accion_t
    registro["confianza_tecnico"]     = confianza_t
    registro["justificacion_tecnico"] = just_t[:300]

    # --- GPU 1: Agente Fundamental ---
    datos_f, tiempo_f, _ = consultar_ia(PUERTO_GPU1, MODELO_GPU1, prompt_f)
    if datos_f:
        impacto_f    = datos_f.get("impacto", "NEUTRAL").upper()
        if impacto_f not in ("ALCISTA", "BAJISTA", "NEUTRAL"):
            impacto_f = "NEUTRAL"
        intensidad_f = int(datos_f.get("intensidad", 50))
        just_f       = str(datos_f.get("justificacion", ""))
        color_f = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(impacto_f, "white")
        console.print(f"[dim]🟡 GPU1 ({tiempo_f:.1f}s):[/dim] [{color_f}]{impacto_f}[/{color_f}] "
                      f"({intensidad_f}%) — {just_f[:80]}")
    else:
        impacto_f, intensidad_f, just_f = "NEUTRAL", 0, "Error GPU1"
        console.print("[red]❌ GPU1 sin respuesta[/red]")

    registro["decision_fundamental"]      = impacto_f
    registro["intensidad_fundamental"]    = intensidad_f
    registro["justificacion_fundamental"] = just_f[:300]

    # --- GPU 2: Gestor de Riesgos (con contexto de posición) ---
    # Calcular P&L actual si hay posición
    pnl_str = ""
    if billetera["en_posicion"]:
        pc = billetera["precio_compra"]
        pnl_actual = (precio - pc) / pc * 100
        pnl_str = f"\nP&L actual de la posición: {'+' if pnl_actual >= 0 else ''}{pnl_actual:.2f}%"

    prompt_r = f"""Eres el Gestor de Riesgos de un bot de paper trading de Bitcoin. Toma la decisión final.

DATOS DEL MERCADO:
- Precio BTC: ${precio:,.2f} USDT
- RSI: {registro.get('rsi', 'N/A')} ({registro.get('rsi_zona', 'N/A')})
- MACD: {registro.get('macd_cruce', 'N/A')}
- Tendencia EMA: {registro.get('tendencia_ema', 'N/A')}

ANÁLISIS DE LOS AGENTES:
- Técnico: {accion_t} (confianza: {confianza_t}%) — {just_t[:100]}
- Fundamental: {impacto_f} (intensidad: {intensidad_f}%) — {just_f[:100]}

{ctx_posicion}{pnl_str}

REGLAS DE DECISIÓN:
1. Si hay posición abierta Y (técnico dice VENTA O RSI > 70 O MACD negativo con pérdida) → VENTA
2. Si NO hay posición Y técnico dice COMPRA con confianza > 60 → COMPRA
3. En caso de duda → ESPERAR

Responde SOLO con JSON válido:
{{"decision": "ESPERAR", "stop_loss_pct": 2.5, "take_profit_pct": 5.0, "motivo": "texto breve"}}
Donde "decision" es exactamente COMPRA, VENTA o ESPERAR."""

    datos_r, tiempo_r, _ = consultar_ia(PUERTO_GPU2, MODELO_GPU2, prompt_r)
    if datos_r:
        decision_r = str(datos_r.get("decision", "ESPERAR")).upper()
        if decision_r not in ("COMPRA", "VENTA", "ESPERAR"):
            decision_r = "ESPERAR"
        sl_r   = float(datos_r.get("stop_loss_pct", STOP_LOSS_PCT))
        tp_r   = float(datos_r.get("take_profit_pct", TAKE_PROFIT_PCT))
        motivo_r = str(datos_r.get("motivo") or datos_r.get("razon") or
                       datos_r.get("justificacion") or "Sin motivo")
        color_r = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(decision_r, "white")
        console.print(f"[dim]🔴 GPU2 ({tiempo_r:.1f}s):[/dim] "
                      f"[bold {color_r}]{decision_r}[/bold {color_r}] "
                      f"SL:-{sl_r}% TP:+{tp_r}%")
    else:
        decision_r, sl_r, tp_r, motivo_r = "ESPERAR", STOP_LOSS_PCT, TAKE_PROFIT_PCT, "Error GPU2"
        console.print("[red]❌ GPU2 sin respuesta[/red]")

    registro["decision_final"]  = decision_r
    registro["stop_loss_pct"]   = sl_r
    registro["take_profit_pct"] = tp_r
    registro["motivo_riesgo"]   = motivo_r[:300]

    # Actualizar SL/TP de la billetera con los valores del Gestor de Riesgos
    billetera["sl_pct"] = sl_r
    billetera["tp_pct"] = tp_r

    # --- Ejecutar decisión (solo si SL/TP no se activó ya) ---
    if not sl_tp_activado:
        if decision_r == "COMPRA":
            ejecutar_compra(precio, ciclo, motivo_r)
        elif decision_r == "VENTA":
            ejecutar_venta(precio, ciclo, "VENTA", motivo_r)

    # --- Mostrar estado de billetera ---
    mostrar_billetera(precio)

    # --- Agregar datos de billetera al registro ---
    vt = valor_total_billetera(precio)
    registro["billetera_usdt"]          = round(billetera["usdt"], 2)
    registro["billetera_btc"]           = round(billetera["btc"], 8)
    registro["billetera_valor_total"]   = round(vt, 2)
    registro["billetera_rendimiento_pct"] = round(rendimiento_pct(precio), 4)
    registro["billetera_en_posicion"]   = billetera["en_posicion"]

    registro["tiempo_ciclo_seg"] = round(time.time() - inicio, 1)
    return registro


# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def main():
    db_disponible = False
    try:
        from src.trading.base_datos import verificar_conexion, crear_tablas
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
        "[bold cyan]🤖 PAPER TRADING 24/7 — CryptoIA[/bold cyan]\n"
        f"Capital virtual: [bold green]${CAPITAL_INICIAL:,.2f} USDT[/bold green] | "
        f"Intervalo: [yellow]{INTERVALO_MINUTOS} min[/yellow] | "
        f"Temporalidad: [yellow]{TEMPORALIDAD}[/yellow]\n"
        f"Stop-Loss: [red]-{STOP_LOSS_PCT}%[/red] | "
        f"Take-Profit: [green]+{TAKE_PROFIT_PCT}%[/green]\n"
        f"DB: [yellow]{'PostgreSQL ✅' if db_disponible else 'No disponible ⚠️'}[/yellow] | "
        f"CSV: [yellow]{CSV_PATH}[/yellow]\n"
        "[bold red]⚠️  SOLO SIMULACIÓN — No se ejecutan operaciones reales[/bold red]\n"
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
                guardar_en_csv(registro)

                if db_disponible:
                    try:
                        from src.trading.base_datos import guardar_ciclo, guardar_estado_billetera
                        ok_db = guardar_ciclo(registro)
                        precio = registro.get("precio_btc", 0)
                        if ok_db and precio:
                            guardar_estado_billetera(billetera, ciclo, float(precio), "CICLO")
                            console.print(f"[dim]💾 Guardado en PostgreSQL + CSV (ciclo #{ciclo})[/dim]")
                        else:
                            console.print(f"[dim]💾 Guardado en CSV (DB falló) (ciclo #{ciclo})[/dim]")
                    except Exception as e_db:
                        console.print(f"[yellow]⚠️  Error guardando en DB: {e_db}[/yellow]")
                else:
                    console.print(f"[dim]💾 Guardado en CSV (ciclo #{ciclo})[/dim]")

                ciclo += 1

            except Exception as e:
                console.print(f"[red]❌ Error en ciclo #{ciclo}: {e}[/red]")
                err_registro = {
                    "ciclo": ciclo, "error": str(e),
                    "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
                }
                guardar_en_csv(err_registro)
                if db_disponible:
                    try:
                        from src.trading.base_datos import guardar_ciclo
                        guardar_ciclo(err_registro)
                    except Exception:
                        pass
                ciclo += 1

            proxima_ejecucion = time.time() + (INTERVALO_MINUTOS * 60)
            console.print(
                f"\n[dim]⏳ Próximo ciclo en {INTERVALO_MINUTOS} minutos "
                f"({datetime.fromtimestamp(proxima_ejecucion, tz=TZ_BA).strftime('%H:%M:%S')})[/dim]\n"
            )

        # Cuenta regresiva
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
        console.print("\n\n[bold yellow]🛑 Paper trading detenido.[/bold yellow]")
        console.print(f"[dim]Registros guardados en: {CSV_PATH}[/dim]")

        # Resumen final
        if billetera["operaciones"]:
            console.print(f"\n[bold]📊 Resumen de operaciones:[/bold]")
            for op in billetera["operaciones"]:
                tipo = op["tipo"]
                color = "green" if tipo in ("VENTA_TP", "VENTA") else "red" if tipo == "VENTA_SL" else "cyan"
                ganancia_str = (f" | P&L: ${op.get('ganancia', 0):+,.2f} "
                                f"({op.get('ganancia_pct', 0):+.2f}%)"
                                if "ganancia" in op else "")
                console.print(
                    f"   [{color}]• Ciclo #{op['ciclo']}: {tipo} a "
                    f"${op['precio']:,.2f}{ganancia_str}[/{color}]"
                )
            console.print(
                f"\n[bold]Ganancia total: ${billetera['ganancia_total']:+,.2f} USDT[/bold]"
            )
        sys.exit(0)
