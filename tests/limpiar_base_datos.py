"""
tests/limpiar_base_datos.py — Limpia todas las tablas de la base de datos CryptoIA

ADVERTENCIA: Este script borra TODOS los datos históricos.
La estructura de las tablas se mantiene intacta.

Uso:
    python tests/limpiar_base_datos.py

El script pide confirmación explícita antes de borrar nada.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

console = Console()

# Tablas a limpiar en orden (respetando foreign keys si las hubiera)
TABLAS = [
    "operaciones",
    "billetera",
    "ciclos_observacion",
    "noticias_cache",
]


def contar_registros(session, tabla: str) -> int:
    """Cuenta los registros de una tabla."""
    from sqlalchemy import text
    try:
        result = session.execute(text(f"SELECT COUNT(*) FROM {tabla}"))
        return result.scalar() or 0
    except Exception:
        return -1


def truncar_tabla(session, tabla: str) -> tuple[bool, int]:
    """
    Trunca una tabla (borra todos los registros, resetea secuencias).
    Retorna (ok, registros_borrados).
    """
    from sqlalchemy import text
    try:
        # Contar antes de borrar
        n = contar_registros(session, tabla)
        # TRUNCATE ... RESTART IDENTITY resetea los IDs auto-incrementales
        session.execute(text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
        session.commit()
        return True, n
    except Exception as e:
        session.rollback()
        console.print(f"[red]  Error truncando {tabla}: {e}[/red]")
        return False, 0


def main():
    from config import DB_SERVER, DB_PORT, DB_DATABASE, DB_USER

    console.print(Panel.fit(
        "[bold red]⚠️  LIMPIEZA DE BASE DE DATOS — CryptoIA[/bold red]\n"
        "Este script borra TODOS los datos históricos.\n"
        "La estructura de las tablas se mantiene intacta.",
        border_style="red"
    ))

    # ── Conectar ─────────────────────────────────────────────────────────────
    console.print("\n[yellow]⏳ Conectando a PostgreSQL...[/yellow]")
    from src.trading.base_datos import verificar_conexion, get_session

    ok, msg = verificar_conexion()
    if not ok:
        console.print(f"[bold red]❌ No se pudo conectar a la base de datos:[/bold red]")
        console.print(f"   {msg}")
        console.print(f"\n[yellow]Verificá que PostgreSQL esté corriendo en {DB_SERVER}:{DB_PORT}[/yellow]")
        sys.exit(1)

    console.print(f"[green]✅ Conectado a {DB_DATABASE} en {DB_SERVER}:{DB_PORT}[/green]")

    # ── Mostrar estado actual ─────────────────────────────────────────────────
    console.print(Rule("[bold]Estado actual de las tablas[/bold]"))
    session = get_session()

    tabla_estado = Table("Tabla", "Registros actuales", show_header=True, header_style="bold cyan")
    totales = {}
    for tabla in TABLAS:
        n = contar_registros(session, tabla)
        totales[tabla] = n
        color = "yellow" if n > 0 else "dim"
        tabla_estado.add_row(tabla, f"[{color}]{n:,}[/{color}]" if n >= 0 else "[red]error[/red]")

    console.print(tabla_estado)
    total_general = sum(v for v in totales.values() if v >= 0)
    console.print(f"\n  Total de registros a borrar: [bold yellow]{total_general:,}[/bold yellow]")

    if total_general == 0:
        console.print("\n[green]✅ La base de datos ya está vacía. No hay nada que borrar.[/green]")
        session.close()
        return

    # ── Confirmación ──────────────────────────────────────────────────────────
    console.print(Rule("[bold red]CONFIRMACIÓN REQUERIDA[/bold red]"))
    console.print(f"[bold]Base de datos:[/bold] [cyan]{DB_DATABASE}[/cyan] en [cyan]{DB_SERVER}:{DB_PORT}[/cyan]")
    console.print(f"[bold]Usuario:[/bold]       [cyan]{DB_USER}[/cyan]")
    console.print()
    console.print("[bold red]Esta acción es IRREVERSIBLE. Se borrarán todos los datos históricos.[/bold red]")
    console.print()

    try:
        respuesta = input("¿Estás seguro de que querés borrar todos los datos? [s/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operación cancelada.[/yellow]")
        session.close()
        return

    if respuesta not in ("s", "si", "sí", "yes", "y"):
        console.print("\n[yellow]Operación cancelada. No se borró nada.[/yellow]")
        session.close()
        return

    # Segunda confirmación para mayor seguridad
    console.print()
    try:
        respuesta2 = input("Segunda confirmación — escribí 'BORRAR' para continuar: ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operación cancelada.[/yellow]")
        session.close()
        return

    if respuesta2 != "BORRAR":
        console.print("\n[yellow]Operación cancelada. No se borró nada.[/yellow]")
        session.close()
        return

    # ── Ejecutar limpieza ─────────────────────────────────────────────────────
    console.print(Rule("[bold]Limpiando tablas...[/bold]"))

    resultados = Table("Tabla", "Registros borrados", "Estado", show_header=True, header_style="bold")
    total_borrado = 0
    errores = 0

    for tabla in TABLAS:
        console.print(f"  [yellow]⏳ Limpiando {tabla}...[/yellow]", end="\r")
        ok_t, n_borrado = truncar_tabla(session, tabla)
        if ok_t:
            total_borrado += n_borrado
            resultados.add_row(tabla, f"{n_borrado:,}", "[green]✅ OK[/green]")
            console.print(f"  [green]✅ {tabla}: {n_borrado:,} registros borrados[/green]")
        else:
            errores += 1
            resultados.add_row(tabla, "—", "[red]❌ Error[/red]")

    session.close()

    # ── Resumen final ─────────────────────────────────────────────────────────
    console.print(Rule("[bold]Resumen[/bold]"))
    console.print(resultados)
    console.print()

    if errores == 0:
        console.print(Panel.fit(
            f"[bold green]✅ Limpieza completada exitosamente[/bold green]\n"
            f"Total de registros borrados: [bold]{total_borrado:,}[/bold]\n"
            f"Tablas limpiadas: {len(TABLAS)}\n"
            f"IDs auto-incrementales reseteados a 1\n\n"
            f"[dim]El bot puede iniciarse desde cero ahora.[/dim]",
            border_style="green"
        ))
    else:
        console.print(Panel.fit(
            f"[bold yellow]⚠️  Limpieza completada con {errores} error(es)[/bold yellow]\n"
            f"Registros borrados: {total_borrado:,}\n"
            f"Revisá los mensajes de error arriba.",
            border_style="yellow"
        ))

    # También limpiar el CSV de logs si existe
    csv_path = "logs/motor_real.csv"
    if os.path.exists(csv_path):
        console.print()
        try:
            resp_csv = input(f"¿También querés borrar el archivo CSV de logs ({csv_path})? [s/N]: ").strip().lower()
            if resp_csv in ("s", "si", "sí", "yes", "y"):
                os.remove(csv_path)
                console.print(f"[green]✅ CSV borrado: {csv_path}[/green]")
            else:
                console.print(f"[dim]CSV conservado: {csv_path}[/dim]")
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[dim]CSV conservado: {csv_path}[/dim]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operación cancelada por el usuario.[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error inesperado: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
