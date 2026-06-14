# Sistema de 3 IAs — CryptoIA Paper Trading

**Versión:** 2.0 — Junio 2026  
**Servidor:** 192.168.1.8 (Ollama)  
**Par:** BTC/USDT — Temporalidad: 15 minutos

---

## Arquitectura General

El sistema utiliza **tres IAs independientes** corriendo en el mismo servidor físico (192.168.1.8) pero en puertos distintos, cada una con un rol específico. Cada 15 minutos el bot ejecuta un ciclo completo consultando a las tres IAs en secuencia.

```
┌─────────────────────────────────────────────────────────────┐
│                    CICLO CADA 15 MINUTOS                    │
│                                                             │
│  Binance API ──► Indicadores técnicos (RSI, MACD, BB, EMA) │
│  RSS Feeds   ──► Noticias de Bitcoin (últimas 24hs)         │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────┐    │
│  │  GPU0    │   │    GPU1      │   │      GPU2        │    │
│  │ Técnico  │   │ Fundamental  │   │  Gestor Riesgos  │    │
│  │qwen2.5:7b│   │ qwen2.5:3b   │   │  qwen2.5:3b      │    │
│  │ :11431   │   │   :11432     │   │    :11433        │    │
│  └────┬─────┘   └──────┬───────┘   └────────┬─────────┘    │
│       │                │                    │              │
│       └────────────────┴────────────────────┘              │
│                          │                                  │
│                          ▼                                  │
│              DECISIÓN FINAL + EJECUCIÓN                     │
│         (COMPRA / VENTA / ESPERAR)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## IA #1 — Agente Técnico (GPU0)

| Parámetro | Valor |
|-----------|-------|
| **Puerto** | 11431 |
| **Modelo** | `qwen2.5:7b` (el más potente del sistema) |
| **Rol** | Análisis de indicadores técnicos del mercado |
| **Responde** | `COMPRA`, `VENTA` o `ESPERAR` + porcentaje de confianza |

### ¿Qué analiza?

Recibe los siguientes indicadores calculados sobre velas de 15 minutos de Binance:

- **RSI (14 períodos):** Mide si el mercado está sobrecomprado (>70) o sobrevendido (<30)
- **MACD:** Detecta cambios de tendencia (cruce de medias móviles)
- **Bandas de Bollinger:** Indica si el precio está en zona alta, media o baja del rango
- **EMA (9, 21, 50 períodos):** Tendencia de corto, mediano y largo plazo
- **Volumen relativo:** Si el volumen actual es mayor o menor al promedio

### ¿Cuándo dice COMPRA?

- RSI en zona neutral (40-65) con tendencia alcista
- MACD positivo (histograma creciente)
- Precio cerca de la banda media o inferior de Bollinger
- EMA corta por encima de EMA larga (tendencia alcista)
- Confianza reportada ≥ 65%

### ¿Cuándo dice VENTA?

- RSI > 70 (sobrecomprado)
- MACD negativo o cruzando a la baja
- Precio en banda superior de Bollinger con señales de reversión
- EMA corta cruzando por debajo de EMA larga

### ¿Cuándo dice ESPERAR?

- Señales mixtas o contradictorias
- Mercado lateral sin tendencia clara
- Confianza < 65%

---

## IA #2 — Agente Fundamental (GPU1)

| Parámetro | Valor |
|-----------|-------|
| **Puerto** | 11432 |
| **Modelo** | `qwen2.5:3b` |
| **Rol** | Análisis de noticias y contexto macroeconómico |
| **Responde** | `ALCISTA`, `BAJISTA` o `NEUTRAL` + intensidad (0-100) |

### ¿Qué analiza?

Recibe titulares de noticias de Bitcoin de las últimas 24 horas obtenidos de feeds RSS de fuentes como CoinDesk, CoinTelegraph, Bitcoin Magazine, etc.

Evalúa el **sentimiento del mercado** basándose en:

- Noticias regulatorias (aprobaciones ETF, restricciones, etc.)
- Adopción institucional (compras de empresas, fondos)
- Eventos macroeconómicos (tasas de interés, inflación)
- Noticias de seguridad (hacks, fraudes)
- Declaraciones de figuras influyentes

### ¿Cuándo dice ALCISTA?

- Noticias positivas de adopción o regulación favorable
- Compras institucionales significativas
- Contexto macro favorable (baja de tasas, debilidad del dólar)

### ¿Cuándo dice BAJISTA?

- Restricciones regulatorias o prohibiciones
- Hacks o fraudes importantes
- Contexto macro negativo (suba de tasas, crisis)

### ¿Cuándo dice NEUTRAL?

- Sin noticias relevantes recientes
- Noticias mixtas que se compensan
- Noticias de bajo impacto

### Caché de noticias

Para evitar procesar la misma noticia dos veces, el sistema guarda un hash MD5 de cada titular en la tabla `noticias_cache` de PostgreSQL. Si una noticia ya fue procesada, se omite.

---

## IA #3 — Gestor de Riesgos (GPU2)

| Parámetro | Valor |
|-----------|-------|
| **Puerto** | 11433 |
| **Modelo** | `qwen2.5:3b` |
| **Rol** | Gestión de posiciones abiertas — decide cuándo vender |
| **Responde** | `VENTA` o `ESPERAR` + niveles de SL/TP sugeridos |

### ¿Cuándo se consulta?

**Solo cuando hay una posición abierta.** Si no hay posición, el GPU2 no se consulta (para evitar que vete las compras, lo cual hacía antes).

### ¿Qué evalúa?

Recibe:
- Datos de mercado actuales (precio, RSI, MACD, EMA)
- Análisis del Técnico y Fundamental
- Estado de la posición: precio de compra, P&L actual, ciclos en posición
- Niveles de Stop-Loss y Take-Profit configurados

### Reglas de decisión (en orden de prioridad):

1. Si el Técnico dice VENTA → **VENTA**
2. Si RSI > 72 (sobrecomprado) → **VENTA**
3. Si MACD negativo Y P&L < -1% → **VENTA** (cortar pérdidas)
4. Si P&L > 3% Y tendencia se debilita → **VENTA** (asegurar ganancia)
5. Si todo sigue bien → **ESPERAR**

---

## Lógica de Decisión Final

### Flujo completo de un ciclo:

```
1. Obtener precio y indicadores de Binance
2. Verificar Stop-Loss automático (-2.5%) → si se activa: VENTA_SL
3. Verificar Take-Profit automático (+5%) → si se activa: VENTA_TP
4. Verificar venta por tiempo (>8 ciclos en posición con P&L>0.5%) → VENTA_TIEMPO
5. Consultar GPU0 (Técnico) → COMPRA/VENTA/ESPERAR + confianza%
6. Consultar GPU1 (Fundamental) → ALCISTA/BAJISTA/NEUTRAL + intensidad%
7. Decisión:
   ├── SIN POSICIÓN:
   │   ├── Técnico=COMPRA + confianza≥65% + Fundamental≠BAJISTA → COMPRA directa
   │   ├── Técnico=COMPRA + Fundamental=BAJISTA → ESPERAR
   │   └── Técnico=ESPERAR/VENTA → ESPERAR
   └── CON POSICIÓN:
       └── Consultar GPU2 (Gestor Riesgos) → VENTA o ESPERAR
