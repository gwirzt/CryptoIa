"""
src/noticias/feed_manager.py — Gestor de feeds RSS de criptomonedas
Obtiene noticias reales de múltiples fuentes y las prepara para el Agente Fundamental.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import feedparser
import hashlib
from datetime import datetime, timezone, timedelta


# Fuentes RSS de criptomonedas
FUENTES_RSS = [
    {
        "nombre": "CoinTelegraph ES",
        "url": "https://es.cointelegraph.com/rss/tag/bitcoin",
        "idioma": "es"
    },
    {
        "nombre": "CoinTelegraph EN",
        "url": "https://cointelegraph.com/rss/tag/bitcoin",
        "idioma": "en"
    },
    {
        "nombre": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "idioma": "en"
    },
    {
        "nombre": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/feed",
        "idioma": "en"
    },
]

# Máxima antigüedad de noticias a considerar (en horas)
MAX_HORAS_ANTIGUEDAD = 4


def _calcular_hash(titulo: str) -> str:
    """Calcula un hash único para un titular (para evitar duplicados)."""
    return hashlib.md5(titulo.lower().strip().encode()).hexdigest()[:12]


def _parsear_fecha(entry) -> datetime | None:
    """Intenta extraer la fecha de publicación de una entrada RSS."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time
            ts = time.mktime(entry.published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        pass
    return None


def obtener_noticias(max_por_fuente: int = 3, max_horas: int = MAX_HORAS_ANTIGUEDAD) -> list[dict]:
    """
    Obtiene noticias reales de todas las fuentes RSS.
    Devuelve lista de dicts con: titulo, fuente, url, fecha, hace_minutos, hash
    Filtra noticias más antiguas que max_horas.
    """
    ahora = datetime.now(tz=timezone.utc)
    limite_tiempo = ahora - timedelta(hours=max_horas)
    noticias = []
    hashes_vistos = set()

    for fuente in FUENTES_RSS:
        try:
            feed = feedparser.parse(fuente["url"])
            count = 0
            for entry in feed.entries:
                if count >= max_por_fuente:
                    break

                titulo = getattr(entry, "title", "").strip()
                if not titulo:
                    continue

                # Evitar duplicados
                h = _calcular_hash(titulo)
                if h in hashes_vistos:
                    continue
                hashes_vistos.add(h)

                # Verificar antigüedad
                fecha = _parsear_fecha(entry)
                if fecha and fecha < limite_tiempo:
                    continue

                hace_minutos = None
                if fecha:
                    delta = ahora - fecha
                    hace_minutos = int(delta.total_seconds() / 60)

                noticias.append({
                    "titulo":        titulo,
                    "fuente":        fuente["nombre"],
                    "url":           getattr(entry, "link", ""),
                    "fecha":         fecha.strftime("%Y-%m-%d %H:%M UTC") if fecha else "Desconocida",
                    "hace_minutos":  hace_minutos,
                    "hash":          h,
                    "idioma":        fuente["idioma"],
                })
                count += 1

        except Exception as e:
            # Si una fuente falla, continuar con las demás
            pass

    # Ordenar por más reciente primero
    noticias.sort(key=lambda x: x["hace_minutos"] if x["hace_minutos"] is not None else 9999)
    return noticias


def formatear_noticias_para_ia(noticias: list[dict], max_noticias: int = 5) -> str:
    """
    Genera un texto narrativo con las noticias reales,
    listo para enviar al Agente Fundamental (GPU 1).
    """
    if not noticias:
        return "No se encontraron noticias recientes de Bitcoin en las últimas horas."

    noticias_usar = noticias[:max_noticias]
    lineas = ["=== NOTICIAS RECIENTES DE BITCOIN ===\n"]

    for i, n in enumerate(noticias_usar, 1):
        if n["hace_minutos"] is not None:
            if n["hace_minutos"] < 60:
                tiempo_str = f"hace {n['hace_minutos']} minutos"
            else:
                horas = n["hace_minutos"] // 60
                mins = n["hace_minutos"] % 60
                tiempo_str = f"hace {horas}h {mins}min" if mins > 0 else f"hace {horas} horas"
        else:
            tiempo_str = "hora desconocida"

        lineas.append(f"NOTICIA {i} ({tiempo_str}):")
        lineas.append(f"Titular: {n['titulo']}")
        lineas.append(f"Fuente: {n['fuente']}")
        lineas.append("")

    return "\n".join(lineas)


def obtener_resumen_noticias(max_noticias: int = 5) -> tuple[list[dict], str]:
    """
    Función principal: obtiene noticias y genera el texto para la IA.
    Devuelve (lista_noticias, texto_para_ia).
    """
    noticias = obtener_noticias(max_por_fuente=3, max_horas=MAX_HORAS_ANTIGUEDAD)
    texto = formatear_noticias_para_ia(noticias, max_noticias)
    return noticias, texto


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()
    console.print(Panel.fit("[bold yellow]📰 Test del módulo de noticias real[/bold yellow]"))
    console.print("[yellow]Obteniendo noticias de RSS...[/yellow]")

    noticias, texto = obtener_resumen_noticias()

    if noticias:
        tabla = Table(title=f"Noticias recientes ({len(noticias)} encontradas)", show_header=True)
        tabla.add_column("#", style="cyan", width=3)
        tabla.add_column("Titular", style="white")
        tabla.add_column("Fuente", style="yellow", width=18)
        tabla.add_column("Hace", style="dim", width=12)
        for i, n in enumerate(noticias, 1):
            hace = f"{n['hace_minutos']}min" if n['hace_minutos'] else "?"
            tabla.add_row(str(i), n["titulo"][:70], n["fuente"], hace)
        console.print(tabla)
    else:
        console.print("[red]No se encontraron noticias recientes.[/red]")

    console.print(Panel(texto, title="Texto para IA", border_style="yellow"))
