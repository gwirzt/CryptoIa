# 🤖 CryptoIA — Guía de Arquitectura y Tests
## Sistema Multi-Agente de Trading con Inteligencia Artificial Local

> **Para:** Usuarios y desarrolladores que quieren entender cómo funciona el sistema  
> **Servidor de IAs:** `192.168.1.8` | **Exchange:** Binance (datos públicos, sin API key) | **Activo:** BTC/USDT

---

## 📖 ¿Qué es CryptoIA?

CryptoIA es un **bot de trading automatizado** que utiliza **3 inteligencias artificiales locales** para analizar el mercado real de Bitcoin (BTC/USDT) en Binance y tomar decisiones de compra/venta.

A diferencia de los bots tradicionales que usan reglas fijas (ej: "si RSI < 30, comprar"), CryptoIA le **pregunta a 3 IAs especializadas** con datos reales del mercado y espera que lleguen a un consenso antes de recomendar cualquier operación.

> **Estado actual:** Modo observación — el sistema analiza el mercado real cada 15 minutos y registra sus decisiones hipotéticas en `logs/observacion.csv`, sin ejecutar operaciones reales.

---

## 🔄 Flujo de Trabajo Real

Cada 15 minutos, el sistema ejecuta este ciclo con datos reales:

```
┌─────────────────────────────────────────────────────────────────┐
│              CICLO REAL (cada 15 minutos)                       │
└─────────────────────────────────────────────────────────────────┘

  📊 BINANCE (datos públicos)       📰 NOTICIAS RSS (tiempo real)
  ────────────────────────          ──────────────────────────────
  Precio BTC actual                 CoinTelegraph ES/EN
  Últimas 150 velas de 15m          Bitcoin Magazine
  Volumen de trading                CoinDesk
       │                                    │
       ▼                                    ▼
  Cálculo de indicadores         Filtro: últimas 4 horas
  RSI, MACD, Bollinger,          Deduplicación por hash
  EMA 9/21, Volumen relativo      Ordenado por más reciente
       │                                    │
       ▼                                    ▼
┌──────────────────────┐        ┌──────────────────────────┐
│   AGENTE TÉCNICO     │        │   AGENTE FUNDAMENTAL     │
│   GPU 0 :11431       │        │   GPU 1 :11432           │
│   qwen2.5:7b         │        │   qwen2.5:3b             │
│                      │        │                          │
│  Recibe reporte con  │        │  Recibe titulares reales │
│  indicadores reales  │        │  de noticias de Bitcoin  │
│                      │        │                          │
│  Responde JSON:      │        │  Responde JSON:          │
│  accion + confianza  │        │  impacto + intensidad    │
│  + justificacion     │        │  + justificacion         │
└──────────┬───────────┘        └────────────┬─────────────┘
           │                                 │
           └──────────────┬──────────────────┘
                          │
                    Normalizador
                    (corrige variantes
                    de idioma/formato)
                          │
                          ▼
             ┌────────────────────────┐
             │   GESTOR DE RIESGOS   │
             │   GPU 2 :11433        │
             │   qwen2.5:3b          │
             │                       │
             │  Recibe:              │
             │  • Veredicto técnico  │
             │  • Veredicto noticias │
             │  • Precio actual BTC  │
             │  • Estado billetera   │
             │                       │
             │  Decide:              │
             │  • COMPRA/VENTA/      │
             │    ESPERAR            │
             │  • Stop-Loss %        │
             │  • Take-Profit %      │
             └──────────┬────────────┘
                        │
                        ▼
             ┌────────────────────────┐
             │  MODO OBSERVACIÓN     │
             │                       │
             │  Registra en CSV:     │
             │  • Decisión del comité│
             │  • Precio real        │
             │  • Todos indicadores  │
             │  • Billetera hipotét. │
             │                       │
             │  ⚠️ NO ejecuta        │
             │  operaciones reales   │
             └────────────────────────┘
```

---

## 🤖 Los 3 Agentes de IA — Roles y Responsabilidades

---

### 🔵 Agente 1: Analista Técnico
**"El que mira los gráficos"**

| Propiedad | Valor |
|-----------|-------|
| **GPU** | GPU 0 |
| **Puerto** | `192.168.1.8:11431` |
| **Modelo** | `qwen2.5:7b` (7 mil millones de parámetros — el más potente) |
| **Especialidad** | Análisis técnico de precios y volumen en tiempo real |

**¿Qué recibe?** Un reporte generado automáticamente con los indicadores calculados sobre las últimas 150 velas reales de Binance:

```
=== DATOS DE MERCADO EN TIEMPO REAL ===
Par: BTC/USDT | Temporalidad: 15m
Precio actual: 62,736.13 USDT (+0.003%)

RSI (14): 45.8  → Zona: NEUTRAL
MACD: Histograma -44.27 (NEGATIVO)
Bollinger: precio en banda INFERIOR
EMA 9: 62,862 / EMA 21: 62,891 → BAJISTA
Volumen relativo: 89.4% del promedio
```

