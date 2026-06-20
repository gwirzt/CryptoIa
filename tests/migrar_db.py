"""
tests/migrar_db.py — Migración de base de datos CryptoIA

Agrega columnas nuevas a tablas existentes sin perder datos.
Seguro de ejecutar múltiples veces (usa IF NOT EXISTS).

Uso:
    python tests/migrar_db.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import text

console = Console()


def main():
    from src.trading.base_datos import verificar_conexion, get_session, crear_tablas

    console.print(Panel.fit(
        "[bold cyan]🗄️  Migración de Base de Datos — CryptoIA[/bold cyan]\n"
        "Agrega columnas nuevas sin borrar datos existentes.",
        border_style="cyan"
    ))

    # Verificar conexión
    console.print("\n[yellow]⏳ Conectando a PostgreSQL...[/yellow]")
    ok, msg = verificar_conexion()
    if not ok:
        console.print(f"[bold red]❌ No se pudo conectar: {msg}[/bold red]")
        sys.exit(1)
    console.print(f"[green]✅ Conectado OK[/green]")

    # Crear tablas nuevas si no existen (seguro)
    console.print("[yellow]⏳ Verificando/creando tablas...[/yellow]")
    crear_tablas()
    console.print("[green]✅ Tablas verificadas[/green]")

    session = get_session()

    # ── Mostrar columnas actuales ──────────────────────────────────────────────
    console.print("\n[bold]Columnas actuales en tabla 'operaciones':[/bold]")
    result = session.execute(text(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = 'operaciones' "
        "ORDER BY ordinal_position"
    ))
    cols_actuales = {row[0]: row[1] for row in result.fetchall()}

    tabla_cols = Table("Columna", "Tipo", "Estado", show_header=True, header_style="bold cyan")
    for col, tipo in cols_actuales.items():
        tabla_cols.add_row(col, tipo, "[green]✅ existe[/green]")
    console.print(tabla_cols)

    # ── Migraciones a aplicar ──────────────────────────────────────────────────
    migraciones = [
        {
            "tabla":   "operaciones",
            "columna": "comision_usdt",
            "tipo":    "FLOAT",
            "desc":    "Comisión real pagada a Binance (≈0.1%)",
        },
        {
            "tabla":   "operaciones",
            "columna": "ganancia_pct",
            "tipo":    "FLOAT",
            "desc":    "P&L porcentual de la operación",
        },
        {
            "tabla":   "operaciones",
            "columna": "pnl_al_vender",
            "tipo":    "FLOAT",
            "desc":    "P&L % en el momento exacto de la venta",
        },
    ]

    console.print("\n[bold]Aplicando migraciones:[/bold]")
    aplicadas = 0
    omitidas  = 0

    for m in migraciones:
        col = m["columna"]
        if col in cols_actuales:
            console.print(f"  [dim]⏭️  {m['tabla']}.{col} — ya existe, omitiendo[/dim]")
            omitidas += 1
            continue

        try:
            session.execute(text(
                f"ALTER TABLE {m['tabla']} ADD COLUMN IF NOT EXISTS {col} {m['tipo']}"
            ))
            session.commit()
            console.print(
                f"  [green]✅ {m['tabla']}.{col} ({m['tipo']}) — agregada[/green]\n"
                f"     [dim]{m['desc']}[/dim]"
            )
            aplicadas += 1
        except Exception as e:
            session.rollback()
            console.print(f"  [red]❌ Error en {m['tabla']}.{col}: {e}[/red]")

    session.close()

    # ── Resumen ────────────────────────────────────────────────────────────────
    console.print(Panel.fit(
        f"[bold green]✅ Migración completada[/bold green]\n"
        f"Columnas agregadas: [bold]{aplicadas}[/bold]\n"
        f"Columnas omitidas (ya existían): [dim]{omitidas}[/dim]",
        border_style="green"
    ))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelado.[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
