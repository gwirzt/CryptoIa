"""
tests/test_comite_real.py — Test del comité completo con datos reales
Los 3 agentes analizan el mercado real de Binance + noticias RSS reales.
NO ejecuta ninguna operación — solo observa y registra.

Ejecutar con:
    venv\Scripts\python.exe tests\test_comite_real.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import requests
from src.agentes.normalizador import (
    normalizar_respuesta_tecnico,
    normalizar_respuesta_fundamental,
    normalizar_respuesta_riesgo
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from config import (
    SERVIDOR_IA,
    PUERTO_GPU0, MODELO_GPU0,
    PUERTO_GPU1, MODELO_GPU1,
    PUERTO_GPU2, MODELO_GPU2,
    CAPITAL_INICIAL
)

console = Console()
TIMEOUT = 90


def consultar_ia(puerto: int, modelo: str, prompt: str) -> tuple[dict | None, float, str]:
    """Consulta a una IA Ollama. Devuelve (json_dict, tiempo_seg, texto_crudo)."""
    url = f"http://{SERVIDOR_IA}:{puerto}/api/generate"
    payload = {"model": modelo, "prompt": prompt, "stream": False, "format": "json"}
    inicio = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        tiempo = time.time() - inicio
        if resp.status_code != 200:
            return None, tiempo, f"HTTP {resp.status_code}"
        texto = resp.json().get("response", "").strip()
        try:
            return json.loads(texto), tiempo, texto
        except json.JSONDecodeError:
            i = texto.find('{')
            f = texto.rfind('}') + 1
            if i >= 0 and f > i:
                try:
                    return json.loads(texto[i:f]), tiempo, texto
                except json.JSONDecodeError:
                    pass
        return None, tiempo, texto
    except requests.exceptions.ConnectionError:
        return None, time.time() - inicio, f"Sin conexión a {SERVIDOR_IA}:{puerto}"
    except requests.exceptions.Timeout:
        return None, TIMEOUT, f"Timeout ({TIMEOUT}s)"
    except Exception as e:
        return None, time.time() - inicio, str(e)


def prompt_tecnico(reporte_mercado: str) -> str:
    return f"""Eres un analista técnico experto en criptomonedas. Analiza los siguientes datos REALES del mercado:

{reporte_mercado}

Basándote ÚNICAMENTE en estos datos técnicos reales, responde con un JSON válido:
{{"accion": "COMPRA", "confianza": 75, "justificacion": "texto breve en español de máximo 2 oraciones"}}

Donde "accion" es exactamente COMPRA, VENTA o ESPERAR. Solo el JSON, sin texto adicional."""


def prompt_fundamental(texto_noticias: str) -> str:
    return f"""Eres un analista fundamental experto en criptomonedas. Evalúa el impacto de estas noticias REALES en el precio de Bitcoin:

{texto_noticias}

Responde con un JSON válido:
{{"impacto": "ALCISTA", "intensidad": 70, "justificacion": "texto breve en español de máximo 2 oraciones"}}

Donde "impacto" es exactamente ALCISTA, BAJISTA o NEUTRAL. Solo el JSON, sin texto adicional."""


def prompt_riesgo(veredicto_t: dict, veredicto_f: dict, precio_actual: float) -> str:
    accion    = veredicto_t.get("accion", "ESPERAR")
    confianza = veredicto_t.get("confianza", 0)
    impacto   = veredicto_f.get("impacto", "NEUTRAL")
    intensidad = veredicto_f.get("intensidad", 0)

    return f"""Eres el Gestor de Riesgos de un bot de trading de Bitcoin. Toma la decisión final basándote en datos REALES:

ANALISTA TÉCNICO: {accion} (confianza: {confianza}%)
ANALISTA FUNDAMENTAL: {impacto} (intensidad: {intensidad}%)
PRECIO ACTUAL BTC: ${precio_actual:,.2f} USDT
BILLETERA: {CAPITAL_INICIAL:,.0f} USDT disponibles, sin posición abierta
MODO: Solo observación — NO se ejecutarán operaciones reales

Reglas de riesgo:
- Stop-Loss: entre 1.5% y 3.5%
- Take-Profit: entre 3% y 8%
- Nunca arriesgar más del 2% del capital por operación

Responde con un JSON válido:
{{"decision": "COMPRA", "stop_loss_pct": 2.5, "take_profit_pct": 5.0, "motivo": "texto breve en español"}}

