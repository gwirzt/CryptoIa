"""
tests/test_observacion.py — Paper Trading 24/7 con billetera virtual y position sizing
Corre en bucle continuo, consulta al comité cada N minutos y simula
operaciones de compra/venta con una billetera virtual.

LÓGICA DE DECISIÓN:
  - SIN POSICIÓN: Técnico=COMPRA + confianza≥65% + Fundamental≠BAJISTA → COMPRA directa
  - CON POSICIÓN: GPU2 evalúa si vender. Además hay reglas automáticas:
      * Stop-Loss automático (-2.5%)
      * Take-Profit automático (+5%)
      * Venta por tiempo: si llevás más de CICLOS_MAX_EN_POSICION ciclos → evaluar salida

GESTIÓN DE CAPITAL (Position Sizing):
  - Importe de compra = min(CAPITAL_INICIAL, billetera["usdt"])
  - Si la billetera tiene MÁS que CAPITAL_INICIAL (ganancias acumuladas):
      → Solo invierte CAPITAL_INICIAL, el excedente queda resguardado en USDT
  - Si la billetera tiene MENOS que CAPITAL_INICIAL (drawdown por pérdidas):
      → Invierte todo lo disponible (protección ante drawdown)
  - CAPITAL_INICIAL también define el importe por operación en trading real con Binance

CONTROL DE PROMPTS (Anti-saturación de contexto):
  - Máximo 10 noticias por ciclo para el Agente Fundamental
  - Máximo 2000 caracteres en el bloque de noticias del prompt
  - Limpieza explícita de variables de string al final de cada ciclo

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
    CICLOS_MAX_EN_POSICION,
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
    "billetera_utilidades_acum", "billetera_ciclos_en_posicion",
]

# ============================================================
# BILLETERA VIRTUAL (paper trading con position sizing)
# ============================================================
billetera = {
    # Saldo USDT disponible (arranca con CAPITAL_INICIAL, crece con ganancias)
    "usdt":               CAPITAL_INICIAL,
    "btc":                0.0,
    "precio_compra":      0.0,
    "sl_pct":             STOP_LOSS_PCT,
    "tp_pct":             TAKE_PROFIT_PCT,
    "en_posicion":        False,
    "ciclos_en_posicion": 0,       # contador de ciclos desde la última compra

    # Historial
    "operaciones":        [],
    "ganancia_total":     0.0,     # suma de todas las ganancias/pérdidas realizadas
}

# Límites de control de prompts (anti-saturación de contexto)
MAX_NOTICIAS_PROMPT  = 10     # máximo de noticias enviadas al Agente Fundamental
MAX_CHARS_NOTICIAS   = 2000   # máximo de caracteres del bloque de noticias


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


def truncar_noticias(texto: str, max_noticias: int = MAX_NOTICIAS_PROMPT,
                     max_chars: int = MAX_CHARS_NOTICIAS) -> str:
    """
    Limita el bloque de noticias para evitar saturación de contexto en el modelo 7b.
    - Toma solo las primeras max_noticias noticias (separadas por líneas en blanco)
    - Trunca el texto total a max_chars caracteres
    Esto previene latencias excesivas en días de alta volatilidad con muchos titulares.
    """
    if not texto or texto == "No se pudieron obtener noticias.":
        return texto

    # Separar por bloques de noticias (cada noticia empieza con "NOTICIA")
    bloques = [b.strip() for b in texto.split("\n\n") if b.strip()]
    bloques_noticias = [b for b in bloques if b.startswith("NOTICIA")]
    otros = [b for b in bloques if not b.startswith("NOTICIA")]

    # Limitar cantidad de noticias
    bloques_noticias = bloques_noticias[:max_noticias]

    # Reconstruir texto
    texto_truncado = "\n\n".join(otros + bloques_noticias)

    # Limitar caracteres totales
    if len(texto_truncado) > max_chars:
        texto_truncado = texto_truncado[:max_chars] + "\n[...truncado para optimizar contexto]"

    return texto_truncado


def valor_total_billetera(precio_btc: float) -> float:
    """Calcula el valor total del capital operativo en USDT."""
    return billetera["usdt"] + (billetera["btc"] * precio_btc)


def rendimiento_pct(precio_btc: float) -> float:
    """Calcula el rendimiento porcentual del capital operativo respecto al inicial."""
    vt = valor_total_billetera(precio_btc)
    return ((vt - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100


def ejecutar_compra(precio: float, ciclo: int, motivo: str = "") -> bool:
    """
    Ejecuta una compra virtual con position sizing:
    - Importe = min(CAPITAL_INICIAL, billetera["usdt"])
    - Si hay más que CAPITAL_INICIAL → solo invierte CAPITAL_INICIAL, el resto queda en USDT
    - Si hay menos (drawdown) → invierte todo lo disponible
    """
    if billetera["en_posicion"] or billetera["usdt"] < 10:
        return False

    # Position sizing: nunca invertir más que CAPITAL_INICIAL
    importe_compra = min(CAPITAL_INICIAL, billetera["usdt"])
    excedente = billetera["usdt"] - importe_compra  # ganancias acumuladas que NO se arriesgan

    btc_comprado = importe_compra / precio
    billetera["btc"] = btc_comprado
    billetera["precio_compra"] = precio
    billetera["en_posicion"] = True
    billetera["usdt"] = excedente  # el excedente queda resguardado en USDT
    billetera["ciclos_en_posicion"] = 0
    billetera["operaciones"].append({
        "ciclo": ciclo, "tipo": "COMPRA",
        "precio": precio, "btc": round(btc_comprado, 6),
        "importe_usdt": round(importe_compra, 2),
        "excedente_resguardado": round(excedente, 2),
        "motivo": motivo,
        "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
    })
    console.print(
        f"   [bold green]📈 COMPRA: {btc_comprado:.6f} BTC a ${precio:,.2f}[/bold green] "
        f"(invertido: ${importe_compra:,.2f})"
    )
    if excedente > 0:
        console.print(
            f"   [bold yellow]   💼 Resguardado: ${excedente:,.2f} USDT "
            f"(ganancias acumuladas — no se arriesgan)[/bold yellow]"
        )
    console.print(
        f"   [dim]   SL: ${precio*(1-billetera['sl_pct']/100):,.2f} | "
        f"TP: ${precio*(1+billetera['tp_pct']/100):,.2f}[/dim]"
    )
    return True


def ejecutar_venta(precio: float, ciclo: int, tipo: str = "VENTA", motivo: str = "") -> bool:
    """
    Ejecuta una venta virtual de todo el BTC en posición.
    Position sizing: el USDT obtenido se suma al saldo disponible.
    Las ganancias se acumulan en billetera["usdt"] — el excedente sobre CAPITAL_INICIAL
    quedará resguardado automáticamente en la próxima compra (position sizing).
    """
    if not billetera["en_posicion"] or billetera["btc"] <= 0:
        return False

    usdt_obtenido = billetera["btc"] * precio
    costo_original = billetera["btc"] * billetera["precio_compra"]
    ganancia = usdt_obtenido - costo_original
    ganancia_pct = ((precio - billetera["precio_compra"]) / billetera["precio_compra"]) * 100

    # El USDT obtenido se suma al saldo (que puede incluir excedente resguardado)
    billetera["usdt"] += usdt_obtenido
    billetera["ganancia_total"] += ganancia

    billetera["operaciones"].append({
        "ciclo": ciclo, "tipo": tipo,
        "precio": precio, "ganancia": round(ganancia, 2),
        "ganancia_pct": round(ganancia_pct, 2),
        "saldo_usdt_resultante": round(billetera["usdt"], 2),
        "motivo": motivo,
        "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
    })
    billetera["btc"] = 0.0
    billetera["en_posicion"] = False
    billetera["precio_compra"] = 0.0
    billetera["ciclos_en_posicion"] = 0

    color = "green" if ganancia >= 0 else "red"
    signo = "+" if ganancia >= 0 else ""
    console.print(
        f"   [bold {color}]📉 {tipo}: ${precio:,.2f} | "
        f"P&L: {signo}${ganancia:,.2f} ({signo}{ganancia_pct:.2f}%)[/bold {color}]"
    )
    # Mostrar saldo resultante y cuánto quedará resguardado en la próxima compra
    excedente = max(0, billetera["usdt"] - CAPITAL_INICIAL)
    if excedente > 0:
        console.print(
            f"   [bold yellow]   💼 Saldo total: ${billetera['usdt']:,.2f} USDT "
            f"(${excedente:,.2f} resguardados en próxima compra)[/bold yellow]"
        )
    else:
        console.print(f"   [dim]   Saldo disponible: ${billetera['usdt']:,.2f} USDT[/dim]")
    return True


def verificar_sl_tp(precio: float, ciclo: int) -> str | None:
    """
    Verifica Stop-Loss y Take-Profit automáticos.
    Retorna 'SL', 'TP' o None.
    """
    if not billetera["en_posicion"] or billetera["precio_compra"] <= 0:
        return None

    pc = billetera["precio_compra"]
    sl_precio = pc * (1 - billetera["sl_pct"] / 100)
    tp_precio = pc * (1 + billetera["tp_pct"] / 100)

    if precio <= sl_precio:
        motivo = (f"Stop-Loss: ${precio:,.2f} ≤ ${sl_precio:,.2f} (-{billetera['sl_pct']}%)")
        console.print(f"   [bold red]🛑 STOP-LOSS activado en ${precio:,.2f} (SL=${sl_precio:,.2f})[/bold red]")
        ejecutar_venta(precio, ciclo, "VENTA_SL", motivo)
        return "SL"

    if precio >= tp_precio:
        motivo = (f"Take-Profit: ${precio:,.2f} ≥ ${tp_precio:,.2f} (+{billetera['tp_pct']}%)")
        console.print(f"   [bold green]🎯 TAKE-PROFIT activado en ${precio:,.2f} (TP=${tp_precio:,.2f})[/bold green]")
        ejecutar_venta(precio, ciclo, "VENTA_TP", motivo)
        return "TP"

    return None


def verificar_venta_por_tiempo(precio: float, ciclo: int) -> bool:
    """
    Regla de seguridad: si llevamos demasiados ciclos en posición
    y el P&L es positivo → vender para asegurar ganancias.
    Retorna True si se ejecutó venta.
    """
    if not billetera["en_posicion"]:
        return False

    ciclos_en_pos = billetera["ciclos_en_posicion"]
    if ciclos_en_pos < CICLOS_MAX_EN_POSICION:
        return False

    pc = billetera["precio_compra"]
    pnl = (precio - pc) / pc * 100

    if pnl > 0.5:  # Solo vender si hay al menos 0.5% de ganancia
        motivo = (f"Venta por tiempo: {ciclos_en_pos} ciclos en posición, "
                  f"P&L={pnl:+.2f}% → asegurando ganancia")
        console.print(
            f"   [bold yellow]⏰ VENTA POR TIEMPO: {ciclos_en_pos} ciclos en posición "
            f"con P&L={pnl:+.2f}%[/bold yellow]"
        )
        ejecutar_venta(precio, ciclo, "VENTA_TIEMPO", motivo)
        return True

    return False


def mostrar_billetera(precio_actual: float):
    """Muestra el estado completo de la billetera virtual."""
    vt = valor_total_billetera(precio_actual)
    rend = rendimiento_pct(precio_actual)
    color_r = "green" if rend >= 0 else "red"
    signo = "+" if rend >= 0 else ""

    tabla = Table(title="💰 Billetera Virtual — Paper Trading", show_header=False,
                  box=None, padding=(0, 1))
    tabla.add_column("Campo", style="cyan", width=24)
    tabla.add_column("Valor", style="white")

    tabla.add_row("Capital operativo inicial", f"${CAPITAL_INICIAL:,.2f} USDT")
    tabla.add_row("USDT disponible",           f"${billetera['usdt']:,.2f} USDT")
    tabla.add_row("BTC en posición",
                  f"{billetera['btc']:.6f} BTC (${billetera['btc']*precio_actual:,.2f})")
    tabla.add_row("Valor operativo total",     f"${vt:,.2f} USDT")
    tabla.add_row("Rendimiento operativo",     f"[{color_r}]{signo}{rend:.2f}%[/{color_r}]")
    # Calcular excedente resguardado (ganancias acumuladas sobre CAPITAL_INICIAL)
    excedente_resguardado = max(0, billetera["usdt"] - CAPITAL_INICIAL) if not billetera["en_posicion"] else 0
    tabla.add_row("─" * 24, "─" * 22)
    tabla.add_row("[bold yellow]Ganancias resguardadas[/bold yellow]",
                  f"[bold yellow]${excedente_resguardado:,.2f} USDT[/bold yellow]")
    tabla.add_row("Ganancia/pérdida total",    f"${billetera['ganancia_total']:,.2f} USDT")
    tabla.add_row("Operaciones realizadas",    str(len(billetera["operaciones"])))

    if billetera["en_posicion"]:
        pc = billetera["precio_compra"]
        sl_p = pc * (1 - billetera["sl_pct"] / 100)
        tp_p = pc * (1 + billetera["tp_pct"] / 100)
        pnl_actual = (precio_actual - pc) / pc * 100
        color_pnl = "green" if pnl_actual >= 0 else "red"
        tabla.add_row("─" * 24, "─" * 22)
        tabla.add_row("Posición abierta",
                      f"Comprado a ${pc:,.2f} (ciclo #{billetera['ciclos_en_posicion']})")
        tabla.add_row("P&L actual",
                      f"[{color_pnl}]{'+' if pnl_actual >= 0 else ''}{pnl_actual:.2f}%[/{color_pnl}]")
        tabla.add_row("Stop-Loss",    f"[red]${sl_p:,.2f}[/red] (-{billetera['sl_pct']}%)")
        tabla.add_row("Take-Profit",  f"[green]${tp_p:,.2f}[/green] (+{billetera['tp_pct']}%)")
        tabla.add_row("Venta por tiempo",
                      f"en {CICLOS_MAX_EN_POSICION - billetera['ciclos_en_posicion']} ciclos más")

    console.print(tabla)


def contexto_posicion_para_ia() -> str:
    """Genera el texto de contexto de posición actual para incluir en los prompts."""
    if billetera["en_posicion"]:
        pc = billetera["precio_compra"]
        return (
            f"POSICIÓN ACTUAL: EN POSICIÓN (comprado a ${pc:,.2f} USDT)\n"
            f"Ciclos en posición: {billetera['ciclos_en_posicion']} de {CICLOS_MAX_EN_POSICION} máximo\n"
            f"Stop-Loss: -{ billetera['sl_pct']}% (${pc*(1-billetera['sl_pct']/100):,.2f})\n"
            f"Take-Profit: +{billetera['tp_pct']}% (${pc*(1+billetera['tp_pct']/100):,.2f})\n"
            f"Operaciones realizadas: {len(billetera['operaciones'])}"
        )
    else:
        excedente = max(0, billetera["usdt"] - CAPITAL_INICIAL)
        return (
            f"POSICIÓN ACTUAL: SIN POSICIÓN (disponible ${billetera['usdt']:,.2f} USDT)\n"
            f"Ganancias resguardadas: ${excedente:,.2f} USDT\n"
            f"Operaciones realizadas: {len(billetera['operaciones'])}"
        )


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def ejecutar_ciclo(ciclo: int) -> dict:
    """Ejecuta un ciclo completo de paper trading."""
    inicio = time.time()
    ts = ahora_ba().strftime("%Y-%m-%d %H:%M:%S")
    registro = {"ciclo": ciclo, "timestamp": ts}

    console.print(Rule(f"[bold cyan]CICLO #{ciclo} — {ts}[/bold cyan]"))

    # Incrementar contador de ciclos en posición
    if billetera["en_posicion"]:
        billetera["ciclos_en_posicion"] += 1

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

    # --- Verificar SL/TP automáticos PRIMERO ---
    sl_tp_activado = verificar_sl_tp(precio, ciclo)

    # --- Verificar venta por tiempo (si no se activó SL/TP) ---
    venta_tiempo = False
    if not sl_tp_activado:
        venta_tiempo = verificar_venta_por_tiempo(precio, ciclo)

    # --- Noticias (con control de tamaño para evitar saturación de contexto) ---
    try:
        from src.noticias.feed_manager import obtener_resumen_noticias
        noticias, texto_noticias_raw = obtener_resumen_noticias()
        texto_noticias = truncar_noticias(texto_noticias_raw)
        registro["noticias_count"] = len(noticias)
        chars_orig = len(texto_noticias_raw)
        chars_final = len(texto_noticias)
        if chars_final < chars_orig:
            console.print(
                f"[yellow]📰 {len(noticias)} noticias → truncadas "
                f"({chars_orig}→{chars_final} chars, máx {MAX_NOTICIAS_PROMPT} noticias)[/yellow]"
            )
        else:
            console.print(f"[yellow]📰 {len(noticias)} noticias recientes[/yellow]")
        del texto_noticias_raw  # liberar memoria
    except Exception:
        texto_noticias = "No se pudieron obtener noticias."
        noticias = []
        registro["noticias_count"] = 0

    # --- Contexto de posición para las IAs ---
    ctx_posicion = contexto_posicion_para_ia()

    # --- Prompt Agente Técnico (GPU0 — qwen2.5:7b) ---
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

    # --- Prompt Agente Fundamental (GPU1 — qwen2.5:3b) ---
    prompt_f = f"""Eres un analista fundamental de criptomonedas. Evalúa estas noticias REALES de Bitcoin:

