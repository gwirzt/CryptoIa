"""
tests/test_ciclo.py — Ejecuta UN ciclo completo del bot y muestra el resultado
Útil para verificar que todo funciona antes de iniciar el bot en producción.
Uso: python tests/test_ciclo.py
"""
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]🧪 TEST DE CICLO ÚNICO — CryptoIA v2[/bold cyan]\n"
        "Ejecuta un ciclo completo sin esperar el intervalo",
        border_style="cyan"
    ))

    # 1. Inicializar DB
    console.print("\n[yellow]1. Inicializando base de datos...[/yellow]")
    from src.trading.posicion import inicializar_db
    inicializar_db()
    console.print("   ✅ DB OK")

    # 2. Obtener mercado
    console.print("\n[yellow]2. Obteniendo datos de mercado...[/yellow]")
    from src.mercado.datos import obtener_velas, resumen_indicadores
    df = obtener_velas(limite=100)
    indicadores = resumen_indicadores(df)
    console.print(f"   Precio:  ${indicadores['precio']:,.2f}")
    console.print(f"   RSI:     {indicadores['rsi']}")
    console.print(f"   MACD:    {indicadores['macd']:.4f} | Signal: {indicadores['macd_signal']:.4f}")
    console.print(f"   EMAs:    9={indicadores['ema9']:,.0f} | 21={indicadores['ema21']:,.0f} | 50={indicadores['ema50']:,.0f}")
    console.print(f"   Tendencia: {'▲ ALCISTA' if indicadores['ema_alcista'] else '▼ BAJISTA' if indicadores['ema_bajista'] else '↔ MIXTA'}")

    # 3. Ver posición actual
    console.print("\n[yellow]3. Verificando posición actual...[/yellow]")
    from src.trading.posicion import obtener_posicion, calcular_pnl
    posicion = obtener_posicion(indicadores.get("simbolo", "BTC/USDT") if False else __import__('config').SIMBOLO)
    posicion_con_pnl = None
    if posicion:
        posicion_con_pnl = calcular_pnl(posicion, indicadores["precio"])
        signo = "+" if posicion_con_pnl["pnl_pct"] >= 0 else ""
        console.print(f"   [green]Posición abierta @ ${posicion['precio_compra']:,.2f}[/green]")
        console.print(f"   P&L: {signo}{posicion_con_pnl['pnl_pct']:.2f}% ({signo}${posicion_con_pnl['pnl_usdt']:.2f})")
    else:
        console.print("   Sin posición abierta")

    # 4. Consultar IA
    console.print("\n[yellow]4. Consultando IA...[/yellow]")
    from src.ia.agente import consultar_ia
    from config import SIMBOLO, TEMPORALIDAD
    decision = consultar_ia(
        indicadores=indicadores,
        posicion=posicion_con_pnl,
        simbolo=SIMBOLO,
        temporalidad=TEMPORALIDAD,
    )
    color = {"COMPRAR": "green", "VENDER": "red", "ESPERAR": "yellow"}.get(decision["decision"], "white")
    console.print(f"   Decisión:  [{color}]{decision['decision']}[/{color}]")
    console.print(f"   Confianza: {decision['confianza']}%")
    console.print(f"   Razón:     {decision['razon']}")

    # 5. Resumen
    console.print(Panel.fit(
        f"[bold]Resultado del ciclo:[/bold]\n"
        f"  Precio:   ${indicadores['precio']:,.2f}\n"
        f"  Decisión: [{color}]{decision['decision']}[/{color}] ({decision['confianza']}%)\n"
        f"  Razón:    {decision['razon']}",
        border_style=color,
        title="✅ Ciclo completado"
    ))


if __name__ == "__main__":
    main()