Donde "decision" es exactamente COMPRA, VENTA o ESPERAR. Solo el JSON, sin texto adicional."""


def ejecutar_test():
    inicio_total = time.time()

    console.print(Panel.fit(
        "[bold magenta]🏛️  TEST — COMITÉ REAL (DATOS EN VIVO)[/bold magenta]\n"
        "[yellow]⚠️  MODO SOLO OBSERVACIÓN — No se ejecutan operaciones[/yellow]",
        border_style="magenta"
    ))

    # =========================================================================
    # OBTENER DATOS REALES
    # =========================================================================
    console.print(Rule("[bold cyan]OBTENIENDO DATOS REALES[/bold cyan]"))

    try:
        console.print("[yellow]📊 Conectando a Binance...[/yellow]")
        from src.mercado.binance_client import obtener_datos_completos
        indicadores, reporte_mercado = obtener_datos_completos()
        console.print(f"[green]✅ Mercado: BTC = ${indicadores['precio']:,.2f} | RSI: {indicadores['rsi']} | {indicadores['rsi_zona']}[/green]")
    except Exception as e:
        console.print(f"[red]❌ Error obteniendo datos de Binance: {e}[/red]")
        return 1

    try:
        console.print("[yellow]📰 Obteniendo noticias RSS...[/yellow]")
        from src.noticias.feed_manager import obtener_resumen_noticias
        noticias, texto_noticias = obtener_resumen_noticias()
        console.print(f"[green]✅ Noticias: {len(noticias)} encontradas[/green]")
        if noticias:
            for n in noticias[:3]:
                hace = f"{n['hace_minutos']}min" if n['hace_minutos'] else "?"
                console.print(f"   [dim]• [{n['fuente']}] {n['titulo'][:65]}... ({hace})[/dim]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Error en noticias: {e} — continuando sin noticias[/yellow]")
        texto_noticias = "No se pudieron obtener noticias en este momento."
        noticias = []

    # =========================================================================
    # PASO 1: AGENTE TÉCNICO (GPU 0)
    # =========================================================================
    console.print(Rule("[bold cyan]PASO 1/3 — Agente Técnico (GPU 0)[/bold cyan]"))
    console.print(f"[dim]{SERVIDOR_IA}:{PUERTO_GPU0} | {MODELO_GPU0}[/dim]")
    console.print("[yellow]⏳ Analizando mercado real...[/yellow]")

    datos_t, tiempo_t, texto_t = consultar_ia(PUERTO_GPU0, MODELO_GPU0, prompt_tecnico(reporte_mercado))

    datos_t = normalizar_respuesta_tecnico(datos_t)
    if datos_t.get("confianza", 0) > 0 or datos_t.get("accion") != "ESPERAR":
        accion = datos_t.get("accion", "ESPERAR")
        confianza = datos_t.get("confianza", 0)
        color = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(accion, "white")
        console.print(f"[green]✅ {tiempo_t:.1f}s[/green] → [{color}]{accion}[/{color}] ({confianza}%)")
        console.print(f"   [dim]{datos_t.get('justificacion', '')[:120]}[/dim]")
    else:
        console.print(f"[red]❌ Error GPU 0: {texto_t}[/red]")

    # =========================================================================
    # PASO 2: AGENTE FUNDAMENTAL (GPU 1)
    # =========================================================================
    console.print(Rule("[bold yellow]PASO 2/3 — Agente Fundamental (GPU 1)[/bold yellow]"))
    console.print(f"[dim]{SERVIDOR_IA}:{PUERTO_GPU1} | {MODELO_GPU1}[/dim]")
    console.print("[yellow]⏳ Analizando noticias reales...[/yellow]")

    datos_f, tiempo_f, texto_f = consultar_ia(PUERTO_GPU1, MODELO_GPU1, prompt_fundamental(texto_noticias))

    if datos_f:
        impacto = datos_f.get("impacto", "?")
        intensidad = datos_f.get("intensidad", "?")
        color = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(impacto, "white")
        console.print(f"[green]✅ {tiempo_f:.1f}s[/green] → [{color}]{impacto}[/{color}] ({intensidad}%)")
        console.print(f"   [dim]{datos_f.get('justificacion', '')[:120]}[/dim]")
    else:
        console.print(f"[red]❌ Error GPU 1: {texto_f}[/red]")
        datos_f = {"impacto": "NEUTRAL", "intensidad": 0, "justificacion": "Error"}

    # =========================================================================
    # PASO 3: GESTOR DE RIESGOS (GPU 2)
    # =========================================================================
    console.print(Rule("[bold red]PASO 3/3 — Gestor de Riesgos (GPU 2)[/bold red]"))
    console.print(f"[dim]{SERVIDOR_IA}:{PUERTO_GPU2} | {MODELO_GPU2}[/dim]")
    console.print("[yellow]⏳ Tomando decisión final...[/yellow]")

    datos_r, tiempo_r, texto_r = consultar_ia(
        PUERTO_GPU2, MODELO_GPU2,
        prompt_riesgo(datos_t, datos_f, indicadores["precio"])
    )

    if datos_r:
        decision = datos_r.get("decision", "?")
        sl = datos_r.get("stop_loss_pct", "?")
        tp = datos_r.get("take_profit_pct", "?")
        motivo = (datos_r.get("motivo") or datos_r.get("razon") or
                  datos_r.get("justificacion") or "Sin motivo")
        color = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(decision, "white")
        console.print(f"[green]✅ {tiempo_r:.1f}s[/green] → [{color}]{decision}[/{color}] | SL:-{sl}% TP:+{tp}%")
        console.print(f"   [dim]{str(motivo)[:120]}[/dim]")
    else:
        console.print(f"[red]❌ Error GPU 2: {texto_r}[/red]")
        datos_r = None

    # =========================================================================
    # RESUMEN FINAL
    # =========================================================================
    tiempo_total = time.time() - inicio_total
    console.print(Rule("[bold magenta]RESUMEN DEL COMITÉ REAL[/bold magenta]"))

    tabla = Table(title="🏛️ Decisión del Comité — Datos Reales", show_header=True, header_style="bold magenta")
    tabla.add_column("Agente",    style="cyan",  no_wrap=True, min_width=28)
    tabla.add_column("Veredicto", style="white", no_wrap=True, min_width=15)
    tabla.add_column("Nivel",     style="green", no_wrap=True, min_width=10)
    tabla.add_column("Tiempo",    style="dim",   no_wrap=True, min_width=8)

    accion_t = datos_t.get("accion", "ERROR")
    ct = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(accion_t, "red")
    tabla.add_row("🔵 Analista Técnico (GPU0)",
                  f"[{ct}]{accion_t}[/{ct}]",
                  f"{datos_t.get('confianza', 0)}%",
                  f"{tiempo_t:.1f}s")

    impacto_f = datos_f.get("impacto", "ERROR")
    cf = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(impacto_f, "red")
    tabla.add_row("🟡 Analista Fundamental (GPU1)",
                  f"[{cf}]{impacto_f}[/{cf}]",
                  f"{datos_f.get('intensidad', 0)}%",
                  f"{tiempo_f:.1f}s")

    if datos_r:
        decision_r = datos_r.get("decision", "ERROR")
        cr = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(decision_r, "red")
        sl_r = datos_r.get("stop_loss_pct", "?")
        tp_r = datos_r.get("take_profit_pct", "?")
        tabla.add_row("🔴 Gestor de Riesgos (GPU2)",
                      f"[bold {cr}]{decision_r}[/bold {cr}]",
                      f"SL:-{sl_r}% TP:+{tp_r}%",
                      f"{tiempo_r:.1f}s")
    else:
        tabla.add_row("🔴 Gestor de Riesgos (GPU2)", "[red]ERROR[/red]", "-", f"{tiempo_r:.1f}s")

    console.print(tabla)

    # Contexto del mercado
    console.print(f"\n[dim]📊 Contexto: BTC=${indicadores['precio']:,.2f} | RSI={indicadores['rsi']} ({indicadores['rsi_zona']}) | "
                  f"MACD={indicadores['macd_cruce']} | Bollinger={indicadores['bb_posicion']} | "
                  f"EMA={indicadores['tendencia_ema']}[/dim]")
    console.print(f"[dim]⏱️  Tiempo total: {tiempo_total:.1f}s[/dim]")

    if datos_r:
        decision_final = datos_r.get("decision", "?")
        color_final = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(decision_final, "white")
        console.print(Panel.fit(
            f"[bold green]✅ COMITÉ REAL COMPLETADO[/bold green]\n"
            f"Decisión: [bold {color_final}]{decision_final}[/bold {color_final}] "
            f"(precio real: ${indicadores['precio']:,.2f} USDT)\n"
            f"[yellow]⚠️  MODO OBSERVACIÓN — No se ejecutó ninguna operación[/yellow]",
            border_style="green"
        ))
        return 0
    else:
        console.print(Panel.fit("[bold red]❌ El Gestor de Riesgos no respondió[/bold red]", border_style="red"))
        return 1


if __name__ == "__main__":
    sys.exit(ejecutar_test())