8. Ejecutar decisión en billetera virtual
9. Guardar en PostgreSQL + CSV
```

### ¿Por qué el GPU2 no decide las compras?

El modelo `qwen2.5:3b` es conservador por naturaleza y tiende a decir ESPERAR ante cualquier duda. Cuando se le pedía que decidiera tanto compras como ventas, vetaba sistemáticamente las compras incluso cuando el Técnico tenía alta confianza. Por eso se separaron los roles:

- **GPU0 (7b)** → decide entradas (más capaz, más agresivo)
- **GPU2 (3b)** → decide salidas (conservador = bueno para proteger ganancias)

---

## Sistema de Utilidades

### ¿Cómo funciona?

El sistema opera con un **capital fijo de $10,000 USDT** y separa las ganancias en una "caja de utilidades":

```
Ejemplo de ciclo completo:

  Estado inicial: $10,000 USDT disponibles

  Ciclo #5:  Técnico=COMPRA (75%) + Fundamental=ALCISTA
             → COMPRA: 0.15625 BTC a $64,000
             → Billetera: $0 USDT + 0.15625 BTC

  Ciclo #12: BTC sube a $67,200 (+5%)
             → TAKE-PROFIT automático activado
             → VENTA: 0.15625 BTC × $67,200 = $10,500
             → Ganancia: +$500 USDT (+5%)
             → Caja de utilidades: +$500 (acumulado)
             → Capital operativo: reseteado a $10,000

  Ciclo #15: Técnico=COMPRA nuevamente
             → COMPRA con los mismos $10,000
             (las utilidades no se arriesgan)
