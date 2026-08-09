"""
tests/limpiar_base_datos.py — Limpia todas las tablas de la base de datos CryptoIA v2

ADVERTENCIA: Este script borra TODOS los datos históricos.
La estructura de las tablas se mantiene intacta.

Tablas que limpia:
  - posicion_v2      (posición abierta actual)
  - operaciones_v2   (historial de compras/ventas)
  - ciclos_log       (log de cada ciclo del bot)

Uso:
    python tests/limpiar_base_datos.py

El script pide confirmación explícita antes de borrar nada.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from config import DB_CONNECTION_STRING, DB_SERVER, DB_PORT, DB_DATABASE, DB_USER

# Tablas a limpiar en orden (posicion primero para no dejar huérfanos)
TABLAS = [
    "posicion_v2",
    "operaciones_v2",
    "ciclos_log",
]


def get_engine():
    return create_engine(DB_CONNECTION_STRING, pool_pre_ping=True)


def contar_registros(engine, tabla: str) -> int:
    """Cuenta los registros de una tabla."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}"))
            return result.scalar() or 0
    except Exception:
        return -1


def truncar_tabla(engine, tabla: str) -> tuple:
    """
    Trunca una tabla (borra todos los registros, resetea secuencias).
    Retorna (ok, registros_borrados).
    """
    try:
        n = contar_registros(engine, tabla)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
        return True, n
    except Exception as e:
        print(f"  ❌ Error truncando {tabla}: {e}")
        return False, 0


def separador(char="─", ancho=60):
    print(char * ancho)


def main():
    print()
    separador("═")
    print("  ⚠️  LIMPIEZA DE BASE DE DATOS — CryptoIA v2")
    print("  Este script borra TODOS los datos históricos.")
    print("  La estructura de las tablas se mantiene intacta.")
    separador("═")

    # ── Conectar ──────────────────────────────────────────────────────────────
    print(f"\n⏳ Conectando a PostgreSQL ({DB_SERVER}:{DB_PORT}/{DB_DATABASE})...")
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✅ Conectado a {DB_DATABASE} en {DB_SERVER}:{DB_PORT} (usuario: {DB_USER})")
    except Exception as e:
        print(f"\n❌ No se pudo conectar a la base de datos:")
        print(f"   {e}")
        print(f"\n⚠️  Verificá que PostgreSQL esté corriendo en {DB_SERVER}:{DB_PORT}")
        sys.exit(1)

    # ── Mostrar estado actual ─────────────────────────────────────────────────
    print()
    separador()
    print("  Estado actual de las tablas")
    separador()

    totales = {}
    for tabla in TABLAS:
        n = contar_registros(engine, tabla)
        totales[tabla] = n
        if n < 0:
            print(f"  {tabla:<25} ERROR (tabla no encontrada)")
        else:
            estado = f"{n:,} registros" if n > 0 else "vacía"
            print(f"  {tabla:<25} {estado}")

    total_general = sum(v for v in totales.values() if v >= 0)
    print()
    print(f"  Total de registros a borrar: {total_general:,}")
    separador()

    if total_general == 0:
        print("\n✅ La base de datos ya está vacía. No hay nada que borrar.")
        return

    # ── Confirmación ──────────────────────────────────────────────────────────
    print()
    separador("─")
    print("  CONFIRMACIÓN REQUERIDA")
    separador("─")
    print(f"  Base de datos : {DB_DATABASE} en {DB_SERVER}:{DB_PORT}")
    print(f"  Usuario       : {DB_USER}")
    print(f"  Registros     : {total_general:,} en total")
    print()
    print("  ⚠️  Esta acción es IRREVERSIBLE.")
    print("      Se borrarán TODOS los datos: posiciones, operaciones y logs.")
    print()

    try:
        respuesta = input("¿Estás seguro de que querés borrar todos los datos? [s/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n\nOperación cancelada.")
        return

    if respuesta not in ("s", "si", "sí", "yes", "y"):
        print("\nOperación cancelada. No se borró nada.")
        return

    print()
    try:
        respuesta2 = input("Segunda confirmación — escribí 'BORRAR' para continuar: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nOperación cancelada.")
        return

    if respuesta2 != "BORRAR":
        print("\nOperación cancelada. No se borró nada.")
        return

    # ── Ejecutar limpieza ─────────────────────────────────────────────────────
    print()
    separador()
    print("  Limpiando tablas...")
    separador()

    total_borrado = 0
    errores = 0

    for tabla in TABLAS:
        print(f"  ⏳ Limpiando {tabla}...", end=" ", flush=True)
        ok_t, n_borrado = truncar_tabla(engine, tabla)
        if ok_t:
            total_borrado += n_borrado
            print(f"✅ {n_borrado:,} registros borrados")
        else:
            errores += 1
            print(f"❌ Error")

    # ── Resumen final ─────────────────────────────────────────────────────────
    print()
    separador("═")
    if errores == 0:
        print("  ✅ LIMPIEZA COMPLETADA EXITOSAMENTE")
        print(f"  Total de registros borrados : {total_borrado:,}")
        print(f"  Tablas limpiadas            : {len(TABLAS)}")
        print(f"  IDs auto-incrementales      : reseteados a 1")
        print()
        print("  El bot puede iniciarse desde cero ahora.")
    else:
        print(f"  ⚠️  Limpieza completada con {errores} error(es)")
        print(f"  Registros borrados: {total_borrado:,}")
        print(f"  Revisá los mensajes de error arriba.")
    separador("═")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperación cancelada por el usuario.")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