{texto_noticias}

{ctx_posicion}

Evalúa el impacto de las noticias en el precio de Bitcoin.

Responde SOLO con JSON válido:
{{"impacto": "ALCISTA", "intensidad": 70, "justificacion": "texto breve"}}
Donde "impacto" es exactamente ALCISTA, BAJISTA o NEUTRAL."""

    # --- GPU0: Agente Técnico ---
    datos_t, tiempo_t, _ = consultar_ia(PUERTO_GPU0, MODELO_GPU0, prompt_t)
    if datos_t:
        accion_t    = str(datos_t.get("accion", "ESPERAR")).upper()
        if accion_t not in ("COMPRA", "VENTA", "ESPERAR"):
            accion_t = "ESPERAR"
        confianza_t = int(datos_t.get("confianza", 50))
        just_t      = str(datos_t.get("justificacion", ""))
        color_t = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(accion_t, "white")
        console.print(f"[dim]🔵 GPU0 Técnico ({tiempo_t:.1f}s):[/dim] "
                      f"[{color_t}]{accion_t}[/{color_t}] ({confianza_t}%) — {just_t[:80]}")
    else:
        accion_t, confianza_t, just_t = "ESPERAR", 0, "Error GPU0"
        console.print("[red]❌ GPU0 sin respuesta[/red]")

    registro["decision_tecnico"]      = accion_t
    registro["confianza_tecnico"]     = confianza_t
    registro["justificacion_tecnico"] = just_t[:300]

    # --- GPU1: Agente Fundamental ---
    datos_f, tiempo_f, _ = consultar_ia(PUERTO_GPU1, MODELO_GPU1, prompt_f)
    if datos_f:
        impacto_f    = str(datos_f.get("impacto", "NEUTRAL")).upper()
        if impacto_f not in ("ALCISTA", "BAJISTA", "NEUTRAL"):
            impacto_f = "NEUTRAL"
        intensidad_f = int(datos_f.get("intensidad", 50))
        just_f       = str(datos_f.get("justificacion", ""))
        color_f = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(impacto_f, "white")
        console.print(f"[dim]🟡 GPU1 Fundamental ({tiempo_f:.1f}s):[/dim] "
                      f"[{color_f}]{impacto_f}[/{color_f}] ({intensidad_f}%) — {just_f[:80]}")
    else:
        impacto_f, intensidad_f, just_f = "NEUTRAL", 0, "Error GPU1"
        console.print("[red]❌ GPU1 sin respuesta[/red]")

    registro["decision_fundamental"]      = impacto_f
    registro["intensidad_fundamental"]    = intensidad_f
    registro["justificacion_fundamental"] = just_f[:300]

    # ---------------------------------------------------------------
    # LÓGICA DE DECISIÓN
    # ---------------------------------------------------------------
    sl_r       = STOP_LOSS_PCT
    tp_r       = TAKE_PROFIT_PCT
    decision_r = "ESPERAR"
    motivo_r   = ""

    if sl_tp_activado or venta_tiempo:
        # Ya se ejecutó una venta automática — registrar y continuar
        decision_r = "VENTA"
        motivo_r   = "Venta automática (SL/TP/Tiempo)"

    elif not billetera["en_posicion"]:
        # ── SIN POSICIÓN: decisión directa por Técnico + Fundamental ──
        # No usamos GPU2 para entrar — tiende a vetar compras
        if accion_t == "COMPRA" and confianza_t >= 65 and impacto_f != "BAJISTA":
            decision_r = "COMPRA"
            motivo_r   = (f"Técnico COMPRA ({confianza_t}%) + Fundamental {impacto_f}. "
                          f"{just_t[:120]}")
            console.print(
                f"[bold green]✅ COMPRA DIRECTA[/bold green] "
                f"(Técnico {confianza_t}% + Fundamental {impacto_f})"
            )
        elif accion_t == "COMPRA" and impacto_f == "BAJISTA":
            decision_r = "ESPERAR"
            motivo_r   = "Técnico COMPRA pero Fundamental BAJISTA — esperando"
            console.print("[yellow]⏸️  ESPERAR: Técnico COMPRA pero noticias BAJISTAS[/yellow]")
        else:
            decision_r = "ESPERAR"
            motivo_r   = f"Técnico {accion_t} ({confianza_t}%) — umbral mínimo 65%"
            console.print(
                f"[yellow]⏸️  ESPERAR: Técnico={accion_t} ({confianza_t}%)[/yellow]"
            )

    else:
        # ── CON POSICIÓN: GPU2 decide si vender o mantener ──
        pc = billetera["precio_compra"]
        pnl_actual = (precio - pc) / pc * 100

        prompt_r = f"""Eres el Gestor de Riesgos de un bot de paper trading de Bitcoin.