```

### Tipos de venta:

| Tipo | Descripción | Resultado |
|------|-------------|-----------|
| `VENTA` | Decisión del GPU2 | Ganancia o pérdida |
| `VENTA_TP` | Take-Profit automático (+5%) | Siempre ganancia |
| `VENTA_SL` | Stop-Loss automático (-2.5%) | Pérdida controlada |
| `VENTA_TIEMPO` | Más de 8 ciclos en posición con P&L>0.5% | Ganancia asegurada |

### Resultado esperado a largo plazo:

- **Capital operativo:** siempre $10,000 (salvo pérdidas por SL)
- **Caja de utilidades:** crece con cada operación ganadora
- **Riesgo máximo por operación:** -2.5% = -$250 USDT
- **Ganancia objetivo por operación:** +5% = +$500 USDT

---

## Configuración (.env)

```env
# IAs
SERVIDOR_IA=192.168.1.8
PUERTO_GPU0=11431          # Agente Técnico (qwen2.5:7b)
PUERTO_GPU1=11432          # Agente Fundamental (qwen2.5:3b)
PUERTO_GPU2=11433          # Gestor de Riesgos (qwen2.5:3b)

# Trading
CAPITAL_INICIAL=10000      # Capital operativo en USDT
STOP_LOSS_PCT=2.5          # Stop-Loss: -2.5%
TAKE_PROFIT_PCT=5.0        # Take-Profit: +5%
CICLOS_MAX_EN_POSICION=8   # Máx ciclos antes de venta por tiempo
INTERVALO_MINUTOS=15       # Frecuencia de análisis
TEMPORALIDAD=15m           # Velas de Binance para indicadores
```

---

## Base de Datos PostgreSQL

**Servidor:** 192.168.1.8:5432  
**Base:** CryptoTrade

| Tabla | Contenido |
|-------|-----------|
| `ciclos_observacion` | Registro de cada ciclo: precio, indicadores, decisiones de las 3 IAs |
| `billetera` | Estado de la billetera virtual en cada ciclo |
| `operaciones` | Historial de compras y ventas ejecutadas |
| `noticias_cache` | Noticias ya procesadas (evita duplicados) |

### Consultar datos:

```bash
# Ver resumen general
python3 tests/ver_datos.py

# Ver historial de billetera
python3 tests/ver_datos.py --billetera

# Ver solo ciclos con COMPRA
python3 tests/ver_datos.py --compras

# Ver todo
python3 tests/ver_datos.py --todo
```

---

## Limitaciones actuales

1. **Solo BTC/USDT:** El sistema está optimizado para Bitcoin. Agregar otros pares requeriría ajustar los prompts.

2. **Modelos pequeños:** `qwen2.5:3b` tiene contexto limitado y puede ser inconsistente. El `qwen2.5:7b` del GPU0 es más confiable.

3. **Sin memoria entre reinicios:** La billetera virtual se resetea al reiniciar el bot. Los datos históricos quedan en PostgreSQL pero el estado en memoria se pierde.

4. **Paper trading únicamente:** El sistema NO ejecuta operaciones reales. Es una simulación para evaluar la estrategia antes de conectar a una exchange real.

5. **Latencia de noticias:** Los feeds RSS pueden tener retraso de 15-60 minutos respecto a eventos reales.

---

*Documento generado automáticamente — CryptoIA v2.0 — Junio 2026*
