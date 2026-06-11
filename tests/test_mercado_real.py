"""
tests/test_mercado_real.py — Test del módulo de mercado con datos reales de Binance
Muestra los indicadores técnicos actuales de BTC/USDT en tiempo real.

Ejecutar con:
    venv\Scripts\python.exe tests\test_mercado_real.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def ejecutar_test():
    console.print(Panel.fit(
        "[bold cyan]📊 TEST — MERCADO REAL (Binance)[/bold cyan]\n"
        "Obteniendo datos en tiempo real de BTC/USDT",
        border_style="cyan"
    ))

    console.print("\n[yellow]⏳ Conectando a Binance y calculando indicadores...[/yellow]")

    try:
        from src.mercado.binance_client import obtener_datos_completos
        indicadores, reporte = obtener_datos_completos()

        # Tabla de indicadores
        tabla = Table(title=f"📈 Indicadores Reales — {indicadores['simbolo']} ({indicadores['temporalidad']})",
                      show_header=True, header_style="bold magenta")
        tabla.add_column("Indicador", style="cyan", no_wrap=True, min_width=22)
        tabla.add_column("Valor", style="white", min_width=20)
        tabla.add_column("Señal", style="green", min_width=15)

        # Precio
        signo = "+" if indicadores["variacion_pct"] >= 0 else ""
        color_var = "green" if indicadores["variacion_pct"] >= 0 else "red"
        tabla.add_row("💰 Precio actual",
                      f"${indicadores['precio']:,.2f} USDT",
                      f"[{color_var}]{signo}{indicadores['variacion_pct']}%[/{color_var}]")

        # RSI
        rsi = indicadores["rsi"]
        rsi_zona = indicadores["rsi_zona"]
        color_rsi = "red" if rsi > 70 else "green" if rsi < 30 else "yellow"
        tabla.add_row("📊 RSI (14)",
                      f"{rsi}",
                      f"[{color_rsi}]{rsi_zona}[/{color_rsi}]")

        # MACD
        macd_cruce = indicadores["macd_cruce"]
        color_macd = "green" if "ALCISTA" in macd_cruce or macd_cruce == "POSITIVO" else "red"
        tabla.add_row("📉 MACD Histograma",
                      f"{indicadores['macd_hist']}",
                      f"[{color_macd}]{macd_cruce}[/{color_macd}]")

        # Bollinger
        bb_pos = indicadores["bb_posicion"]
        color_bb = "green" if bb_pos == "INFERIOR" else "red" if bb_pos == "SUPERIOR" else "yellow"
        tabla.add_row("🎯 Bollinger",
                      f"${indicadores['bb_lower']:,.0f} — ${indicadores['bb_upper']:,.0f}",
                      f"[{color_bb}]Precio en banda {bb_pos}[/{color_bb}]")

        # EMAs
        tend_ema = indicadores["tendencia_ema"]
        color_ema = "green" if tend_ema == "ALCISTA" else "red"
        tabla.add_row("📈 EMA 9 / EMA 21",
                      f"${indicadores['ema9']:,.2f} / ${indicadores['ema21']:,.2f}",
                      f"[{color_ema}]{tend_ema}[/{color_ema}]")

        # Volumen
        vol_rel = indicadores["volumen_relativo"]
        color_vol = "green" if vol_rel > 120 else "yellow" if vol_rel > 80 else "red"
        tabla.add_row("📦 Volumen relativo",
                      f"{indicadores['volumen']:,.2f}",
                      f"[{color_vol}]{vol_rel}% del promedio[/{color_vol}]")

        # Tendencia 5 velas
        tend5 = indicadores["tendencia_5v"]
        color_t5 = "green" if tend5 == "ALCISTA" else "red"
        tabla.add_row("🕯️  Tendencia 5 velas",
                      "",
                      f"[{color_t5}]{tend5}[/{color_t5}]")

        console.print("\n", tabla)
        console.print(f"\n[dim]⏰ Timestamp: {indicadores['timestamp']}[/dim]")

        # Mostrar el reporte que se enviará a la IA
        console.print(Panel(reporte, title="📤 Reporte que se enviará al Agente Técnico (GPU 0)",
                            border_style="cyan"))

        console.print(Panel.fit(
            "[bold green]✅ TEST PASADO — Datos reales obtenidos correctamente[/bold green]\n"
            f"Precio actual: ${indicadores['precio']:,.2f} USDT | RSI: {indicadores['rsi']}",
            border_style="green"
        ))
        return 0

    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1


if __name__ == "__main__":
    sys.exit(ejecutar_test())
