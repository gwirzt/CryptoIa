"""
src/trading/motor_real.py — Motor de trading real/testnet 24/7

Versión de producción basada en test_observacion.py.
Integra los 3 agentes IA + Binance real/testnet.

MODOS DE OPERACIÓN (controlados por .env):
  MODO_REAL=false + BINANCE_TESTNET=true  → Paper trading puro (sin Binance)
  MODO_REAL=true  + BINANCE_TESTNET=true  → Trading real en Testnet (dinero ficticio)
  MODO_REAL=true  + BINANCE_TESTNET=false → Trading real en Producción (¡dinero real!)

DIFERENCIAS con test_observacion.py:
  - Saldo real de Binance (no billetera virtual en memoria)
  - Órdenes reales cuando MODO_REAL=true
  - Logging a archivo además de consola
  - Manejo de errores más robusto para 24/7
  - Guarda estado en PostgreSQL para que la API lo lea

Ejecutar:
    python src/trading/motor_real.py
    nohup python3 src/trading/motor_real.py > logs/motor_real.log 2>&1 &

Detener con: Ctrl+C
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import time
import csv
import logging
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
    MODO_REAL,
    BINANCE_TESTNET,
)

# ==============================================================================
# LOGGING A ARCHIVO
# ==============================================================================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/motor_real.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("motor_real")

console = Console()

# Zona horaria Argentina
try:
    TZ_BA = ZoneInfo(TIMEZONE)
except Exception:
    TZ_BA = timezone.utc

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
TIMEOUT_IA       = 90
CSV_PATH         = "logs/motor_real.csv"
MAX_NOTICIAS_PROMPT = 10
MAX_CHARS_NOTICIAS  = 2000

CSV_HEADERS = [
    "timestamp", "ciclo", "precio_btc", "rsi", "rsi_zona",
    "macd_cruce", "bb_posicion", "tendencia_ema", "volumen_relativo",
    "decision_tecnico", "confianza_tecnico",
    "decision_fundamental", "intensidad_fundamental",
    "decision_final", "stop_loss_pct", "take_profit_pct",
    "justificacion_tecnico", "justificacion_fundamental", "motivo_riesgo",
    "tiempo_ciclo_seg", "noticias_count", "error",
    "saldo_usdt", "saldo_btc", "valor_total_usdt",
    "rendimiento_pct", "en_posicion", "ganancia_total",
    "ciclos_en_posicion", "modo_real", "entorno",
]

# ==============================================================================
# ESTADO GLOBAL DEL BOT (compartido con la API via PostgreSQL)
# ==============================================================================
estado_bot = {
    "activo":             True,
    "ciclo_actual":       0,
    "ultimo_ciclo_ts":    None,
    "en_posicion":        False,
    "precio_compra":      0.0,
    "ciclos_en_posicion": 0,
    "sl_pct":             STOP_LOSS_PCT,
    "tp_pct":             TAKE_PROFIT_PCT,
    "ganancia_total":     0.0,
    "operaciones":        [],
    # Saldo (real o simulado según MODO_REAL)
    "saldo_usdt":         CAPITAL_INICIAL,
    "saldo_btc":          0.0,
    "modo_real":          MODO_REAL,
    "entorno":            "TESTNET" if BINANCE_TESTNET else "PRODUCCIÓN",
}

# ==============================================================================
# TRADER BINANCE (inicializado al arrancar)
# ==============================================================================
trader = None


def inicializar_trader():
    """Inicializa el cliente Binance. Retorna True si OK."""
    global trader
    from src.trading.binance_trader import crear_trader
    trader = crear_trader()
    ok, msg = trader.inicializar()
    if ok:
        console.print(f"[green]✅ {msg}[/green]")
        logger.info(msg)
    else:
        console.print(f"[yellow]⚠️  {msg} — usando saldo simulado[/yellow]")
        logger.warning(msg)
    return ok


# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================

def ahora_ba() -> datetime:
    return datetime.now(TZ_BA)


def consultar_ia(puerto: int, modelo: str, prompt: str) -> tuple:
    """Consulta a una IA Ollama. Retorna (json_dict|None, tiempo_seg, texto_crudo)."""
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


def truncar_noticias(texto: str) -> str:
    if not texto or texto == "No se pudieron obtener noticias.":
        return texto
    bloques = [b.strip() for b in texto.split("\n\n") if b.strip()]
    bloques_noticias = [b for b in bloques if b.startswith("NOTICIA")][:MAX_NOTICIAS_PROMPT]
    otros = [b for b in bloques if not b.startswith("NOTICIA")]
    texto_truncado = "\n\n".join(otros + bloques_noticias)
    if len(texto_truncado) > MAX_CHARS_NOTICIAS:
        texto_truncado = texto_truncado[:MAX_CHARS_NOTICIAS] + "\n[...truncado]"
    return texto_truncado


def guardar_en_csv(fila: dict):
    archivo_existe = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not archivo_existe:
            writer.writeheader()
        writer.writerow({k: fila.get(k, "") for k in CSV_HEADERS})


def obtener_saldo_actual() -> tuple[float, float]:
    """
    Obtiene el saldo actual (real de Binance o simulado).
    Retorna (usdt, btc)
    """
    if MODO_REAL and trader and trader._inicializado:
        ok, saldo = trader.obtener_saldo()
        if ok:
            return saldo["usdt"], saldo["btc"]
    # Fallback: saldo simulado del estado_bot
    return estado_bot["saldo_usdt"], estado_bot["saldo_btc"]


def valor_total(precio_btc: float) -> float:
    usdt, btc = obtener_saldo_actual()
    return usdt + (btc * precio_btc)


def rendimiento_pct(precio_btc: float) -> float:
    vt = valor_total(precio_btc)
    return ((vt - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100


# ==============================================================================
# OPERACIONES DE COMPRA / VENTA
# ==============================================================================

def ejecutar_compra(precio: float, ciclo: int, motivo: str = "") -> bool:
    """
    Ejecuta una compra (real o simulada según MODO_REAL).
    Position sizing: invierte min(CAPITAL_INICIAL, saldo_disponible).
    """
    usdt_disponible, btc_actual = obtener_saldo_actual()

    if estado_bot["en_posicion"] or usdt_disponible < 10:
        return False

    importe_compra = min(CAPITAL_INICIAL, usdt_disponible)
    excedente = usdt_disponible - importe_compra

    if MODO_REAL and trader and trader._inicializado:
        # ── ORDEN REAL EN BINANCE ──
        ok, resultado = trader.comprar(usdt_amount=importe_compra)
        if not ok:
            console.print(f"[red]❌ Error en compra real: {resultado.get('error')}[/red]")
            logger.error(f"Error compra real: {resultado.get('error')}")
            return False
        btc_comprado = resultado["btc_comprado"]
        precio_real  = resultado["precio_promedio"]
        comision     = resultado["comision_usdt"]
        console.print(
            f"   [bold green]📈 COMPRA REAL: {btc_comprado:.6f} BTC @ ${precio_real:,.2f}[/bold green] "
            f"(invertido: ${importe_compra:,.2f} | comisión: ${comision:.2f})"
        )
        logger.info(f"COMPRA REAL: {btc_comprado:.6f} BTC @ ${precio_real:,.2f} | ciclo #{ciclo}")
    else:
        # ── SIMULACIÓN (paper trading) ──
        btc_comprado = (importe_compra / precio) * 0.999  # simular comisión
        precio_real  = precio
        console.print(
            f"   [bold green]📈 COMPRA SIMULADA: {btc_comprado:.6f} BTC @ ${precio_real:,.2f}[/bold green] "
            f"(invertido: ${importe_compra:,.2f})"
        )

    # Actualizar estado
    estado_bot["saldo_usdt"]         = excedente
    estado_bot["saldo_btc"]          = btc_comprado
    estado_bot["precio_compra"]      = precio_real
    estado_bot["en_posicion"]        = True
    estado_bot["ciclos_en_posicion"] = 0
    estado_bot["sl_pct"]             = STOP_LOSS_PCT
    estado_bot["tp_pct"]             = TAKE_PROFIT_PCT
    estado_bot["operaciones"].append({
        "ciclo": ciclo, "tipo": "COMPRA",
        "precio": precio_real, "btc": round(btc_comprado, 6),
        "importe_usdt": round(importe_compra, 2),
        "excedente_resguardado": round(excedente, 2),
        "motivo": motivo,
        "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
        "modo": "REAL" if MODO_REAL else "SIMULADO",
    })

    if excedente > 0:
        console.print(f"   [bold yellow]   💼 Resguardado: ${excedente:,.2f} USDT[/bold yellow]")
    console.print(
        f"   [dim]   SL: ${precio_real*(1-STOP_LOSS_PCT/100):,.2f} | "
        f"TP: ${precio_real*(1+TAKE_PROFIT_PCT/100):,.2f}[/dim]"
    )
    return True


def ejecutar_venta(precio: float, ciclo: int, tipo: str = "VENTA", motivo: str = "") -> bool:
    """
    Ejecuta una venta (real o simulada según MODO_REAL).
    Vende TODO el BTC en posición.
    """
    if not estado_bot["en_posicion"]:
        return False

    btc_en_posicion = estado_bot["saldo_btc"]
    if btc_en_posicion <= 0:
        return False

    if MODO_REAL and trader and trader._inicializado:
        # ── ORDEN REAL EN BINANCE ──
        ok, resultado = trader.vender_todo()
        if not ok:
            console.print(f"[red]❌ Error en venta real: {resultado.get('error')}[/red]")
            logger.error(f"Error venta real: {resultado.get('error')}")
            return False
        usdt_obtenido = resultado["usdt_obtenido"]
        precio_real   = resultado["precio_promedio"]
        comision      = resultado["comision_usdt"]
        console.print(
            f"   [bold]📉 VENTA REAL: ${precio_real:,.2f}[/bold] "
            f"(obtenido: ${usdt_obtenido:,.2f} | comisión: ${comision:.2f})"
        )
        logger.info(f"VENTA REAL: {btc_en_posicion:.6f} BTC @ ${precio_real:,.2f} | ciclo #{ciclo}")
    else:
        # ── SIMULACIÓN ──
        usdt_obtenido = btc_en_posicion * precio * 0.999  # simular comisión
        precio_real   = precio

    costo_original = btc_en_posicion * estado_bot["precio_compra"]
    ganancia       = usdt_obtenido - costo_original
    ganancia_pct   = ((precio_real - estado_bot["precio_compra"]) / estado_bot["precio_compra"]) * 100

    estado_bot["saldo_usdt"]    += usdt_obtenido
    estado_bot["saldo_btc"]      = 0.0
    estado_bot["ganancia_total"] += ganancia
    estado_bot["en_posicion"]    = False
    estado_bot["precio_compra"]  = 0.0
    estado_bot["ciclos_en_posicion"] = 0

    estado_bot["operaciones"].append({
        "ciclo": ciclo, "tipo": tipo,
        "precio": precio_real, "ganancia": round(ganancia, 2),
        "ganancia_pct": round(ganancia_pct, 2),
        "saldo_usdt_resultante": round(estado_bot["saldo_usdt"], 2),
        "motivo": motivo,
        "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
        "modo": "REAL" if MODO_REAL else "SIMULADO",
    })

    color = "green" if ganancia >= 0 else "red"
    signo = "+" if ganancia >= 0 else ""
    console.print(
        f"   [bold {color}]📉 {tipo}: ${precio_real:,.2f} | "
        f"P&L: {signo}${ganancia:,.2f} ({signo}{ganancia_pct:.2f}%)[/bold {color}]"
    )
    excedente = max(0, estado_bot["saldo_usdt"] - CAPITAL_INICIAL)
    if excedente > 0:
        console.print(
            f"   [bold yellow]   💼 Saldo total: ${estado_bot['saldo_usdt']:,.2f} USDT "
            f"(${excedente:,.2f} resguardados)[/bold yellow]"
        )
    return True


def verificar_sl_tp(precio: float, ciclo: int) -> str | None:
    if not estado_bot["en_posicion"] or estado_bot["precio_compra"] <= 0:
        return None
    pc = estado_bot["precio_compra"]
    sl_precio = pc * (1 - estado_bot["sl_pct"] / 100)
    tp_precio = pc * (1 + estado_bot["tp_pct"] / 100)
    if precio <= sl_precio:
        motivo = f"Stop-Loss: ${precio:,.2f} ≤ ${sl_precio:,.2f} (-{estado_bot['sl_pct']}%)"
        console.print(f"   [bold red]🛑 STOP-LOSS activado en ${precio:,.2f}[/bold red]")
        ejecutar_venta(precio, ciclo, "VENTA_SL", motivo)
        return "SL"
    if precio >= tp_precio:
        motivo = f"Take-Profit: ${precio:,.2f} ≥ ${tp_precio:,.2f} (+{estado_bot['tp_pct']}%)"
        console.print(f"   [bold green]🎯 TAKE-PROFIT activado en ${precio:,.2f}[/bold green]")
        ejecutar_venta(precio, ciclo, "VENTA_TP", motivo)
        return "TP"
    return None


def verificar_venta_por_tiempo(precio: float, ciclo: int) -> bool:
    if not estado_bot["en_posicion"]:
        return False
    ciclos_en_pos = estado_bot["ciclos_en_posicion"]
    if ciclos_en_pos < CICLOS_MAX_EN_POSICION:
        return False
    pc  = estado_bot["precio_compra"]
    pnl = (precio - pc) / pc * 100
    if pnl > 0.5:
        motivo = f"Venta por tiempo: {ciclos_en_pos} ciclos, P&L={pnl:+.2f}%"
        console.print(f"   [bold yellow]⏰ VENTA POR TIEMPO: {ciclos_en_pos} ciclos, P&L={pnl:+.2f}%[/bold yellow]")
        ejecutar_venta(precio, ciclo, "VENTA_TIEMPO", motivo)
        return True
    return False


def contexto_posicion_para_ia() -> str:
    if estado_bot["en_posicion"]:
        pc = estado_bot["precio_compra"]
        return (
            f"POSICIÓN ACTUAL: EN POSICIÓN (comprado a ${pc:,.2f} USDT)\n"
            f"Ciclos en posición: {estado_bot['ciclos_en_posicion']} de {CICLOS_MAX_EN_POSICION} máximo\n"
            f"Stop-Loss: -{estado_bot['sl_pct']}% (${pc*(1-estado_bot['sl_pct']/100):,.2f})\n"
            f"Take-Profit: +{estado_bot['tp_pct']}% (${pc*(1+estado_bot['tp_pct']/100):,.2f})\n"
            f"Operaciones realizadas: {len(estado_bot['operaciones'])}"
        )
    else:
        usdt, _ = obtener_saldo_actual()
        excedente = max(0, usdt - CAPITAL_INICIAL)
        return (
            f"POSICIÓN ACTUAL: SIN POSICIÓN (disponible ${usdt:,.2f} USDT)\n"
            f"Ganancias resguardadas: ${excedente:,.2f} USDT\n"
            f"Operaciones realizadas: {len(estado_bot['operaciones'])}"
        )


def mostrar_estado(precio_actual: float):
    usdt, btc = obtener_saldo_actual()
    vt   = usdt + (btc * precio_actual)
    rend = ((vt - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100
    color_r = "green" if rend >= 0 else "red"
    signo   = "+" if rend >= 0 else ""

    tabla = Table(
        title=f"💰 Estado — {'REAL' if MODO_REAL else 'SIMULADO'} | "
              f"{'TESTNET' if BINANCE_TESTNET else 'PRODUCCIÓN'}",
        show_header=False, box=None, padding=(0, 1)
    )
    tabla.add_column("Campo", style="cyan", width=26)
    tabla.add_column("Valor", style="white")

    tabla.add_row("Capital operativo inicial", f"${CAPITAL_INICIAL:,.2f} USDT")
    tabla.add_row("USDT disponible",           f"${usdt:,.2f} USDT")
    tabla.add_row("BTC en posición",           f"{btc:.6f} BTC (${btc*precio_actual:,.2f})")
    tabla.add_row("Valor total",               f"${vt:,.2f} USDT")
    tabla.add_row("Rendimiento",               f"[{color_r}]{signo}{rend:.2f}%[/{color_r}]")
    tabla.add_row("Ganancia/pérdida total",    f"${estado_bot['ganancia_total']:,.2f} USDT")
    tabla.add_row("Operaciones realizadas",    str(len(estado_bot["operaciones"])))

    if estado_bot["en_posicion"]:
        pc      = estado_bot["precio_compra"]
        sl_p    = pc * (1 - estado_bot["sl_pct"] / 100)
        tp_p    = pc * (1 + estado_bot["tp_pct"] / 100)
        pnl_act = (precio_actual - pc) / pc * 100
        color_p = "green" if pnl_act >= 0 else "red"
        tabla.add_row("─" * 26, "─" * 22)
        tabla.add_row("Posición abierta",
                      f"Comprado a ${pc:,.2f} (ciclo #{estado_bot['ciclos_en_posicion']})")
        tabla.add_row("P&L actual",
                      f"[{color_p}]{'+' if pnl_act >= 0 else ''}{pnl_act:.2f}%[/{color_p}]")
        tabla.add_row("Stop-Loss",   f"[red]${sl_p:,.2f}[/red] (-{estado_bot['sl_pct']}%)")
        tabla.add_row("Take-Profit", f"[green]${tp_p:,.2f}[/green] (+{estado_bot['tp_pct']}%)")

    console.print(tabla)


# ==============================================================================
# CICLO PRINCIPAL
# ==============================================================================

def ejecutar_ciclo(ciclo: int) -> dict:
    inicio = time.time()
    ts     = ahora_ba().strftime("%Y-%m-%d %H:%M:%S")
    registro = {
        "ciclo": ciclo, "timestamp": ts,
        "modo_real": MODO_REAL,
        "entorno": "TESTNET" if BINANCE_TESTNET else "PRODUCCIÓN",
    }

    console.print(Rule(f"[bold cyan]CICLO #{ciclo} — {ts} | {'🔴 REAL' if MODO_REAL else '🟡 SIMULADO'}[/bold cyan]"))

    estado_bot["ciclo_actual"]    = ciclo
    estado_bot["ultimo_ciclo_ts"] = ts

    if estado_bot["en_posicion"]:
        estado_bot["ciclos_en_posicion"] += 1

    # --- Datos de mercado ---
    try:
        from src.mercado.binance_client import obtener_datos_completos
        indicadores, reporte_mercado = obtener_datos_completos()
        precio = float(indicadores["precio"])
        registro.update({
            "precio_btc":       precio,
            "rsi":              float(indicadores["rsi"]),
            "rsi_zona":         indicadores["rsi_zona"],
            "macd_cruce":       indicadores["macd_cruce"],
            "bb_posicion":      indicadores["bb_posicion"],
            "tendencia_ema":    indicadores["tendencia_ema"],
            "volumen_relativo": float(indicadores["volumen_relativo"]),
        })
        console.print(
            f"[cyan]📊 BTC=${precio:,.2f} | RSI={indicadores['rsi']:.1f} ({indicadores['rsi_zona']}) | "
            f"MACD={indicadores['macd_cruce']} | BB={indicadores['bb_posicion']}[/cyan]"
        )
    except Exception as e:
        console.print(f"[red]❌ Error Binance: {e}[/red]")
        logger.error(f"Error obteniendo datos de mercado: {e}")
        registro["error"] = str(e)
        registro["tiempo_ciclo_seg"] = round(time.time() - inicio, 1)
        return registro

    # --- Verificar SL/TP automáticos ---
    sl_tp_activado = verificar_sl_tp(precio, ciclo)
    venta_tiempo   = False
    if not sl_tp_activado:
        venta_tiempo = verificar_venta_por_tiempo(precio, ciclo)

    # --- Noticias ---
    try:
        from src.noticias.feed_manager import obtener_resumen_noticias
        noticias, texto_noticias_raw = obtener_resumen_noticias()
        texto_noticias = truncar_noticias(texto_noticias_raw)
        registro["noticias_count"] = len(noticias)
        console.print(f"[yellow]📰 {len(noticias)} noticias recientes[/yellow]")
        del texto_noticias_raw
    except Exception:
        texto_noticias = "No se pudieron obtener noticias."
        noticias       = []
        registro["noticias_count"] = 0

    ctx_posicion = contexto_posicion_para_ia()

    # --- Prompt Agente Técnico (GPU0) ---
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

    # --- Prompt Agente Fundamental (GPU1) ---
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
        console.print(
            f"[dim]🔵 GPU0 Técnico ({tiempo_t:.1f}s):[/dim] "
            f"[{color_t}]{accion_t}[/{color_t}] ({confianza_t}%) — {just_t[:80]}"
        )
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
        console.print(
            f"[dim]🟡 GPU1 Fundamental ({tiempo_f:.1f}s):[/dim] "
            f"[{color_f}]{impacto_f}[/{color_f}] ({intensidad_f}%) — {just_f[:80]}"
        )
    else:
        impacto_f, intensidad_f, just_f = "NEUTRAL", 0, "Error GPU1"
        console.print("[red]❌ GPU1 sin respuesta[/red]")

    registro["decision_fundamental"]      = impacto_f
    registro["intensidad_fundamental"]    = intensidad_f
    registro["justificacion_fundamental"] = just_f[:300]

    # --- LÓGICA DE DECISIÓN ---
    sl_r       = estado_bot["sl_pct"]
    tp_r       = estado_bot["tp_pct"]
    decision_r = "ESPERAR"
    motivo_r   = ""

    if sl_tp_activado or venta_tiempo:
        decision_r = "VENTA"
        motivo_r   = "Venta automática (SL/TP/Tiempo)"

    elif not estado_bot["en_posicion"]:
        # SIN POSICIÓN: decisión directa por Técnico + Fundamental
        if accion_t == "COMPRA" and confianza_t >= 65 and impacto_f != "BAJISTA":
            decision_r = "COMPRA"
            motivo_r   = f"Técnico COMPRA ({confianza_t}%) + Fundamental {impacto_f}. {just_t[:120]}"
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
            console.print(f"[yellow]⏸️  ESPERAR: Técnico={accion_t} ({confianza_t}%)[/yellow]")

    else:
        # CON POSICIÓN: GPU2 decide si vender o mantener
        pc         = estado_bot["precio_compra"]
        pnl_actual = (precio - pc) / pc * 100

        prompt_r = f"""Eres el Gestor de Riesgos de un bot de trading de Bitcoin.
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

    estado_bot["sl_pct"] = sl_r
    estado_bot["tp_pct"] = tp_r

    # --- Ejecutar decisión ---
    if not sl_tp_activado and not venta_tiempo:
        if decision_r == "COMPRA":
            ejecutar_compra(precio, ciclo, motivo_r)
        elif decision_r == "VENTA":
            ejecutar_venta(precio, ciclo, "VENTA", motivo_r)

    # --- Mostrar estado ---
    mostrar_estado(precio)

    # --- Agregar datos de saldo al registro ---
    usdt_actual, btc_actual = obtener_saldo_actual()
    vt = usdt_actual + (btc_actual * precio)
    registro["saldo_usdt"]         = round(usdt_actual, 2)
    registro["saldo_btc"]          = round(btc_actual, 8)
    registro["valor_total_usdt"]   = round(vt, 2)
    registro["rendimiento_pct"]    = round(((vt - CAPITAL_INICIAL) / CAPITAL_INICIAL) * 100, 4)
    registro["en_posicion"]        = estado_bot["en_posicion"]
    registro["ganancia_total"]     = round(estado_bot["ganancia_total"], 2)
    registro["ciclos_en_posicion"] = estado_bot["ciclos_en_posicion"]
    registro["tiempo_ciclo_seg"]   = round(time.time() - inicio, 1)

    logger.info(
        f"Ciclo #{ciclo} completado | BTC=${precio:,.2f} | "
        f"Decision={decision_r} | Saldo=${usdt_actual:,.2f} USDT | "
        f"Tiempo={registro['tiempo_ciclo_seg']}s"
    )
    return registro


