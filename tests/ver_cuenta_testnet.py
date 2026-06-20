"""
tests/ver_cuenta_testnet.py — Muestra el estado real de la cuenta en Binance Testnet

Uso:
    python tests/ver_cuenta_testnet.py

Muestra:
  - Saldo USDT y BTC disponible en la cuenta Testnet
  - Precio actual de BTC/USDT
  - Valor total de la cuenta en USDT
  - Últimas 10 órdenes ejecutadas
  - Estado de conexión y configuración
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
    from config import (
        BINANCE_API_KEY, BINANCE_SECRET,
        BINANCE_TESTNET, MODO_REAL, SIMBOLO,
        CAPITAL_INICIAL,
    )

    # ── Banner ──────────────────────────────────────────────────────────────
    entorno = "TESTNET" if BINANCE_TESTNET else "⚠️  PRODUCCIÓN REAL"
    modo    = "REAL" if MODO_REAL else "DRY-RUN (simulación)"

    console.print(Panel.fit(
        f"[bold cyan]🔍 Estado de Cuenta Binance — {entorno}[/bold cyan]\n"
        f"Símbolo: [yellow]{SIMBOLO}[/yellow] | Modo: [yellow]{modo}[/yellow]\n"
        f"Capital operativo configurado: [green]${CAPITAL_INICIAL:,.2f} USDT[/green]",
        border_style="cyan"
    ))

    # ── Verificar credenciales ───────────────────────────────────────────────
    if not BINANCE_API_KEY or BINANCE_API_KEY == "TU_BINANCE_API_KEY_AQUI":
        console.print("[bold red]❌ BINANCE_API_KEY no configurada en el .env[/bold red]")
        console.print("[yellow]   Editá el archivo .env y completá BINANCE_API_KEY y BINANCE_SECRET[/yellow]")
        sys.exit(1)

    if not BINANCE_SECRET or BINANCE_SECRET == "TU_BINANCE_SECRET_AQUI":
        console.print("[bold red]❌ BINANCE_SECRET no configurada en el .env[/bold red]")
        sys.exit(1)

    # ── Conectar ─────────────────────────────────────────────────────────────
    console.print("\n[yellow]⏳ Conectando a Binance...[/yellow]")
    from src.trading.binance_trader import BinanceTrader

    trader = BinanceTrader(
        api_key   = BINANCE_API_KEY,
        secret    = BINANCE_SECRET,
        testnet   = BINANCE_TESTNET,
        modo_real = MODO_REAL,
        simbolo   = SIMBOLO,
    )

    ok, msg = trader.inicializar()
    if not ok:
        console.print(f"[bold red]❌ Error de conexión: {msg}[/bold red]")
        console.print("\n[yellow]Posibles causas:[/yellow]")
        console.print("  • Las claves API son incorrectas")
        console.print("  • La cuenta Testnet no tiene claves activas")
        console.print("  • Sin acceso a internet o firewall bloqueando")
        console.print("\n[cyan]Obtener claves Testnet en: https://testnet.binance.vision/[/cyan]")
        sys.exit(1)

    console.print(f"[green]✅ {msg}[/green]")

    # ── Precio actual ────────────────────────────────────────────────────────
    console.print(Rule("[bold]Precio Actual[/bold]"))
    ok_p, precio = trader.obtener_precio()
    if ok_p and precio > 0:
        console.print(f"  [bold cyan]BTC/USDT: ${precio:,.2f} USDT[/bold cyan]")
    else:
        console.print("[red]❌ No se pudo obtener el precio actual[/red]")
        precio = 0.0

    # ── Saldo de la cuenta ───────────────────────────────────────────────────
    console.print(Rule("[bold]Saldo de la Cuenta[/bold]"))
    ok_s, saldo = trader.obtener_saldo()

    if ok_s:
        usdt       = saldo.get("usdt", 0.0)
        btc        = saldo.get("btc", 0.0)
        total_usdt = saldo.get("total_usdt", usdt + btc * precio)

        rendimiento = ((total_usdt - CAPITAL_INICIAL) / CAPITAL_INICIAL * 100) if CAPITAL_INICIAL > 0 else 0
        color_rend  = "green" if rendimiento >= 0 else "red"
        signo       = "+" if rendimiento >= 0 else ""

        tabla_saldo = Table(show_header=False, box=None, padding=(0, 2))
        tabla_saldo.add_column("Campo", style="cyan", width=30)
        tabla_saldo.add_column("Valor", style="white")

        tabla_saldo.add_row("USDT disponible",          f"[bold green]${usdt:,.4f} USDT[/bold green]")
        tabla_saldo.add_row("BTC disponible",           f"[bold yellow]{btc:.8f} BTC[/bold yellow]")
        if precio > 0:
            tabla_saldo.add_row("Valor BTC en USDT",    f"${btc * precio:,.2f} USDT")
        tabla_saldo.add_row("─" * 28,                   "─" * 20)
        tabla_saldo.add_row("Valor total de la cuenta", f"[bold]${total_usdt:,.2f} USDT[/bold]")
        tabla_saldo.add_row("Capital inicial configurado", f"${CAPITAL_INICIAL:,.2f} USDT")
        tabla_saldo.add_row("Rendimiento vs capital",   f"[{color_rend}]{signo}{rendimiento:.2f}%[/{color_rend}]")

        console.print(tabla_saldo)
    else:
        console.print(f"[red]❌ Error obteniendo saldo: {saldo.get('error', 'desconocido')}[/red]")

    # ── Últimas órdenes ──────────────────────────────────────────────────────
    console.print(Rule("[bold]Últimas Órdenes Ejecutadas[/bold]"))
    ok_o, ordenes = trader.obtener_ordenes_recientes(limit=10)

    if ok_o and ordenes:
        tabla_ord = Table(
            "Fecha/Hora", "Tipo", "Estado", "Precio", "Cantidad BTC", "Total USDT",
            show_header=True, header_style="bold cyan"
        )
        for o in reversed(ordenes):
            tipo    = str(o.get("tipo", "?"))
            estado  = str(o.get("estado", "?"))
            precio_o = o.get("precio") or 0
            cant    = o.get("cantidad") or 0
            costo   = o.get("costo") or (cant * precio_o if cant and precio_o else 0)
            ts      = str(o.get("timestamp", ""))[:19].replace("T", " ")

            color_tipo = "green" if tipo == "BUY" else "red"
            tabla_ord.add_row(
                ts,
                f"[{color_tipo}]{tipo}[/{color_tipo}]",
                estado,
                f"${float(precio_o):,.2f}" if precio_o else "—",
                f"{float(cant):.6f}" if cant else "—",
                f"${float(costo):,.2f}" if costo else "—",
            )
        console.print(tabla_ord)
    elif ok_o and not ordenes:
        console.print("[yellow]  Sin órdenes ejecutadas en esta cuenta[/yellow]")
    else:
        console.print("[yellow]  No se pudieron obtener las órdenes (puede ser normal en Testnet)[/yellow]")

    # ── Resumen de configuración ─────────────────────────────────────────────
    console.print(Rule("[bold]Configuración Activa[/bold]"))
    from config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, INTERVALO_MINUTOS, TEMPORALIDAD
    from config import TRAILING_STOP_ACTIVACION_PCT, TRAILING_STOP_PROTECCION_PCT, VENTA_DEFENSIVA_PNL_MIN_PCT

    tabla_cfg = Table(show_header=False, box=None, padding=(0, 2))
    tabla_cfg.add_column("Parámetro", style="cyan", width=35)
    tabla_cfg.add_column("Valor", style="white")

    tabla_cfg.add_row("Entorno",                    f"[bold]{'TESTNET' if BINANCE_TESTNET else 'PRODUCCIÓN'}[/bold]")
    tabla_cfg.add_row("Modo de ejecución",          f"{'REAL (órdenes reales)' if MODO_REAL else 'DRY-RUN (sin órdenes)'}")
    tabla_cfg.add_row("Temporalidad velas",         TEMPORALIDAD)
    tabla_cfg.add_row("Intervalo entre ciclos",     f"{INTERVALO_MINUTOS} minutos")
    tabla_cfg.add_row("Stop-Loss fijo",             f"[red]-{STOP_LOSS_PCT}%[/red]")
    tabla_cfg.add_row("Take-Profit fijo",           f"[green]+{TAKE_PROFIT_PCT}%[/green]")
    tabla_cfg.add_row("Trailing Stop (activación)", f"P&L >= +{TRAILING_STOP_ACTIVACION_PCT}%")
    tabla_cfg.add_row("Trailing Stop (protección)", f"Protege +{TRAILING_STOP_PROTECCION_PCT}% de ganancia")
    tabla_cfg.add_row("Venta defensiva (mín P&L)",  f"P&L >= +{VENTA_DEFENSIVA_PNL_MIN_PCT}% con señal bajista")

    console.print(tabla_cfg)
    console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelado por el usuario.[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error inesperado: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
