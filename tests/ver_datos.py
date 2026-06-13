"""
tests/ver_datos.py — Consulta rápida de la base de datos PostgreSQL
Muestra en consola el estado actual del bot: ciclos, estadísticas,
billetera hipotética y noticias procesadas.

Ejecutar con:
    venv\Scripts\python.exe tests\ver_datos.py
    venv\Scripts\python.exe tests\ver_datos.py --ciclos 50
    venv\Scripts\python.exe tests\ver_datos.py --hoy
    venv\Scripts\python.exe tests\ver_datos.py --compras
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.columns import Columns
from rich.text import Text

console = Console()

# Zona horaria Buenos Aires
try:
    from config import TIMEZONE as _TZ_STR
    TZ_BA = ZoneInfo(_TZ_STR)
except Exception:
    TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")


def ts_ba(ts) -> str:
    """Convierte un timestamp (datetime o str) a hora Argentina formateada."""
    if ts is None:
        return "N/A"
    if isinstance(ts, str):
        return ts[:19]
    try:
        if ts.tzinfo is None:
            # Sin zona → asumir UTC
            ts = ts.replace(tzinfo=timezone.utc)
        ts_local = ts.astimezone(TZ_BA)
        return ts_local.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)[:19]


def parse_args():
    parser = argparse.ArgumentParser(description="Ver datos del bot CryptoIA en PostgreSQL")
    parser.add_argument("--ciclos",   type=int, default=20,  help="Cantidad de ciclos a mostrar (default: 20)")
    parser.add_argument("--hoy",      action="store_true",   help="Solo mostrar ciclos de hoy")
    parser.add_argument("--compras",  action="store_true",   help="Solo mostrar ciclos con decisión COMPRA")
    parser.add_argument("--ventas",   action="store_true",   help="Solo mostrar ciclos con decisión VENTA")
    parser.add_argument("--noticias", action="store_true",   help="Mostrar noticias en caché")
    parser.add_argument("--billetera",action="store_true",   help="Mostrar historial de billetera")
    parser.add_argument("--todo",     action="store_true",   help="Mostrar todo")
    return parser.parse_args()


def conectar():
    """Verifica conexión y devuelve True/False."""
    try:
        from src.trading.base_datos import verificar_conexion
        ok, msg = verificar_conexion()
        if not ok:
            console.print(f"[red]❌ Sin conexión a PostgreSQL: {msg[:100]}[/red]")
            return False
        return True
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        return False


def mostrar_resumen_general():
    """Muestra estadísticas generales del bot."""
    try:
        from src.trading.base_datos import get_session, CicloObservacion
        from sqlalchemy import func

        session = get_session()
        total = session.query(func.count(CicloObservacion.id)).scalar() or 0

        if total == 0:
            console.print("[yellow]⚠️  No hay ciclos registrados aún. ¿El bot está corriendo?[/yellow]")
            session.close()
            return

        compras  = session.query(func.count(CicloObservacion.id)).filter(CicloObservacion.decision_final == "COMPRA").scalar() or 0
        ventas   = session.query(func.count(CicloObservacion.id)).filter(CicloObservacion.decision_final == "VENTA").scalar() or 0
        esperar  = session.query(func.count(CicloObservacion.id)).filter(CicloObservacion.decision_final == "ESPERAR").scalar() or 0
        errores  = session.query(func.count(CicloObservacion.id)).filter(CicloObservacion.error.isnot(None)).scalar() or 0

        # Precio más reciente
        ultimo = session.query(CicloObservacion).order_by(CicloObservacion.id.desc()).first()
        precio_actual = ultimo.precio_btc if ultimo else 0
        ultimo_ts     = ts_ba(ultimo.timestamp) if ultimo else "N/A"
        ultimo_ciclo  = ultimo.ciclo if ultimo else 0

        # Precio más antiguo (para calcular variación)
        primero = session.query(CicloObservacion).order_by(CicloObservacion.id.asc()).first()
        precio_inicio = primero.precio_btc if primero else 0
        primer_ts     = ts_ba(primero.timestamp) if primero else "N/A"

        # Tiempo promedio de ciclo
        avg_tiempo = session.query(func.avg(CicloObservacion.tiempo_ciclo_seg)).scalar() or 0

        # RSI promedio
        avg_rsi = session.query(func.avg(CicloObservacion.rsi)).scalar() or 0

        session.close()

        # Calcular variación de precio
        var_precio = 0
        if precio_inicio and precio_actual:
            var_precio = ((precio_actual - precio_inicio) / precio_inicio) * 100

        color_var = "green" if var_precio >= 0 else "red"
        signo_var = "+" if var_precio >= 0 else ""

        # Panel de resumen
        tabla_resumen = Table(show_header=False, box=None, padding=(0, 2))
        tabla_resumen.add_column("Campo", style="cyan", width=22)
        tabla_resumen.add_column("Valor", style="white")

        tabla_resumen.add_row("Total ciclos",      f"[bold]{total}[/bold]")
        tabla_resumen.add_row("Último ciclo",       f"#{ultimo_ciclo} — {ultimo_ts}")
        tabla_resumen.add_row("Primer registro",    primer_ts)
        tabla_resumen.add_row("Precio BTC actual",  f"[bold]${precio_actual:,.2f}[/bold]" if precio_actual else "N/A")
        tabla_resumen.add_row("Variación período",  f"[{color_var}]{signo_var}{var_precio:.2f}%[/{color_var}]" if precio_inicio else "N/A")
        tabla_resumen.add_row("RSI promedio",       f"{avg_rsi:.1f}")
        tabla_resumen.add_row("Tiempo prom/ciclo",  f"{avg_tiempo:.1f}s")
        tabla_resumen.add_row("Errores",            f"[red]{errores}[/red]" if errores > 0 else "[green]0[/green]")

        # Panel de decisiones
        tabla_decisiones = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
        tabla_decisiones.add_column("Decisión", width=10)
        tabla_decisiones.add_column("Cantidad", width=8, justify="right")
        tabla_decisiones.add_column("Porcentaje", width=10, justify="right")

        tabla_decisiones.add_row(
            "[green]COMPRA[/green]",
            str(compras),
            f"[green]{compras/total*100:.1f}%[/green]"
        )
        tabla_decisiones.add_row(
            "[red]VENTA[/red]",
            str(ventas),
            f"[red]{ventas/total*100:.1f}%[/red]"
        )
        tabla_decisiones.add_row(
            "[yellow]ESPERAR[/yellow]",
            str(esperar),
            f"[yellow]{esperar/total*100:.1f}%[/yellow]"
        )

        console.print(Rule("[bold cyan]📊 RESUMEN GENERAL[/bold cyan]"))
        console.print(Columns([
            Panel(tabla_resumen,    title="Estado del Bot",    border_style="cyan"),
            Panel(tabla_decisiones, title="Distribución Decisiones", border_style="cyan"),
        ]))

    except Exception as e:
        console.print(f"[red]❌ Error en resumen: {e}[/red]")


def mostrar_ciclos(n: int = 20, solo_hoy: bool = False,
                   solo_compras: bool = False, solo_ventas: bool = False):
    """Muestra los últimos N ciclos en una tabla."""
    try:
        from src.trading.base_datos import get_session, CicloObservacion

        session = get_session()
        query = session.query(CicloObservacion)

        if solo_hoy:
            hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(CicloObservacion.timestamp >= hoy)
            titulo = f"Ciclos de HOY"
        elif solo_compras:
            query = query.filter(CicloObservacion.decision_final == "COMPRA")
            titulo = f"Ciclos con decisión COMPRA"
        elif solo_ventas:
            query = query.filter(CicloObservacion.decision_final == "VENTA")
            titulo = f"Ciclos con decisión VENTA"
        else:
            titulo = f"Últimos {n} ciclos"

        ciclos = query.order_by(CicloObservacion.id.desc()).limit(n).all()
        session.close()

        if not ciclos:
            console.print(f"[yellow]⚠️  No hay datos para mostrar ({titulo})[/yellow]")
            return

        console.print(Rule(f"[bold cyan]🕐 {titulo.upper()} ({len(ciclos)} registros)[/bold cyan]"))

        tabla = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="dim",
            row_styles=["", "dim"]
        )
        tabla.add_column("#",         style="dim",    width=5,  justify="right")
        tabla.add_column("Timestamp", style="dim",    width=20)
        tabla.add_column("BTC",       style="white",  width=13, justify="right")
        tabla.add_column("RSI",       style="yellow", width=8,  justify="right")
        tabla.add_column("Zona RSI",  style="dim",    width=10)
        tabla.add_column("MACD",      style="dim",    width=10)
        tabla.add_column("Técnico",   style="cyan",   width=9)
        tabla.add_column("Fundament", style="cyan",   width=9)
        tabla.add_column("DECISIÓN",  style="bold",   width=9)
        tabla.add_column("Tiempo",    style="dim",    width=7,  justify="right")

        for c in reversed(ciclos):
            dec = c.decision_final or "N/A"
            color_dec = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(dec, "white")

            dec_t = c.decision_tecnico or "N/A"
            color_t = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(dec_t, "white")

            dec_f = c.decision_fundamental or "N/A"
            color_f = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(dec_f, "white")

            rsi_str = f"{c.rsi:.1f}" if c.rsi else "N/A"
            precio_str = f"${c.precio_btc:,.2f}" if c.precio_btc else "N/A"
            tiempo_str = f"{c.tiempo_ciclo_seg:.0f}s" if c.tiempo_ciclo_seg else "N/A"
            ts_str = ts_ba(c.timestamp)

            # Indicar error con ❌
            if c.error:
                dec = "ERROR"
                color_dec = "red"

            tabla.add_row(
                str(c.ciclo),
                ts_str,
                precio_str,
                rsi_str,
                c.rsi_zona or "N/A",
                c.macd_cruce or "N/A",
                f"[{color_t}]{dec_t}[/{color_t}]",
                f"[{color_f}]{dec_f}[/{color_f}]",
                f"[bold {color_dec}]{dec}[/bold {color_dec}]",
                tiempo_str,
            )

        console.print(tabla)

    except Exception as e:
        console.print(f"[red]❌ Error mostrando ciclos: {e}[/red]")


def mostrar_billetera():
    """Muestra el historial de la billetera hipotética."""
    try:
        from src.trading.base_datos import get_session, Billetera

        session = get_session()
        registros = session.query(Billetera).order_by(Billetera.id.desc()).limit(20).all()
        session.close()

        if not registros:
            console.print("[yellow]⚠️  No hay registros de billetera aún[/yellow]")
            return

        console.print(Rule("[bold cyan]💰 HISTORIAL BILLETERA HIPOTÉTICA[/bold cyan]"))

        tabla = Table(show_header=True, header_style="bold cyan", border_style="dim")
        tabla.add_column("Timestamp",   style="dim",   width=20)
        tabla.add_column("Ciclo",       style="dim",   width=6,  justify="right")
        tabla.add_column("USDT",        style="white", width=12, justify="right")
        tabla.add_column("BTC",         style="white", width=12, justify="right")
        tabla.add_column("Valor Total", style="bold",  width=13, justify="right")
        tabla.add_column("Posición",    style="cyan",  width=10)
        tabla.add_column("Ganancia",    style="bold",  width=12, justify="right")
        tabla.add_column("Evento",      style="yellow",width=10)

        for r in reversed(registros):
            ts_str = ts_ba(r.timestamp)
            usdt_str = f"${r.usdt:,.2f}" if r.usdt is not None else "N/A"
            btc_str  = f"{r.btc:.6f}" if r.btc is not None else "N/A"
            total_str = f"${r.valor_total_usdt:,.2f}" if r.valor_total_usdt else "N/A"
            pos_str  = "[green]EN POSICIÓN[/green]" if r.en_posicion else "[dim]Sin posición[/dim]"

            gan = r.ganancia_total or 0
            color_g = "green" if gan >= 0 else "red"
            signo_g = "+" if gan >= 0 else ""
            gan_str = f"[{color_g}]{signo_g}${gan:,.2f}[/{color_g}]"

            evento_color = {
                "COMPRA": "green", "VENTA": "cyan", "VENTA_SL": "red",
                "VENTA_TP": "green", "INICIO": "blue", "CICLO": "dim"
            }.get(r.evento or "", "white")

            tabla.add_row(
                ts_str,
                str(r.ciclo or ""),
                usdt_str,
                btc_str,
                total_str,
                pos_str,
                gan_str,
                f"[{evento_color}]{r.evento or 'N/A'}[/{evento_color}]",
            )

        console.print(tabla)

    except Exception as e:
        console.print(f"[red]❌ Error mostrando billetera: {e}[/red]")


def mostrar_noticias():
    """Muestra las últimas noticias procesadas en caché."""
    try:
        from src.trading.base_datos import get_session, NoticiaCache

        session = get_session()
        noticias = session.query(NoticiaCache).order_by(NoticiaCache.id.desc()).limit(20).all()
        total = session.query(NoticiaCache).count()
        session.close()

        if not noticias:
            console.print("[yellow]⚠️  No hay noticias en caché aún[/yellow]")
            return

        console.print(Rule(f"[bold cyan]📰 NOTICIAS EN CACHÉ ({total} total)[/bold cyan]"))

        tabla = Table(show_header=True, header_style="bold cyan", border_style="dim")
        tabla.add_column("Fecha",    style="dim",   width=20)
        tabla.add_column("Fuente",   style="cyan",  width=15)
        tabla.add_column("Titular",  style="white", width=55)
        tabla.add_column("Impacto",  style="bold",  width=10)
        tabla.add_column("Intens.",  style="yellow",width=7, justify="right")

        for n in reversed(noticias):
            ts_str = ts_ba(n.fecha_procesada)
            titular = (n.titular[:52] + "...") if n.titular and len(n.titular) > 55 else (n.titular or "N/A")

            impacto = n.impacto_ia or "N/A"
            color_i = {"ALCISTA": "green", "BAJISTA": "red", "NEUTRAL": "yellow"}.get(impacto, "white")
            intens_str = str(n.intensidad_ia) if n.intensidad_ia else "N/A"

            tabla.add_row(
                ts_str,
                n.fuente or "N/A",
                titular,
                f"[{color_i}]{impacto}[/{color_i}]",
                intens_str,
            )

        console.print(tabla)

    except Exception as e:
        console.print(f"[red]❌ Error mostrando noticias: {e}[/red]")


def mostrar_justificaciones_recientes(n: int = 5):
    """Muestra las justificaciones de los últimos N ciclos."""
    try:
        from src.trading.base_datos import get_session, CicloObservacion

        session = get_session()
        ciclos = session.query(CicloObservacion).order_by(CicloObservacion.id.desc()).limit(n).all()
        session.close()

        if not ciclos:
            return

        console.print(Rule("[bold cyan]💬 ÚLTIMAS JUSTIFICACIONES DE LOS AGENTES[/bold cyan]"))

        for c in reversed(ciclos):
            dec = c.decision_final or "N/A"
            color_dec = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(dec, "white")
            ts_str = ts_ba(c.timestamp)

            console.print(f"\n[dim]Ciclo #{c.ciclo} — {ts_str} — BTC: ${c.precio_btc:,.2f} — Decisión: [bold {color_dec}]{dec}[/bold {color_dec}][/dim]")

            if c.justificacion_tecnico:
                console.print(f"  [cyan]🔵 Técnico ({c.decision_tecnico}, {c.confianza_tecnico}%):[/cyan] {c.justificacion_tecnico[:150]}")
            if c.justificacion_fundamental:
                console.print(f"  [yellow]🟡 Fundamental ({c.decision_fundamental}, {c.intensidad_fundamental}%):[/yellow] {c.justificacion_fundamental[:150]}")
            if c.motivo_riesgo:
                console.print(f"  [red]🔴 Riesgo:[/red] {c.motivo_riesgo[:150]}")

    except Exception as e:
        console.print(f"[red]❌ Error mostrando justificaciones: {e}[/red]")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    args = parse_args()

    console.print(Panel.fit(
        "[bold cyan]🔍 CryptoIA — Visor de Datos PostgreSQL[/bold cyan]\n"
        "[dim]Base: CryptoTrade @ 192.168.1.8:5432[/dim]",
        border_style="cyan"
    ))

    # Verificar conexión
    if not conectar():
        sys.exit(1)

    mostrar_todo = args.todo or (not args.noticias and not args.billetera and not args.compras and not args.ventas)

    # Resumen general (siempre)
    mostrar_resumen_general()

    # Ciclos
    if mostrar_todo or args.hoy or args.compras or args.ventas:
        mostrar_ciclos(
            n           = args.ciclos,
            solo_hoy    = args.hoy,
            solo_compras= args.compras,
            solo_ventas = args.ventas,
        )

    # Justificaciones (solo en modo completo)
    if mostrar_todo:
        mostrar_justificaciones_recientes(3)

    # Billetera
    if args.billetera or args.todo:
        mostrar_billetera()

    # Noticias
    if args.noticias or args.todo:
        mostrar_noticias()

    console.print(f"\n[dim]Actualizado: {datetime.now(TZ_BA).strftime('%Y-%m-%d %H:%M:%S')} (Buenos Aires)[/dim]")
    console.print("[dim]Tip: --ciclos 50 | --hoy | --compras | --ventas | --billetera | --noticias | --todo[/dim]")


if __name__ == "__main__":
    main()
