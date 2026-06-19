"""
tests/test_binance_trader.py — Test de conexión a Binance Testnet

Verifica que el cliente BinanceTrader puede conectarse al testnet
y obtener datos básicos (precio, saldo). NO ejecuta órdenes reales.

Requisitos:
  - BINANCE_API_KEY y BINANCE_SECRET en el .env (de testnet.binance.vision)
  - BINANCE_TESTNET=true en el .env

Ejecutar:
    python tests/test_binance_trader.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

console = Console()


def main():
    console.print(Panel.fit(
        "[bold cyan]🧪 TEST — Binance Trader[/bold cyan]\n"
        "[yellow]⚠️  Solo lectura — NO ejecuta órdenes[/yellow]",
        border_style="cyan"
    ))

    # Cargar config
    from config import (
        BINANCE_API_KEY, BINANCE_SECRET,
        BINANCE_TESTNET, MODO_REAL, SIMBOLO
    )

    console.print(f"\n[dim]API Key: {'***' + BINANCE_API_KEY[-4:] if len(BINANCE_API_KEY) > 4 else '⚠️  NO DEFINIDA'}[/dim]")
    console.print(f"[dim]Testnet: {BINANCE_TESTNET}[/dim]")
    console.print(f"[dim]Modo Real: {MODO_REAL}[/dim]")
    console.print(f"[dim]Símbolo: {SIMBOLO}[/dim]\n")

    if not BINANCE_API_KEY or not BINANCE_SECRET:
        console.print("[bold red]❌ BINANCE_API_KEY o BINANCE_SECRET no definidos en .env[/bold red]")
        console.print("[yellow]Obtener en: https://testnet.binance.vision/[/yellow]")
        return 1

    # Crear trader
    from src.trading.binance_trader import BinanceTrader
    trader = BinanceTrader(
        api_key   = BINANCE_API_KEY,
        secret    = BINANCE_SECRET,
        testnet   = BINANCE_TESTNET,
        modo_real = False,  # siempre False en test
        simbolo   = SIMBOLO,
    )

    # =========================================================================
    # TEST 1: Conexión
    # =========================================================================
    console.print(Rule("[bold cyan]TEST 1 — Conexión[/bold cyan]"))
    ok, msg = trader.inicializar()
    if ok:
        console.print(f"[green]✅ {msg}[/green]")
    else:
        console.print(f"[red]❌ {msg}[/red]")
        return 1

    # =========================================================================
    # TEST 2: Precio actual
    # =========================================================================
    console.print(Rule("[bold cyan]TEST 2 — Precio actual[/bold cyan]"))
    ok, precio = trader.obtener_precio()
    if ok and precio > 0:
        console.print(f"[green]✅ Precio {SIMBOLO}: ${precio:,.2f} USDT[/green]")
    else:
        console.print(f"[red]❌ No se pudo obtener precio[/red]")

    # =========================================================================
    # TEST 3: Saldo de la cuenta
    # =========================================================================
    console.print(Rule("[bold cyan]TEST 3 — Saldo de la cuenta[/bold cyan]"))
    ok, saldo = trader.obtener_saldo()
    if ok:
        tabla = Table(title="💰 Saldo en Binance Testnet", show_header=True, header_style="bold green")
        tabla.add_column("Moneda", style="cyan")
        tabla.add_column("Disponible", style="green")
        tabla.add_row("USDT", f"${saldo['usdt']:,.4f}")
        tabla.add_row("BTC",  f"{saldo['btc']:.8f}")
        tabla.add_row("Total (USDT)", f"${saldo['total_usdt']:,.2f}")
        console.print(tabla)
    else:
        console.print(f"[red]❌ Error obteniendo saldo: {saldo.get('error')}[/red]")

    # =========================================================================
    # TEST 4: Estado del trader
    # =========================================================================
    console.print(Rule("[bold cyan]TEST 4 — Estado del trader[/bold cyan]"))
    estado = trader.estado()
    tabla2 = Table(title="⚙️  Estado del Trader", show_header=False, box=None)
    tabla2.add_column("Campo", style="cyan", width=20)
    tabla2.add_column("Valor", style="white")
    for k, v in estado.items():
        tabla2.add_row(k, str(v))
    console.print(tabla2)

    # =========================================================================
    # TEST 5: Simulación de compra (DRY-RUN)
    # =========================================================================
    console.print(Rule("[bold cyan]TEST 5 — Simulación de compra (DRY-RUN)[/bold cyan]"))
    console.print("[dim]Simulando compra de $100 USDT (sin ejecutar nada real)...[/dim]")
    ok, resultado = trader.comprar(usdt_amount=100)
    if ok:
        console.print(f"[green]✅ Simulación OK:[/green]")
        for k, v in resultado.items():
            console.print(f"   [dim]{k}:[/dim] {v}")
    else:
        console.print(f"[red]❌ Error en simulación: {resultado.get('error')}[/red]")

    # =========================================================================
    # RESUMEN
    # =========================================================================
    console.print(Panel.fit(
        "[bold green]✅ Tests completados[/bold green]\n"
        f"Entorno: [bold]{'TESTNET' if BINANCE_TESTNET else 'PRODUCCIÓN'}[/bold]\n"
        f"Precio BTC: [bold]${precio:,.2f}[/bold] USDT\n"
        "[yellow]Para activar trading real: MODO_REAL=true en .env[/yellow]",
        border_style="green"
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