# ==============================================================================
# BUCLE PRINCIPAL
# ==============================================================================

def main():
    # Inicializar trader Binance
    trader_ok = inicializar_trader()

    # Inicializar DB
    db_disponible = False
    try:
        from src.trading.base_datos import verificar_conexion, crear_tablas
        ok, msg = verificar_conexion()
        if ok:
            crear_tablas()
            db_disponible = True
            console.print(f"[green]✅ PostgreSQL conectado[/green]")
        else:
            console.print(f"[yellow]⚠️  PostgreSQL no disponible — solo CSV[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Error DB: {e} — solo CSV[/yellow]")

    # Banner de inicio
    modo_str   = "[bold red]🔴 REAL[/bold red]" if MODO_REAL else "[bold yellow]🟡 SIMULADO[/bold yellow]"
    entorno_str = "[bold orange1]TESTNET[/bold orange1]" if BINANCE_TESTNET else "[bold red]⚠️  PRODUCCIÓN REAL[/bold red]"

    console.print(Panel.fit(
        f"[bold cyan]🤖 MOTOR DE TRADING — CryptoIA[/bold cyan]\n"
        f"Modo: {modo_str} | Entorno: {entorno_str}\n"
        f"Capital operativo: [bold green]${CAPITAL_INICIAL:,.2f} USDT[/bold green] | "
        f"Intervalo: [yellow]{INTERVALO_MINUTOS} min[/yellow]\n"
        f"Stop-Loss: [red]-{STOP_LOSS_PCT}%[/red] | "
        f"Take-Profit: [green]+{TAKE_PROFIT_PCT}%[/green] | "
        f"Máx ciclos en posición: [yellow]{CICLOS_MAX_EN_POSICION}[/yellow]\n"
        f"API disponible en: [cyan]http://0.0.0.0:8000[/cyan] (si está corriendo)\n"
        "Detener con: [bold]Ctrl+C[/bold]",
        border_style="cyan"
    ))

    if MODO_REAL and not trader_ok:
        console.print("[bold red]⚠️  MODO_REAL=true pero Binance no conectó — abortando[/bold red]")
        console.print("[yellow]Verificá BINANCE_API_KEY y BINANCE_SECRET en el .env[/yellow]")
        sys.exit(1)

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
                            # Adaptar estado_bot al formato de billetera esperado por base_datos
                            billetera_compat = {
                                "usdt":           estado_bot["saldo_usdt"],
                                "btc":            estado_bot["saldo_btc"],
                                "precio_compra":  estado_bot["precio_compra"],
                                "en_posicion":    estado_bot["en_posicion"],
                                "ganancia_total": estado_bot["ganancia_total"],
                                "operaciones":    estado_bot["operaciones"],
                                "sl_pct":         estado_bot["sl_pct"],
                                "tp_pct":         estado_bot["tp_pct"],
                            }
                            guardar_estado_billetera(billetera_compat, ciclo, float(precio_db), "CICLO")
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
                logger.error(f"Error en ciclo #{ciclo}: {e}", exc_info=True)
                err_registro = {
                    "ciclo": ciclo, "error": str(e),
                    "timestamp": ahora_ba().strftime("%Y-%m-%d %H:%M:%S"),
                    "modo_real": MODO_REAL,
                }
                guardar_en_csv(err_registro)
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
        console.print("\n\n[bold yellow]🛑 Motor de trading detenido.[/bold yellow]")
        estado_bot["activo"] = False

        usdt_f, btc_f = obtener_saldo_actual()
        excedente_final = max(0, usdt_f - CAPITAL_INICIAL)
        console.print(f"\n[bold]📊 Resumen final:[/bold]")
        console.print(f"  Operaciones: {len(estado_bot['operaciones'])}")
        console.print(f"  Saldo USDT final: ${usdt_f:,.2f} USDT")
        console.print(f"  Ganancia/pérdida total: ${estado_bot['ganancia_total']:+,.2f} USDT")
        console.print(f"  [bold yellow]Ganancias resguardadas: ${excedente_final:,.2f} USDT[/bold yellow]")

        if estado_bot["operaciones"]:
            console.print(f"\n[bold]Detalle de operaciones:[/bold]")
            for op in estado_bot["operaciones"]:
                tipo  = op["tipo"]
                color = "green" if tipo in ("VENTA_TP", "VENTA", "VENTA_TIEMPO") else \
                        "red" if tipo == "VENTA_SL" else "cyan"
                ganancia_str = (
                    f" | P&L: ${op.get('ganancia', 0):+,.2f} ({op.get('ganancia_pct', 0):+.2f}%)"
                    if "ganancia" in op else ""
                )
                console.print(
                    f"   [{color}]• Ciclo #{op['ciclo']}: {tipo} a "
                    f"${op['precio']:,.2f}{ganancia_str} [{op.get('modo','?')}][/{color}]"
                )
        sys.exit(0)
