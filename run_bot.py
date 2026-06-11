"""
run_bot.py — Punto de entrada principal del CryptoIA Trading Bot
Uso: python run_bot.py
"""
import sys
import os
from rich.console import Console
from rich.panel import Panel

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]🤖 CryptoIA Trading Bot[/bold cyan]\n"
        "Sistema Multi-Agente de Trading con IAs Locales\n"
        "[dim]Servidor: 192.168.1.8 | Exchange: Binance | Activo: BTC/USDT[/dim]",
        border_style="cyan"
    ))

    # 1. Verificar conectividad antes de arrancar
    console.print("\n[yellow]🔌 Verificando conectividad con todos los servicios...[/yellow]")
    from tests.test_conexion import ejecutar_tests
    resultado = ejecutar_tests()

    if resultado != 0:
        console.print("\n[bold red]❌ No se puede iniciar el bot: hay servicios sin conexión.[/bold red]")
        console.print("[dim]Ejecutá 'python tests/test_conexion.py' para más detalles.[/dim]")
        sys.exit(1)

    # 2. Iniciar el motor principal (se implementará en FASE 4)
    console.print("\n[bold green]✅ Todos los servicios OK. Iniciando motor de trading...[/bold green]")
    console.print("[dim]⚠️  Motor principal pendiente de implementación (FASE 4)[/dim]")

    # TODO FASE 4: from src.trading.motor_principal import ejecutar_bot
    # TODO FASE 4: ejecutar_bot()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]🛑 Bot detenido por el usuario.[/bold yellow]")
        sys.exit(0)
