"""
src/trading/base_datos.py — Capa de persistencia con PostgreSQL
Modelos SQLAlchemy para todas las tablas del sistema CryptoIA.

Tablas:
  - ciclos_observacion  : Registro de cada ciclo del bot (precio, indicadores, decisiones)
  - noticias_cache      : Titulares ya procesados (evita repetir análisis)
  - billetera           : Estado de la billetera con historial
  - operaciones         : Compras/ventas hipotéticas con P&L
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Boolean,
    DateTime, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from config import DB_CONNECTION_STRING

Base = declarative_base()

# ==============================================================================
# MODELOS (TABLAS)
# ==============================================================================

class CicloObservacion(Base):
    """
    Registro de cada ciclo del bot de observación.
    Una fila por cada vez que el comité analiza el mercado.
    """
    __tablename__ = "ciclos_observacion"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    timestamp       = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    ciclo           = Column(Integer, nullable=False)

    # Datos de mercado
    simbolo         = Column(String(20),  default="BTC/USDT")
    temporalidad    = Column(String(10),  default="15m")
    precio_btc      = Column(Float,       nullable=True)
    variacion_pct   = Column(Float,       nullable=True)

    # Indicadores técnicos
    rsi             = Column(Float,       nullable=True)
    rsi_zona        = Column(String(20),  nullable=True)
    macd_hist       = Column(Float,       nullable=True)
    macd_cruce      = Column(String(20),  nullable=True)
    bb_posicion     = Column(String(20),  nullable=True)
    tendencia_ema   = Column(String(20),  nullable=True)
    volumen_relativo= Column(Float,       nullable=True)
    tendencia_5v    = Column(String(20),  nullable=True)

    # Noticias
    noticias_count  = Column(Integer,     default=0)

    # Decisiones de los agentes
    decision_tecnico      = Column(String(20),  nullable=True)
    confianza_tecnico     = Column(Integer,      nullable=True)
    justificacion_tecnico = Column(Text,         nullable=True)

    decision_fundamental      = Column(String(20),  nullable=True)
    intensidad_fundamental    = Column(Integer,      nullable=True)
    justificacion_fundamental = Column(Text,         nullable=True)

    decision_final    = Column(String(20),  nullable=True)
    stop_loss_pct     = Column(Float,       nullable=True)
    take_profit_pct   = Column(Float,       nullable=True)
    motivo_riesgo     = Column(Text,        nullable=True)

    # Métricas del ciclo
    tiempo_ciclo_seg  = Column(Float,       nullable=True)
    error             = Column(Text,        nullable=True)

    def __repr__(self):
        return (f"<CicloObservacion #{self.ciclo} | {self.timestamp} | "
                f"BTC=${self.precio_btc} | {self.decision_final}>")


class NoticiaCache(Base):
    """
    Caché de noticias ya procesadas.
    Evita que el Agente Fundamental analice el mismo titular dos veces.
    """
    __tablename__ = "noticias_cache"
    __table_args__ = (
        UniqueConstraint("hash_titular", name="uq_hash_titular"),
    )

    id              = Column(Integer, primary_key=True, autoincrement=True)
    hash_titular    = Column(String(32),  nullable=False, unique=True)
    titular         = Column(Text,        nullable=False)
    fuente          = Column(String(100), nullable=True)
    url             = Column(Text,        nullable=True)
    fecha_noticia   = Column(DateTime(timezone=True), nullable=True)
    fecha_procesada = Column(DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    impacto_ia      = Column(String(20),  nullable=True)   # ALCISTA/BAJISTA/NEUTRAL
    intensidad_ia   = Column(Integer,     nullable=True)

    def __repr__(self):
        return f"<NoticiaCache {self.hash_titular} | {self.fuente} | {self.impacto_ia}>"


class Billetera(Base):
    """
    Estado de la billetera hipotética con historial completo.
    Cada cambio de estado genera una nueva fila.
    """
    __tablename__ = "billetera"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    timestamp       = Column(DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    ciclo           = Column(Integer,     nullable=True)

    usdt            = Column(Float,       nullable=False, default=0.0)
    btc             = Column(Float,       nullable=False, default=0.0)
    precio_btc_ref  = Column(Float,       nullable=True)   # precio al momento del registro
    valor_total_usdt= Column(Float,       nullable=True)   # usdt + btc * precio_btc_ref
    en_posicion     = Column(Boolean,     default=False)
    precio_compra   = Column(Float,       nullable=True)
    stop_loss_precio= Column(Float,       nullable=True)
    take_profit_precio = Column(Float,    nullable=True)
    ganancia_total  = Column(Float,       default=0.0)
    operaciones_count = Column(Integer,   default=0)
    evento          = Column(String(50),  nullable=True)   # INICIO, COMPRA, VENTA, SL, TP, CICLO

    def __repr__(self):
        return (f"<Billetera #{self.id} | {self.timestamp} | "
                f"USDT={self.usdt:.2f} | BTC={self.btc:.6f} | {self.evento}>")


class Operacion(Base):
    """
    Registro de cada operación hipotética ejecutada.
    """
    __tablename__ = "operaciones"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    timestamp       = Column(DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    ciclo           = Column(Integer,     nullable=True)
    tipo            = Column(String(20),  nullable=False)  # COMPRA, VENTA, VENTA_SL, VENTA_TP
    precio          = Column(Float,       nullable=False)
    btc_cantidad    = Column(Float,       nullable=True)
    usdt_cantidad   = Column(Float,       nullable=True)
    ganancia_usdt   = Column(Float,       nullable=True)
    ganancia_pct    = Column(Float,       nullable=True)
    motivo          = Column(Text,        nullable=True)
    decision_tecnico    = Column(String(20), nullable=True)
    decision_fundamental= Column(String(20), nullable=True)
    rsi_al_operar   = Column(Float,       nullable=True)

    def __repr__(self):
        return (f"<Operacion #{self.id} | {self.tipo} | "
                f"${self.precio:,.2f} | P&L={self.ganancia_usdt}>")


# ==============================================================================
# MOTOR Y SESIÓN
# ==============================================================================

_engine = None
_SessionLocal = None


def get_engine():
    """Crea y devuelve el motor de SQLAlchemy (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DB_CONNECTION_STRING,
            pool_pre_ping=True,       # verifica conexión antes de usarla
            pool_size=5,
            max_overflow=10,
            echo=False                # True para ver SQL en consola (debug)
        )
    return _engine