Hay una posición ABIERTA. Decide si VENDER o MANTENER (ESPERAR).

DATOS DEL MERCADO:
- Precio BTC: ${precio:,.2f} USDT
- RSI: {registro.get('rsi', 'N/A')} ({registro.get('rsi_zona', 'N/A')})
- MACD: {registro.get('macd_cruce', 'N/A')}
- Tendencia EMA: {registro.get('tendencia_ema', 'N/A')}

ANÁLISIS DE LOS AGENTES:
- Técnico: {accion_t} (confianza: {confianza_t}%) — {just_t[:100]}
- Fundamental: {impacto_f} (intensidad: {intensidad_f}%) — {just_f[:100]}

{ctx_posicion}
P&L actual: {pnl_actual:+.2f}%

REGLAS (aplicar en orden):
1. Si técnico dice VENTA → VENTA
2. Si RSI > 72 (sobrecomprado) → VENTA
3. Si MACD negativo Y P&L < -1% → VENTA
4. Si P&L > 3% Y tendencia se debilita → VENTA
5. Si todo sigue bien → ESPERAR

Responde SOLO con JSON válido:
{{"decision": "ESPERAR", "stop_loss_pct": 2.5, "take_profit_pct": 5.0, "motivo": "texto breve"}}
Donde "decision" es exactamente VENTA o ESPERAR."""

        datos_r, tiempo_r_seg, _ = consultar_ia(PUERTO_GPU2, MODELO_GPU2, prompt_r)
        if datos_r:
            decision_r = str(datos_r.get("decision", "ESPERAR")).upper()
            if decision_r not in ("VENTA", "ESPERAR"):
                decision_r = "ESPERAR"
            sl_r     = float(datos_r.get("stop_loss_pct", STOP_LOSS_PCT))
            tp_r     = float(datos_r.get("take_profit_pct", TAKE_PROFIT_PCT))
            motivo_r = str(datos_r.get("motivo") or datos_r.get("razon") or
                           datos_r.get("justificacion") or "Sin motivo")
            color_r  = {"VENTA": "red", "ESPERAR": "yellow"}.get(decision_r, "white")
            console.print(
                f"[dim]🔴 GPU2 Riesgos ({tiempo_r_seg:.1f}s):[/dim] "
                f"[bold {color_r}]{decision_r}[/bold {color_r}] "
                f"SL:-{sl_r}% TP:+{tp_r}% | P&L={pnl_actual:+.2f}%"
            )
        else:
            decision_r = "ESPERAR"
            motivo_r   = "Error GPU2 — manteniendo posición"
            console.print("[red]❌ GPU2 sin respuesta — manteniendo posición[/red]")

    registro["decision_final"]  = decision_r
    registro["stop_loss_pct"]   = sl_r
    registro["take_profit_pct"] = tp_r
    registro["motivo_riesgo"]   = motivo_r[:300]

    # Actualizar SL/TP de la billetera
    billetera["sl_pct"] = sl_r
    billetera["tp_pct"] = tp_r

    # --- Ejecutar decisión (si no hubo venta automática ya) ---
    if not sl_tp_activado and not venta_tiempo:
        if decision_r == "COMPRA":
            ejecutar_compra(precio, ciclo, motivo_r)
        elif decision_r == "VENTA":
            ejecutar_venta(precio, ciclo, "VENTA", motivo_r)

    # --- Mostrar estado de billetera ---
    mostrar_billetera(precio)

    # --- Agregar datos de billetera al registro ---
    vt = valor_total_billetera(precio)
    registro["billetera_usdt"]              = round(billetera["usdt"], 2)
    registro["billetera_btc"]               = round(billetera["btc"], 8)
    registro["billetera_valor_total"]       = round(vt, 2)
    registro["billetera_rendimiento_pct"]   = round(rendimiento_pct(precio), 4)
    registro["billetera_en_posicion"]       = billetera["en_posicion"]
    # Ganancias resguardadas = excedente sobre CAPITAL_INICIAL (solo cuando no hay posición)
    excedente_csv = max(0, billetera["usdt"] - CAPITAL_INICIAL) if not billetera["en_posicion"] else 0
    registro["billetera_utilidades_acum"]   = round(excedente_csv, 2)
    registro["billetera_ciclos_en_posicion"]= billetera["ciclos_en_posicion"]

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
            console.print(f"[green]✅ PostgreSQL conectado — datos en DB + CSV[/green]")
        else:
            console.print(f"[yellow]⚠️  PostgreSQL no disponible — solo CSV[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Error DB: {e} — solo CSV[/yellow]")

    console.print(Panel.fit(
        "[bold cyan]🤖 PAPER TRADING 24/7 — CryptoIA[/bold cyan]\n"
        f"Capital operativo: [bold green]${CAPITAL_INICIAL:,.2f} USDT[/bold green] | "
        f"Intervalo: [yellow]{INTERVALO_MINUTOS} min[/yellow] | "
        f"Temporalidad: [yellow]{TEMPORALIDAD}[/yellow]\n"
        f"Stop-Loss: [red]-{STOP_LOSS_PCT}%[/red] | "
        f"Take-Profit: [green]+{TAKE_PROFIT_PCT}%[/green] | "
        f"Máx ciclos en posición: [yellow]{CICLOS_MAX_EN_POSICION}[/yellow]\n"
        f"Sistema de utilidades: [bold yellow]ACTIVO[/bold yellow] — "
        f"ganancias se retiran y el capital se resetea a ${CAPITAL_INICIAL:,.2f}\n"
        "[bold red]⚠️  SOLO SIMULACIÓN — No se ejecutan operaciones reales[/bold red]\n"
        "Detener con: [bold]Ctrl+C[/bold]",
        border_style="cyan"
    ))

    ciclo = 1
    proxima_ejecucion = time.time()

    while True:
        ahora_ts = time.time()

        if ahora_ts >= proxima_ejecucion:
            try:
                registro = ejecutar_ciclo(ciclo)
                guardar_en_csv(registro)

                if db_disponible:
                    try:
                        from src.trading.base_datos import guardar_ciclo, guardar_estado_billetera
                        ok_db = guardar_ciclo(registro)
                        precio_db = registro.get("precio_btc", 0)
                        if ok_db and precio_db:
                            guardar_estado_billetera(billetera, ciclo, float(precio_db), "CICLO")
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
                f"\n[dim]⏳ Próximo ciclo en {INTERVALO_MINUTOS} min "
                f"({datetime.fromtimestamp(proxima_ejecucion, tz=TZ_BA).strftime('%H:%M:%S')})[/dim]\n"
            )

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

        # Resumen final
        excedente_final = max(0, billetera["usdt"] - CAPITAL_INICIAL)
        console.print(f"\n[bold]📊 Resumen final:[/bold]")
        console.print(f"  Operaciones: {len(billetera['operaciones'])}")
        console.print(f"  Saldo USDT final: ${billetera['usdt']:,.2f} USDT")
        console.print(f"  Ganancia/pérdida total: ${billetera['ganancia_total']:+,.2f} USDT")
        console.print(f"  [bold yellow]Ganancias resguardadas: ${excedente_final:,.2f} USDT[/bold yellow]")

        if billetera["operaciones"]:
            console.print(f"\n[bold]Detalle de operaciones:[/bold]")
            for op in billetera["operaciones"]:
                tipo = op["tipo"]
                color = "green" if tipo in ("VENTA_TP", "VENTA", "VENTA_TIEMPO") else \
                        "red" if tipo == "VENTA_SL" else "cyan"
                ganancia_str = (f" | P&L: ${op.get('ganancia', 0):+,.2f} "
                                f"({op.get('ganancia_pct', 0):+.2f}%)"
                                if "ganancia" in op else "")
                console.print(
                    f"   [{color}]• Ciclo #{op['ciclo']}: {tipo} a "
                    f"${op['precio']:,.2f}{ganancia_str}[/{color}]"
                )
        sys.exit(0)
