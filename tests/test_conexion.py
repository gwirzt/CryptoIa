"""
tests/test_conexion.py — Verifica conectividad de todos los servicios
Uso: python tests/test_conexion.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from config import URL_IA_TAGS, MODELO_IA, DB_CONNECTION_STRING, DB_SERVER, DB_PORT, DB_DATABASE, SERVIDOR_IA, PUERTO_IA

console = Console()
TIMEOUT = 5


def test_ollama() -> tuple:
    try:
        resp = requests.get(URL_IA_TAGS, timeout=TIMEOUT)
        if resp.status_code == 200:
            modelos = [m.get("name", "") for m in resp.json().get("models", [])]
            if any(MODELO_IA in m for m in modelos):
                return True, f"✅ Activo | Modelo '{MODELO_IA}' encontrado"
            else:
                return True, f"⚠️  Activo pero modelo '{MODELO_IA}' NO encontrado. Disponibles: {', '.join(modelos)}"
        return False, f"❌ HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, f"❌ Sin conexión a {URL_IA_TAGS}"
    except requests.exceptions.Timeout:
        return False, f"❌ Timeout ({TIMEOUT}s)"
    except Exception as e:
        return False, f"❌ {e}"


def test_postgresql() -> tuple:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(DB_CONNECTION_STRING, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).fetchone()[0]
        return True, f"✅ Conectado | {version.split(',')[0][:60]}"
    except Exception as e:
        return False, f"❌ {str(e)[:100]}"


def ejecutar_tests():
    console.print(Panel.fit(
        "[bold cyan]🔌 TEST DE CONECTIVIDAD — CryptoIA v2[/bold cyan]",
        border_style="cyan"
    ))

    resultados = []
    ok_ollama, msg_ollama = test_ollama()
    resultados.append(("Ollama IA", f"{SERVIDOR_IA}:{PUERTO_IA}", ok_ollama, msg_ollama))

    ok_db, msg_db = test_postgresql()
    resultados.append(("PostgreSQL", f"{DB_SERVER}:{DB_PORT}/{DB_DATABASE}", ok_db, msg_db))

    tabla = Table(title="Resultados", show_header=True, header_style="bold magenta")
    tabla.add_column("Servicio",  style="cyan",  no_wrap=True, min_width=20)
    tabla.add_column("Host",      style="white", no_wrap=True, min_width=30)
    tabla.add_column("Estado",    no_wrap=True,  min_width=8)
    tabla.add_column("Detalle",   style="white", min_width=40)

    todos_ok = True
    for servicio, host, ok, detalle in resultados:
        estado = "[green]OK[/green]" if ok else "[red]FALLO[/red]"
        if not ok:
            todos_ok = False
        tabla.add_row(servicio, host, estado, detalle)

    console.print("\n", tabla)

    if todos_ok:
        console.print(Panel.fit("[bold green]✅ TODOS LOS SERVICIOS OPERATIVOS[/bold green]", border_style="green"))
        return 0
    else:
        console.print(Panel.fit("[bold red]⚠️  SERVICIOS CON PROBLEMAS[/bold red]", border_style="red"))
        return 1


if __name__ == "__main__":
    sys.exit(ejecutar_tests())
