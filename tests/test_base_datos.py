"""
tests/test_base_datos.py — Test de conexión y funcionamiento de PostgreSQL
Verifica que la base de datos está accesible, crea las tablas y prueba
escritura/lectura básica.

Ejecutar con:
    venv\Scripts\python.exe tests\test_base_datos.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

console = Console()


def ejecutar_test():
    console.print(Panel.fit(
        "[bold cyan]🗄️  TEST — BASE DE DATOS PostgreSQL[/bold cyan]\n"
        "Verificando conexión, tablas y operaciones básicas",
        border_style="cyan"
    ))

    from config import DB_SERVER, DB_PORT, DB_DATABASE, DB_USER, DB_CONNECTION_STRING
    console.print(f"[dim]Conectando a: postgresql://{DB_USER}:***@{DB_SERVER}:{DB_PORT}/{DB_DATABASE}[/dim]\n")

    errores = 0

    # =========================================================================
    # PASO 1: Verificar conexión
    # =========================================================================
    console.print(Rule("[bold cyan]PASO 1/5 — Verificar conexión[/bold cyan]"))
    try:
        from src.trading.base_datos import verificar_conexion
        ok, msg = verificar_conexion()
        if ok:
            console.print(f"[green]✅ Conectado a PostgreSQL[/green]")
            console.print(f"[dim]   {msg[:100]}[/dim]")
        else:
            console.print(f"[red]❌ Error de conexión: {msg}[/red]")
            console.print("[yellow]💡 Verificá que PostgreSQL esté corriendo en 192.168.1.8:5432[/yellow]")
            console.print("[yellow]💡 Verificá usuario/password en el archivo .env[/yellow]")
            return 1
    except Exception as e:
        console.print(f"[red]❌ Excepción: {e}[/red]")
        return 1

    # =========================================================================
    # PASO 2: Crear tablas
    # =========================================================================
    console.print(Rule("[bold cyan]PASO 2/5 — Crear tablas[/bold cyan]"))
    try:
        from src.trading.base_datos import crear_tablas
        crear_tablas()
        console.print("[green]✅ Tablas creadas/verificadas:[/green]")
        console.print("   [dim]• ciclos_observacion[/dim]")
        console.print("   [dim]• noticias_cache[/dim]")
        console.print("   [dim]• billetera[/dim]")
        console.print("   [dim]• operaciones[/dim]")
    except Exception as e:
        console.print(f"[red]❌ Error creando tablas: {e}[/red]")
        errores += 1

    # =========================================================================
    # PASO 3: Escribir un ciclo de prueba
    # =========================================================================
    console.print(Rule("[bold cyan]PASO 3/5 — Escribir ciclo de prueba[/bold cyan]"))
    try:
        from src.trading.base_datos import guardar_ciclo
        datos_prueba = {
            "ciclo":                  0,
            "precio_btc":             62736.13,
            "variacion_pct":          0.003,
            "rsi":                    45.8,
            "rsi_zona":               "NEUTRAL",
            "macd_hist":              -44.27,
            "macd_cruce":             "NEGATIVO",
            "bb_posicion":            "INFERIOR",
            "tendencia_ema":          "BAJISTA",
            "volumen_relativo":       89.4,
            "tendencia_5v":           "BAJISTA",
            "noticias_count":         3,
            "decision_tecnico":       "ESPERAR",
            "confianza_tecnico":      75,
            "justificacion_tecnico":  "Test de escritura en PostgreSQL",
            "decision_fundamental":   "ALCISTA",
            "intensidad_fundamental": 70,
            "justificacion_fundamental": "Noticias institucionales positivas",
            "decision_final":         "ESPERAR",
            "stop_loss_pct":          2.5,
            "take_profit_pct":        5.0,
            "motivo_riesgo":          "Señales contradictorias — test",
            "tiempo_ciclo_seg":       49.9,
            "error":                  None,
        }
        ok = guardar_ciclo(datos_prueba)
        if ok:
            console.print("[green]✅ Ciclo de prueba guardado en ciclos_observacion[/green]")
        else:
            console.print("[red]❌ Error guardando ciclo[/red]")
            errores += 1
    except Exception as e:
        console.print(f"[red]❌ Excepción: {e}[/red]")
        errores += 1

    # =========================================================================
    # PASO 4: Verificar caché de noticias
    # =========================================================================
    console.print(Rule("[bold cyan]PASO 4/5 — Caché de noticias[/bold cyan]"))
    try:
        from src.trading.base_datos import guardar_noticia_cache, noticia_ya_procesada

        hash_test = "test_hash_001"
        titular_test = "Bitcoin supera los $63,000 en nueva ola alcista institucional"

        # Guardar
        ok = guardar_noticia_cache(
            hash_titular = hash_test,
            titular      = titular_test,
            fuente       = "Test",
            url          = "https://test.com",
            impacto      = "ALCISTA",
            intensidad   = 70
        )
        if ok:
            console.print("[green]✅ Noticia guardada en caché[/green]")
        else:
            console.print("[yellow]⚠️  No se pudo guardar (puede que ya exista)[/yellow]")

        # Verificar que existe
        existe = noticia_ya_procesada(hash_test)
        if existe:
            console.print("[green]✅ Verificación de caché: noticia encontrada correctamente[/green]")
        else:
            console.print("[red]❌ La noticia no se encontró en el caché[/red]")
            errores += 1

        # Verificar que una noticia nueva NO existe
        no_existe = noticia_ya_procesada("hash_que_no_existe_xyz")
        if not no_existe:
            console.print("[green]✅ Verificación negativa: hash inexistente devuelve False[/green]")
        else:
            console.print("[red]❌ Error: hash inexistente devolvió True[/red]")
            errores += 1

    except Exception as e:
        console.print(f"[red]❌ Excepción en caché: {e}[/red]")
        errores += 1

    # =========================================================================
    # PASO 5: Leer datos y mostrar estadísticas
    # =========================================================================
    console.print(Rule("[bold cyan]PASO 5/5 — Leer datos y estadísticas[/bold cyan]"))
    try:
        from src.trading.base_datos import obtener_ultimos_ciclos, obtener_estadisticas

        ciclos = obtener_ultimos_ciclos(5)
        if ciclos:
            tabla = Table(title="Últimos ciclos en PostgreSQL", show_header=True, header_style="bold cyan")
            tabla.add_column("Ciclo", style="cyan",  width=6)
            tabla.add_column("Timestamp", style="dim", width=22)
            tabla.add_column("BTC",    style="white", width=12)
            tabla.add_column("RSI",    style="yellow", width=8)
            tabla.add_column("Decisión", style="green", width=10)
            tabla.add_column("Tiempo", style="dim", width=8)
            for c in ciclos:
                precio_str = f"${c['precio_btc']:,.2f}" if c['precio_btc'] else "N/A"
                rsi_str    = str(c['rsi']) if c['rsi'] else "N/A"
                dec_str    = c['decision_final'] or "N/A"
                t_str      = f"{c['tiempo_seg']}s" if c['tiempo_seg'] else "N/A"
                color = {"COMPRA": "green", "VENTA": "red", "ESPERAR": "yellow"}.get(dec_str, "white")
                tabla.add_row(
                    str(c['ciclo']),
                    str(c['timestamp'])[:19],
                    precio_str,
                    rsi_str,
                    f"[{color}]{dec_str}[/{color}]",
                    t_str
                )
            console.print(tabla)
        else:
            console.print("[yellow]⚠️  No hay ciclos en la base de datos aún[/yellow]")

        stats = obtener_estadisticas()
        if stats:
            console.print(f"\n[dim]📊 Estadísticas: {stats['total_ciclos']} ciclos | "
                          f"COMPRA: {stats['pct_compra']}% | "
                          f"VENTA: {stats['pct_venta']}% | "
                          f"ESPERAR: {stats['pct_esperar']}%[/dim]")

    except Exception as e:
        console.print(f"[red]❌ Error leyendo datos: {e}[/red]")
        errores += 1

    # =========================================================================
    # RESULTADO FINAL
    # =========================================================================
    console.print("")
    if errores == 0:
        console.print(Panel.fit(
            "[bold green]✅ TEST PASADO — PostgreSQL funcionando correctamente[/bold green]\n"
            f"Servidor: {DB_SERVER}:{DB_PORT} | Base: {DB_DATABASE}\n"
            "Tablas: ciclos_observacion, noticias_cache, billetera, operaciones",
            border_style="green"
        ))
        return 0
    else:
        console.print(Panel.fit(
            f"[bold red]❌ TEST CON {errores} ERROR(ES)[/bold red]\n"
            "Revisá la conexión y los logs de PostgreSQL",
            border_style="red"
        ))
        return 1


if __name__ == "__main__":
    sys.exit(ejecutar_test())