**¿Qué responde?**
```json
{
  "accion": "ESPERAR",
  "confianza": 75,
  "justificacion": "El precio se encuentra en las bandas inferiores y hay una tendencia bajista, pero el MACD negativo y RSI neutral no son señales claras para operar."
}
```

---

### 🟡 Agente 2: Analista Fundamental
**"El que lee las noticias"**

| Propiedad | Valor |
|-----------|-------|
| **GPU** | GPU 1 |
| **Puerto** | `192.168.1.8:11432` |
| **Modelo** | `qwen2.5:3b` |
| **Especialidad** | Análisis de noticias RSS reales de Bitcoin |

**¿Qué recibe?** Los últimos titulares reales de las últimas 4 horas de:
- CoinTelegraph ES/EN
- Bitcoin Magazine  
- CoinDesk

**Ejemplo de noticias reales recibidas:**
```
NOTICIA 1 (hace 26 minutos):
"Public Companies Added 43,557 BTC in May as SpaceX Enters Bitcoin..."
Fuente: Bitcoin Magazine

NOTICIA 2 (hace 90 minutos):
"Bitcoin tags $63.2K as BTC price action ignores inflation, Iran H..."
Fuente: CoinTelegraph EN
```

**¿Qué responde?**
```json
{
  "impacto": "ALCISTA",
  "intensidad": 70,
  "justificacion": "Las noticias muestran actividad institucional creciente en Bitcoin, incluyendo empresas públicas y SpaceX."
}
```

---

### 🔴 Agente 3: Gestor de Riesgos
**"El árbitro final"**

| Propiedad | Valor |
|-----------|-------|
| **GPU** | GPU 2 |
| **Puerto** | `192.168.1.8:11433` |
| **Modelo** | `qwen2.5:3b` |
| **Especialidad** | Decisión final con gestión de capital |

**¿Qué recibe?** Los veredictos normalizados de los otros dos agentes + precio real + estado de billetera.

**¿Qué responde?**
```json
{
  "decision": "ESPERAR",
  "stop_loss_pct": 2.5,
  "take_profit_pct": 5.0,
  "motivo": "Señales técnicas bajistas contradicen el sentimiento fundamental alcista. Mejor esperar confirmación."
}
```

---

## 🔧 Módulo Normalizador

Los modelos de IA a veces responden con variantes del texto esperado (ej: "ESPORTE" en lugar de "ESPERAR", "buy" en lugar de "COMPRA"). El módulo `src/agentes/normalizador.py` estandariza automáticamente todas las respuestas:

```
"esporte"  → ESPERAR
"buy"      → COMPRA  
"sell"     → VENTA
"hold"     → ESPERAR
"bullish"  → ALCISTA
"bearish"  → BAJISTA
```

---

## 📊 Indicadores Técnicos Calculados en Tiempo Real

Todos los indicadores se calculan sobre las **últimas 150 velas reales de Binance** usando la librería `ta`:

### RSI — Índice de Fuerza Relativa (14 períodos)
```
RSI < 30  →  SOBREVENDIDO  →  Posible rebote  →  Señal de COMPRA
RSI > 70  →  SOBRECOMPRADO →  Posible caída   →  Señal de VENTA
RSI 30-70 →  NEUTRAL       →  Sin señal clara
```

### MACD (12, 26, 9)
```
Histograma POSITIVO + cruce ALCISTA  →  Tendencia alcista  →  COMPRA
Histograma NEGATIVO + cruce BAJISTA  →  Tendencia bajista  →  VENTA
```

### Bandas de Bollinger (20, 2)
```
Precio en banda INFERIOR  →  Precio bajo, posible rebote  →  COMPRA
Precio en banda SUPERIOR  →  Precio alto, posible caída   →  VENTA
Precio en banda MEDIA     →  Zona neutral
```

### EMA 9 y EMA 21
```
EMA 9 > EMA 21  →  Tendencia ALCISTA de corto plazo
EMA 9 < EMA 21  →  Tendencia BAJISTA de corto plazo
```

### Volumen Relativo
```
> 120% del promedio  →  Alto interés del mercado
80-120%             →  Volumen normal
< 80%               →  Bajo interés
```

---

## 🗳️ Sistema de Consenso

