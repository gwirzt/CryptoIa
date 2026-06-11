"""
tests/test_conexion.py — Verificación de conectividad de todos los servicios
Ejecutar con: python tests/test_conexion.py
"""
import sys
import os

# Aseguramos que Python encuentre el config.py en la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pyodbc
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from config import (
    URL_GPU0_HEALTH, URL_GPU1_HEALTH, URL_GPU2_HEALTH,
    MODELO_GPU0, MODELO_GPU1, MODELO_GPU2,
    DB_DRIVER, DB_SERVER, DB_DATABASE, DB_USER, DB_PASSWORD,
    SERVIDOR_IA, PUERTO_GPU0, PUERTO_GPU1, PUERTO_GPU2
)

console = Console()
TIMEOUT = 5  # segundos de espera por cada test


def test_ollama(nombre: str, url_health: str, modelo: str) -> tuple[bool, str]:
    """Verifica que un servidor Ollama esté activo y tenga el modelo cargado."""
    try:
        resp = requests.get(url_health, timeout=TIMEOUT)
        if resp.status_code == 200:
            datos = resp.json()
            modelos_disponibles = [m.get("name", "") for m in datos.get("models", [])]
            if any(modelo in m for m in modelos_disponibles):
                return True, f"✅ Activo | Modelo '{modelo}' encontrado"
            else:
                modelos_str = ", ".join(modelos_disponibles) if modelos_disponibles else "ninguno"
                return True, f"⚠️  Activo pero modelo '{modelo}' NO encontrado. Disponibles: {modelos_str}"
        else:
            return False, f"❌ HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, f"❌ Sin conexión a {url_health}"
    except requests.exceptions.Timeout:
        return False, f"❌ Timeout ({TIMEOUT}s) — servidor no responde"
    except Exception as e:
        return False, f"❌ Error inesperado: {e}"


def test_sqlserver() -> tuple[bool, str]:
    """Verifica la conexión a SQL Server."""
    try:
        conn_str = (
            f"DRIVER={{{DB_DRIVER}}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_DATABASE};"
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD};"
            f"TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(conn_str, timeout=TIMEOUT)
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0].split("\n")[0].strip()
        conn.close()
        return True, f"✅ Conectado | {version[:60]}..."
    except pyodbc.Error as e:
        return False, f"❌ Error ODBC: {str(e)[:80]}"
    except Exception as e:
        return False, f"❌ Error inesperado: {e}"


def ejecutar_tests():
    console.print(Panel.fit(
        "[bold cyan]🔌 TEST DE CONECTIVIDAD — CryptoIA[/bold cyan]\n"
        "Verificando todos los servicios del sistema...",
        border_style="cyan"
    ))

    resultados = []

    # --- Tests de Ollama ---
    console.print("\n[bold yellow]🤖 Verificando servidores Ollama...[/bold yellow]")
    
    ok0, msg0 = test_ollama(f"GPU 0 (:{PUERTO_GPU0})", URL_GPU0_HEALTH, MODELO_GPU0)
    resultados.append(("GPU 0 — Analista Técnico",    f"{SERVIDOR_IA}:{PUERTO_GPU0}", ok0, msg0))

    ok1, msg1 = test_ollama(f"GPU 1 (:{PUERTO_GPU1})", URL_GPU1_HEALTH, MODELO_GPU1)
    resultados.append(("GPU 1 — Analista Fundamental", f"{SERVIDOR_IA}:{PUERTO_GPU1}", ok1, msg1))

    ok2, msg2 = test_ollama(f"GPU 2 (:{PUERTO_GPU2})", URL_GPU2_HEALTH, MODELO_GPU2)
    resultados.append(("GPU 2 — Gestor de Riesgos",   f"{SERVIDOR_IA}:{PUERTO_GPU2}", ok2, msg2))

    # --- Test de SQL Server ---
    console.print("\n[bold yellow]🗄️  Verificando SQL Server...[/bold yellow]")
    ok_db, msg_db = test_sqlserver()
    resultados.append(("SQL Server",                   f"{DB_SERVER}/{DB_DATABASE}",   ok_db, msg_db))

    # --- Tabla de resultados ---
    tabla = Table(title="📋 Resultados del Test de Conectividad", show_header=True, header_style="bold magenta")
    tabla.add_column("Servicio",   style="cyan",  no_wrap=True, min_width=30)
    tabla.add_column("Host",       style="white", no_wrap=True, min_width=25)
    tabla.add_column("Estado",     style="green", no_wrap=True, min_width=8)
    tabla.add_column("Detalle",    style="white", min_width=40)

    todos_ok = True
    for servicio, host, ok, detalle in resultados:
        estado = "[green]OK[/green]" if ok else "[red]FALLO[/red]"
        if not ok:
            todos_ok = False
        tabla.add_row(servicio, host, estado, detalle)

    console.print("\n", tabla)

    # --- Resumen final ---
    if todos_ok:
        console.print(Panel.fit(
            "[bold green]✅ TODOS LOS SERVICIOS ESTÁN OPERATIVOS[/bold green]\n"
            "El sistema está listo para iniciar el bot.",
            border_style="green"
        ))
        return 0
    else:
        fallos = sum(1 for _, _, ok, _ in resultados if not ok)
        console.print(Panel.fit(
            f"[bold red]⚠️  {fallos} SERVICIO(S) CON PROBLEMAS[/bold red]\n"
            "Revisá la conectividad de red y que los servicios estén corriendo.",
            border_style="red"
        ))
        return 1


if __name__ == "__main__":
    sys.exit(ejecutar_tests())