def get_session() -> Session:
    """Devuelve una nueva sesión de base de datos."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal()


def crear_tablas():
    """
    Crea todas las tablas en PostgreSQL si no existen.
    Seguro de ejecutar múltiples veces (usa CREATE TABLE IF NOT EXISTS).
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    return True


def verificar_conexion() -> tuple[bool, str]:
    """
    Verifica que la conexión a PostgreSQL funciona.
    Devuelve (True, version_string) o (False, mensaje_error).
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            return True, version
    except SQLAlchemyError as e:
        return False, str(e)


# ==============================================================================
# FUNCIONES DE ESCRITURA
# ==============================================================================

def guardar_ciclo(datos: dict) -> bool:
    """
    Guarda un ciclo de observación en la base de datos.
    Acepta el mismo diccionario que se guarda en el CSV.
    Devuelve True si se guardó correctamente.
    """
    session = get_session()
    try:
        ciclo = CicloObservacion(
            timestamp       = datetime.now(timezone.utc),
            ciclo           = datos.get("ciclo", 0),
            precio_btc      = datos.get("precio_btc"),
            variacion_pct   = datos.get("variacion_pct"),
            rsi             = datos.get("rsi"),
            rsi_zona        = datos.get("rsi_zona"),
            macd_hist       = datos.get("macd_hist"),
            macd_cruce      = datos.get("macd_cruce"),
            bb_posicion     = datos.get("bb_posicion"),
            tendencia_ema   = datos.get("tendencia_ema"),
            volumen_relativo= datos.get("volumen_relativo"),
            tendencia_5v    = datos.get("tendencia_5v"),
            noticias_count  = datos.get("noticias_count", 0),
            decision_tecnico      = datos.get("decision_tecnico"),
            confianza_tecnico     = datos.get("confianza_tecnico"),
            justificacion_tecnico = datos.get("justificacion_tecnico"),
            decision_fundamental      = datos.get("decision_fundamental"),
            intensidad_fundamental    = datos.get("intensidad_fundamental"),
            justificacion_fundamental = datos.get("justificacion_fundamental"),
            decision_final    = datos.get("decision_final"),
            stop_loss_pct     = datos.get("stop_loss_pct"),
            take_profit_pct   = datos.get("take_profit_pct"),
            motivo_riesgo     = datos.get("motivo_riesgo"),
            tiempo_ciclo_seg  = datos.get("tiempo_ciclo_seg"),
            error             = datos.get("error"),
        )
        session.add(ciclo)
        session.commit()
        return True
    except SQLAlchemyError as e:
        session.rollback()
        print(f"[DB ERROR] guardar_ciclo: {e}")
        return False
    finally:
        session.close()


def noticia_ya_procesada(hash_titular: str) -> bool:
    """Verifica si una noticia ya fue procesada (está en caché)."""
    session = get_session()
    try:
        existe = session.query(NoticiaCache).filter_by(hash_titular=hash_titular).first()
        return existe is not None
    except SQLAlchemyError:
        return False
    finally:
        session.close()


def guardar_noticia_cache(hash_titular: str, titular: str, fuente: str = "",
                          url: str = "", impacto: str = None, intensidad: int = None) -> bool:
    """Guarda una noticia en el caché para no procesarla de nuevo."""
    session = get_session()
    try:
        noticia = NoticiaCache(
            hash_titular    = hash_titular,
            titular         = titular,
            fuente          = fuente,
            url             = url,
            fecha_procesada = datetime.now(timezone.utc),
            impacto_ia      = impacto,
            intensidad_ia   = intensidad,
        )
        session.add(noticia)
        session.commit()
        return True
    except SQLAlchemyError as e:
        session.rollback()
        # Si ya existe (unique constraint), no es un error real
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return True
        print(f"[DB ERROR] guardar_noticia_cache: {e}")
        return False
    finally:
        session.close()


def guardar_estado_billetera(datos_billetera: dict, ciclo: int, precio_btc: float,
                              evento: str = "CICLO") -> bool:
    """Guarda el estado actual de la billetera hipotética."""
    session = get_session()
    try:
        b = datos_billetera
        valor_total = b.get("usdt", 0) + (b.get("btc", 0) * precio_btc)
        sl_precio = None
        tp_precio = None
        if b.get("en_posicion") and b.get("precio_compra", 0) > 0:
            sl_precio = b["precio_compra"] * (1 - b.get("sl_pct", 2.5) / 100)
            tp_precio = b["precio_compra"] * (1 + b.get("tp_pct", 5.0) / 100)

        registro = Billetera(
            timestamp        = datetime.now(timezone.utc),
            ciclo            = ciclo,
            usdt             = b.get("usdt", 0),
            btc              = b.get("btc", 0),
            precio_btc_ref   = precio_btc,
            valor_total_usdt = valor_total,
            en_posicion      = b.get("en_posicion", False),
            precio_compra    = b.get("precio_compra"),
            stop_loss_precio = sl_precio,
            take_profit_precio = tp_precio,
            ganancia_total   = b.get("ganancia_total", 0),
            operaciones_count= len(b.get("operaciones", [])),
            evento           = evento,
        )
        session.add(registro)
        session.commit()
        return True
    except SQLAlchemyError as e:
        session.rollback()
        print(f"[DB ERROR] guardar_estado_billetera: {e}")
        return False
    finally:
        session.close()


def guardar_operacion(datos_op: dict, indicadores: dict = None) -> bool:
    """Guarda una operación hipotética (compra/venta) en la base de datos."""
    session = get_session()
    try:
        op = Operacion(
            timestamp       = datetime.now(timezone.utc),
            ciclo           = datos_op.get("ciclo"),
            tipo            = datos_op.get("tipo"),
            precio          = datos_op.get("precio"),
            btc_cantidad    = datos_op.get("btc"),
            usdt_cantidad   = datos_op.get("usdt"),
            ganancia_usdt   = datos_op.get("ganancia"),
            motivo          = datos_op.get("motivo", ""),
            rsi_al_operar   = indicadores.get("rsi") if indicadores else None,
        )
        session.add(op)
        session.commit()
        return True
    except SQLAlchemyError as e:
        session.rollback()
        print(f"[DB ERROR] guardar_operacion: {e}")
        return False
    finally:
        session.close()


# ==============================================================================
# FUNCIONES DE LECTURA
# ==============================================================================

def obtener_ultimos_ciclos(n: int = 10) -> list[dict]:
    """Devuelve los últimos N ciclos de observación."""
    session = get_session()
    try:
        ciclos = (session.query(CicloObservacion)
                  .order_by(CicloObservacion.id.desc())
                  .limit(n)
                  .all())
        return [
            {
                "ciclo":          c.ciclo,
                "timestamp":      str(c.timestamp),
                "precio_btc":     c.precio_btc,
                "rsi":            c.rsi,
                "decision_final": c.decision_final,
                "tiempo_seg":     c.tiempo_ciclo_seg,
            }
            for c in reversed(ciclos)
        ]
    except SQLAlchemyError as e:
        print(f"[DB ERROR] obtener_ultimos_ciclos: {e}")
        return []
    finally:
        session.close()


def obtener_estadisticas() -> dict:
    """Devuelve estadísticas generales del modo observación."""
    session = get_session()
    try:
        from sqlalchemy import func
        total = session.query(func.count(CicloObservacion.id)).scalar() or 0
        compras = session.query(func.count(CicloObservacion.id)).filter(
            CicloObservacion.decision_final == "COMPRA").scalar() or 0
        ventas = session.query(func.count(CicloObservacion.id)).filter(
            CicloObservacion.decision_final == "VENTA").scalar() or 0
        esperar = session.query(func.count(CicloObservacion.id)).filter(
            CicloObservacion.decision_final == "ESPERAR").scalar() or 0
        errores = session.query(func.count(CicloObservacion.id)).filter(
            CicloObservacion.error.isnot(None)).scalar() or 0
        return {
            "total_ciclos": total,
            "compras":      compras,
            "ventas":       ventas,
            "esperar":      esperar,
            "errores":      errores,
            "pct_compra":   round(compras / total * 100, 1) if total > 0 else 0,
            "pct_venta":    round(ventas  / total * 100, 1) if total > 0 else 0,
            "pct_esperar":  round(esperar / total * 100, 1) if total > 0 else 0,
        }
    except SQLAlchemyError as e:
        print(f"[DB ERROR] obtener_estadisticas: {e}")
        return {}
    finally:
        session.close()


# ==============================================================================
# INICIALIZACIÓN DIRECTA
# ==============================================================================

if __name__ == "__main__":
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    console.print(Panel.fit("[bold cyan]🗄️  Test de Base de Datos PostgreSQL[/bold cyan]"))

    # 1. Verificar conexión
    console.print("[yellow]⏳ Verificando conexión a PostgreSQL...[/yellow]")
    ok, msg = verificar_conexion()
    if ok:
        console.print(f"[green]✅ Conectado: {msg[:80]}[/green]")
    else:
        console.print(f"[red]❌ Error: {msg}[/red]")
        sys.exit(1)

    # 2. Crear tablas
    console.print("[yellow]⏳ Creando tablas...[/yellow]")
    crear_tablas()
    console.print("[green]✅ Tablas creadas/verificadas[/green]")

    # 3. Mostrar cadena de conexión (sin password)
    from config import DB_SERVER, DB_PORT, DB_DATABASE, DB_USER
    console.print(Panel.fit(
        f"[bold green]✅ PostgreSQL listo[/bold green]\n"
        f"Servidor: {DB_SERVER}:{DB_PORT}\n"
        f"Base de datos: {DB_DATABASE}\n"
        f"Usuario: {DB_USER}\n"
        f"Tablas: ciclos_observacion, noticias_cache, billetera, operaciones",
        border_style="green"
    ))