```
┌─────────────────────────────────────────────────────────┐
│              LÓGICA DE CONSENSO (GPU 2)                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  GPU0=COMPRA  + GPU1=ALCISTA  → GPU2 tiende a COMPRA ✅ │
│  GPU0=VENTA   + GPU1=BAJISTA  → GPU2 tiende a VENTA  ✅ │
│  GPU0=COMPRA  + GPU1=BAJISTA  → GPU2 tiende a ESPERAR⏸️ │
│  GPU0=VENTA   + GPU1=ALCISTA  → GPU2 tiende a ESPERAR⏸️ │
│  GPU0=ESPERAR + cualquiera    → GPU2 tiende a ESPERAR⏸️ │
│                                                         │
│  GPU2 también considera:                                │
│  • Precio actual del BTC                                │
│  • Capital disponible en billetera                      │
│  • Reglas de stop-loss y take-profit                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 💰 Billetera Hipotética (Modo Observación)

Durante el modo observación, el sistema **simula** qué hubiera pasado si hubiera operado:

```
Capital inicial: 10.000 USDT

Ejemplo de ciclo real (11/06/2026):
┌─────────────────────────────────────────────────────┐
│  Precio BTC real:     $62,749.37 USDT               │
│  RSI real:            46.2 (NEUTRAL)                │
│  Decisión comité:     ESPERAR                       │
│  → No se simula operación                           │
│                                                     │
│  Si hubiera sido COMPRA:                            │
│  BTC comprados:       0.15934 BTC                   │
│  Stop-Loss en -2.5%:  $61,180.14 USDT               │
│  Take-Profit en +5%:  $65,886.84 USDT               │
└─────────────────────────────────────────────────────┘
```

---

## 🧪 Tests Disponibles

### Test 0: Conectividad
**Archivo:** `tests/test_conexion.py`

Verifica que todos los servicios están accesibles: 3 GPUs Ollama + SQL Server.

```bash
venv\Scripts\python.exe tests\test_conexion.py
```

---

### Test 1: Mercado Real
**Archivo:** `tests/test_mercado_real.py`

Conecta a Binance, descarga las últimas 150 velas reales de BTC/USDT, calcula todos los indicadores técnicos y muestra el reporte que se enviará al Agente Técnico.

**¿Qué muestra?**
- Precio actual real de BTC
- RSI, MACD, Bollinger, EMAs, Volumen calculados en tiempo real
- El texto exacto del reporte que recibirá la IA

**¿Cómo saber si pasó?**
- ✅ **PASÓ:** Muestra precio real y tabla de indicadores
- ❌ **FALLÓ:** Error de conexión a Binance o error en cálculo de indicadores

```bash
venv\Scripts\python.exe tests\test_mercado_real.py
```

---

### Test 2: Comité Real (Un ciclo completo)
**Archivo:** `tests/test_comite_real.py`

Ejecuta un ciclo completo con datos reales: obtiene precio y noticias actuales, consulta a los 3 agentes y muestra la decisión del comité. **No ejecuta ninguna operación.**

**¿Qué hace paso a paso?**
1. Conecta a Binance → obtiene precio y calcula indicadores reales
2. Obtiene noticias RSS reales de las últimas 4 horas
3. Consulta al Agente Técnico (GPU 0) con los datos reales
4. Consulta al Agente Fundamental (GPU 1) con las noticias reales
5. Envía ambos veredictos al Gestor de Riesgos (GPU 2)
6. Muestra la decisión final del comité

**Tiempo esperado:** 30-60 segundos (depende de la carga de las GPUs)

**¿Cómo saber si pasó?**
- ✅ **PASÓ:** Los 3 agentes responden con JSON válido y se muestra la decisión
- ⚠️ **PARCIAL:** Algún agente tardó mucho o respondió con formato incorrecto (el normalizador lo corrige)
- ❌ **FALLÓ:** Error de conexión a Binance o a alguna GPU

```bash
venv\Scripts\python.exe tests\test_comite_real.py
```

---

### Test 3: Modo Observación 24/7
**Archivo:** `tests/test_observacion.py`

Corre en bucle continuo, ejecutando un ciclo completo cada 15 minutos. Registra cada decisión en `logs/observacion.csv` para analizar el rendimiento hipotético del bot a lo largo del tiempo.

**¿Qué registra en el CSV?**
- Timestamp del ciclo
- Precio real de BTC
- Todos los indicadores técnicos
- Decisión de cada agente (técnico, fundamental, riesgo)
- Decisión final del comité
- Estado de la billetera hipotética
- Tiempo que tardó el ciclo

**¿Cómo interpretar el CSV?**
Abrilo en Excel o Google Sheets para ver:
- ¿Cuántas veces el bot hubiera comprado/vendido?
- ¿Cuál hubiera sido el rendimiento hipotético?
- ¿En qué condiciones de RSI el comité decide comprar?
- ¿Hay coherencia entre las decisiones de los 3 agentes?

**Detener con:** `Ctrl+C` — muestra un resumen de operaciones hipotéticas al salir.

```bash
# Corre indefinidamente (días/semanas)
venv\Scripts\python.exe tests\test_observacion.py
```

---

## 🚀 Guía Rápida de Ejecución

```bash
# 1. Activar entorno virtual
cd c:\pythonDev\CryptoIa
venv\Scripts\activate

# 2. Verificar conectividad (siempre primero)
python tests\test_conexion.py

# 3. Ver datos reales del mercado ahora mismo
python tests\test_mercado_real.py

# 4. Ejecutar un ciclo completo del comité con datos reales
python tests\test_comite_real.py

# 5. Iniciar modo observación 24/7 (deja corriendo días)
python tests\test_observacion.py
```

---

## 📁 Estructura del Proyecto

```
CryptoIa/
├── src/
│   ├── mercado/
│   │   └── binance_client.py    ← Datos reales de Binance + indicadores
│   ├── noticias/
│   │   └── feed_manager.py      ← RSS reales de CoinTelegraph, CoinDesk, etc.
│   ├── agentes/
│   │   └── normalizador.py      ← Normaliza respuestas de las IAs
│   ├── trading/                 ← (FASE 4 — pendiente)
│   └── dashboard/               ← (FASE 5 — pendiente)
├── tests/
│   ├── test_conexion.py         ← Verifica conectividad con todos los servicios
│   ├── test_mercado_real.py     ← Muestra indicadores reales de Binance
│   ├── test_comite_real.py      ← Un ciclo completo con datos reales
│   └── test_observacion.py      ← Modo observación 24/7 (sin operar)
├── logs/
│   └── observacion.csv          ← Registro de decisiones del comité
├── docs/
│   └── arquitectura.md          ← Este documento
├── config.py                    ← Configuración centralizada
├── .env                         ← Variables de entorno (no commitear)
├── requirements.txt             ← Dependencias Python
├── run_bot.py                   ← Punto de entrada principal
└── hoja_de_ruta.md              ← Plan de desarrollo por fases
```

---

## ⚙️ Configuración (`.env`)

```env
# Servidor de IAs
SERVIDOR_IA=192.168.1.8
PUERTO_GPU0=11431        # Agente Técnico (qwen2.5:7b)
PUERTO_GPU1=11432        # Agente Fundamental (qwen2.5:3b)
PUERTO_GPU2=11433        # Gestor de Riesgos (qwen2.5:3b)
MODELO_GPU0=qwen2.5:7b
MODELO_GPU1=qwen2.5:3b
MODELO_GPU2=qwen2.5:3b

# Trading
EXCHANGE=binance
SIMBOLO=BTC/USDT
TEMPORALIDAD=15m
CAPITAL_INICIAL=10000
```

---

## 📚 Glosario de Términos

| Término | Definición |
|---------|------------|
| **RSI** | Indicador 0-100 que mide si el mercado está sobrecomprado (>70) o sobrevendido (<30) |
| **MACD** | Indicador que detecta cambios de tendencia mediante cruces de líneas |
| **Bollinger** | Bandas que definen el rango "normal" de precio. Precio fuera de las bandas suele volver al centro |
| **EMA** | Media Móvil Exponencial. Da más peso a los precios recientes |
| **Stop-Loss** | Venta automática si el precio cae X% para limitar pérdidas |
| **Take-Profit** | Venta automática si el precio sube X% para asegurar ganancias |
| **COMPRA** | El comité recomienda comprar BTC con USDT disponibles |
| **VENTA** | El comité recomienda vender BTC y convertir a USDT |
| **ESPERAR** | El comité no recomienda operar en este ciclo |
| **FUD** | Fear, Uncertainty, Doubt. Noticias negativas que pueden ser exageradas |
| **FOMO** | Fear Of Missing Out. Euforia de mercado que puede indicar sobrecompra |
| **Ollama** | Software que permite correr modelos de IA localmente en el servidor |
| **OHLCV** | Open, High, Low, Close, Volume. Los 5 datos de cada vela de precio |
| **Vela** | Representación del precio en un período de tiempo (aquí: 15 minutos) |
| **Modo observación** | El bot analiza el mercado real pero NO ejecuta operaciones |
| **Billetera hipotética** | Simulación de qué hubiera pasado si el bot hubiera operado |

---

## ⚠️ Notas Importantes

1. **NUNCA** commitear el archivo `.env` al repositorio (ya está en `.gitignore`)
2. El bot opera en **modo observación** — no ejecuta operaciones reales
3. Los modelos Ollama deben estar **precargados** en el servidor antes de iniciar
4. Binance no requiere API key para leer precios públicos
5. El CSV de observación crece ~1KB por ciclo (15 min) → ~100KB/día → ~3MB/mes

---

*Última actualización: Junio 2026*  
*Estado: FASE 1 completada — Módulo de mercado real funcionando*  
*Próximo paso: Dejar correr el modo observación varios días, luego FASE 2 (noticias mejoradas)*
