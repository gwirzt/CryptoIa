# CryptoIA — Guía de Configuración Completa

> Documento de referencia para entender qué hace cada variable del archivo `.env`.
> Última actualización: Junio 2026

---

## Índice

1. [Base de Datos](#1-base-de-datos)
2. [Servidor de IA (Ollama)](#2-servidor-de-ia-ollama)
3. [Binance — Exchange](#3-binance--exchange)
4. [Trading — Configuración General](#4-trading--configuración-general)
5. [Gestión de Riesgo](#5-gestión-de-riesgo)
6. [Timeout de Posición](#6-timeout-de-posición)
7. [Compra — Lógica y Umbrales](#7-compra--lógica-y-umbrales)
8. [Venta — Protecciones de la IA](#8-venta--protecciones-de-la-ia)
9. [DCA — Dollar Cost Averaging](#9-dca--dollar-cost-averaging)
10. [Zona Horaria y Logging](#10-zona-horaria-y-logging)
11. [Flujo de decisión del bot](#11-flujo-de-decisión-del-bot)
12. [Perfiles de configuración recomendados](#12-perfiles-de-configuración-recomendados)

---

## 1. Base de Datos

```ini
DB_SERVER=192.168.1.6
DB_PORT=5432
DB_DATABASE=CryptoTrade
DB_USER=Crypto
DB_PASSWORD=tu_password
```

| Variable | Descripción |
|----------|-------------|
| `DB_SERVER` | IP del servidor PostgreSQL |
| `DB_PORT` | Puerto de PostgreSQL (default: 5432) |
| `DB_DATABASE` | Nombre de la base de datos |
| `DB_USER` | Usuario de la base de datos |
| `DB_PASSWORD` | Contraseña del usuario |

**¿Para qué se usa la DB?** El bot guarda en PostgreSQL:
- Posiciones abiertas (`posicion_v2`)
- Historial de operaciones (`operaciones_v2`)
- Log de cada ciclo (`ciclos_log`)

---

## 2. Servidor de IA (Ollama)

```ini
SERVIDOR_IA=192.168.1.6
PUERTO_GPU0=11434
MODELO_GPU0=qwen2.5:7b
```

| Variable | Descripción |
|----------|-------------|
| `SERVIDOR_IA` | IP del servidor donde corre Ollama |
| `PUERTO_GPU0` | Puerto del servidor Ollama |
| `MODELO_GPU0` | Modelo de IA a usar (ej: `qwen2.5:7b`, `llama3.2:3b`) |

**¿Qué hace la IA?** En cada ciclo, el bot le envía a la IA:
- Precio actual y precio de compra
- Indicadores técnicos (RSI, MACD, EMAs, Bollinger)
- P&L actual en % y USDT
- Punto de equilibrio (precio mínimo para no perder)

La IA responde: `COMPRAR`, `VENDER` o `ESPERAR` con un nivel de confianza (0-100%).

**Modelos recomendados:**
- `qwen2.5:7b` — Mejor balance velocidad/calidad (recomendado)
- `qwen2.5:3b` — Más rápido, menor calidad
- `llama3.2:3b` — Alternativa liviana

---

## 3. Binance — Exchange

```ini
BINANCE_API_KEY=tu_api_key
BINANCE_SECRET=tu_secret
BINANCE_TESTNET=true
MODO_REAL=false
```

| Variable | Valores | Descripción |
|----------|---------|-------------|
| `BINANCE_API_KEY` | string | Clave API de Binance |
| `BINANCE_SECRET` | string | Secret de Binance |
| `BINANCE_TESTNET` | `true` / `false` | `true` = usa Testnet (dinero ficticio) |
| `MODO_REAL` | `true` / `false` | `false` = paper trading (sin órdenes reales) |

**Combinaciones posibles:**

| `BINANCE_TESTNET` | `MODO_REAL` | Resultado |
|-------------------|-------------|-----------|
| `true` | `false` | **Paper trading** — simula todo localmente, no toca Binance |
| `true` | `true` | **Testnet** — órdenes reales en Binance Testnet (dinero ficticio) |
| `false` | `true` | **Producción real** — órdenes reales con dinero real ⚠️ |

> **Recomendación:** Empezar siempre con `MODO_REAL=false` hasta validar la estrategia.

---

## 4. Trading — Configuración General

```ini
SIMBOLO=BTC/USDT
TEMPORALIDAD=5m
INTERVALO_MINUTOS=7
CAPITAL_INICIAL=10000
```

| Variable | Descripción |
|----------|-------------|
| `SIMBOLO` | Par de trading (ej: `BTC/USDT`, `ETH/USDT`) |
| `TEMPORALIDAD` | Temporalidad de las velas para análisis técnico |
| `INTERVALO_MINUTOS` | Cada cuántos minutos ejecuta un ciclo el bot |
| `CAPITAL_INICIAL` | Capital total en USDT disponible para operar |

**Relación TEMPORALIDAD / INTERVALO_MINUTOS:**

| `TEMPORALIDAD` | `INTERVALO_MINUTOS` recomendado |
|----------------|--------------------------------|
| `1m` | 1-2 |
| `5m` | 5-7 |
| `15m` | 15 |
| `1h` | 60 |

> **Importante:** Con DCA activado, `CAPITAL_INICIAL` se divide en partes iguales. Si tenés $700 y `DCA_NIVELES=4`, cada compra usa $175.

---

## 5. Gestión de Riesgo

### Stop-Loss

```ini
STOP_LOSS_PCT=1.5
```

**¿Qué hace?** Si el precio cae más de `STOP_LOSS_PCT`% desde el precio de compra, el bot vende automáticamente sin consultar a la IA.

**Es la ÚNICA forma de vender con pérdida real** (la guardia de equilibrio no aplica al stop-loss).

| Valor | Comportamiento |
|-------|---------------|
| `1.5%` | Agresivo — libera capital rápido, más stop-losses |
| `2.5%` | Moderado — más tolerante a fluctuaciones |
| `5.0%` | Conservador — pocas ventas forzadas, mayor riesgo |

**Ejemplo:** Compraste a $60.000. Con `STOP_LOSS_PCT=1.5`, vende automáticamente si el precio baja a $59.100.

---

### Take-Profit

```ini
TAKE_PROFIT_PCT=5.0
```

**¿Qué hace?** Si el precio sube más de `TAKE_PROFIT_PCT`% desde la compra, vende automáticamente asegurando la ganancia.

**Ejemplo:** Compraste a $60.000. Con `TAKE_PROFIT_PCT=5.0`, vende si el precio sube a $63.000.

---

### Trailing Stop

```ini
TRAILING_STOP_ACTIVACION_PCT=2.0
TRAILING_STOP_PROTECCION_PCT=0.5
```

**¿Qué hace?** Protege ganancias cuando el precio sube. Una vez que el precio subió `ACTIVACION`%, el stop-loss "sigue" al precio hacia arriba para proteger al menos `PROTECCION`% de ganancia.

**Ejemplo:**
- Compraste a $60.000
- Precio sube a $61.200 (+2% → se activa el trailing)
- Precio máximo alcanzado: $62.000
- Si el precio cae 0.5% desde $62.000 → vende a $61.690 (asegurando ganancia)

**Diferencia con Take-Profit:** El trailing stop no tiene un techo fijo, deja correr las ganancias mientras el precio siga subiendo.

---

### Comisiones

```ini
COMISION_TOTAL_PCT=0.2
```

**¿Qué hace?** Define el porcentaje total de comisiones del exchange (compra + venta). Se usa para calcular el **punto de equilibrio**: el precio mínimo al que se puede vender sin perder dinero real.

**Fórmula:** `precio_minimo_venta = precio_compra × (1 + COMISION_TOTAL_PCT / 100)`

**Ejemplo:** Compraste a $60.000 con comisiones del 0.2% → precio mínimo de venta = $60.120.

| Valor | Cuándo usarlo |
|-------|---------------|
| `0.2%` | Binance estándar (sin BNB) |
| `0.1%` | Binance pagando fees con BNB |

---

## 6. Timeout de Posición

```ini
CICLOS_MAX_EN_POSICION=20
CICLOS_MIN_EN_POSICION=1
COOLDOWN_POST_STOPLOSS=2
```

### CICLOS_MAX_EN_POSICION

**¿Qué hace?** Evita quedar "congelado" en una posición perdedora indefinidamente. Si el bot lleva más de `CICLOS_MAX_EN_POSICION` ciclos en la misma posición sin poder vender (porque el precio está bajo el punto de equilibrio), **fuerza la venta** para liberar capital y poder operar en niveles más bajos.

**Cálculo de tiempo:** `CICLOS_MAX_EN_POSICION × INTERVALO_MINUTOS = tiempo máximo`

| Valor | Tiempo máximo (con 7 min/ciclo) |
|-------|--------------------------------|
| `10` | ~1.2 horas |
| `20` | ~2.3 horas |
| `40` | ~4.7 horas |
| `60` | ~7 horas |

> **Nota:** Cuanto menor el valor, más agresivo el bot para liberar capital. Cuanto mayor, más paciente.

### CICLOS_MIN_EN_POSICION

**¿Qué hace?** Número mínimo de ciclos que el bot debe esperar antes de permitir que la IA venda. Evita salidas prematuras en los primeros minutos de una posición.

**Ejemplo:** Con `CICLOS_MIN_EN_POSICION=1`, la IA puede vender desde el segundo ciclo (7 minutos después de comprar).

### COOLDOWN_POST_STOPLOSS

**¿Qué hace?** Número de ciclos de espera después de un stop-loss antes de volver a comprar. Evita recomprar inmediatamente en una tendencia bajista.

**Ejemplo:** Con `COOLDOWN_POST_STOPLOSS=2`, después de un stop-loss el bot espera 2 ciclos (~14 minutos) antes de volver a evaluar compras.

---

## 7. Compra — Lógica y Umbrales

```ini
CONFIANZA_MIN_COMPRA=55
COMPRA_DETERMINISTA=true
COMPRA_DET_RSI_MIN=35
COMPRA_DET_RSI_MAX=65
MACD_HIST_MIN_COMPRA=-15.0
```

### CONFIANZA_MIN_COMPRA

**¿Qué hace?** La IA devuelve un nivel de confianza (0-100%) con cada decisión. Si dice COMPRAR pero con confianza menor a este valor, el bot ignora la señal y espera.

| Valor | Comportamiento |
|-------|---------------|
| `40-50` | Agresivo — compra con señales débiles |
| `55-65` | Moderado — balance entre oportunidades y seguridad |
| `70-80` | Conservador — solo compra con señales muy claras |

### COMPRA_DETERMINISTA

**¿Qué hace?** Si `true`, el bot puede comprar basándose solo en indicadores técnicos, sin esperar la señal de la IA. Evita que el bot nunca entre al mercado por exceso de conservadurismo de la IA.

**Condiciones para compra determinista (todas deben cumplirse):**
1. RSI entre `COMPRA_DET_RSI_MIN` y `COMPRA_DET_RSI_MAX`
2. MACD histograma > `MACD_HIST_MIN_COMPRA`
3. EMAs en tendencia alcista O precio cerca del piso de Bollinger

### COMPRA_DET_RSI_MIN / COMPRA_DET_RSI_MAX

**¿Qué hace?** Define el rango de RSI válido para la compra determinista.

| RSI | Interpretación |
|-----|---------------|
| < 30 | Sobrevendido extremo (posible rebote, pero también caída libre) |
| 30-40 | Zona de oportunidad |
| 40-60 | Zona neutral |
| 60-70 | Zona de precaución |
| > 70 | Sobrecomprado (no comprar) |

**Ejemplo:** Con `COMPRA_DET_RSI_MIN=35` y `COMPRA_DET_RSI_MAX=65`, el bot compra determinísticamente cuando el RSI está entre 35 y 65 (zona de oportunidad sin estar sobrecomprado).

### MACD_HIST_MIN_COMPRA

**¿Qué hace?** Valor mínimo del histograma MACD para permitir una compra determinista. Evita comprar cuando el MACD está muy negativo (caída libre).

**Ejemplo:** Con `-15.0`, si el MACD histograma es -20 (caída fuerte), no compra aunque el RSI esté en zona de oportunidad.

---

## 8. Venta — Protecciones de la IA

```ini
PNL_MIN_PARA_VENDER_IA=0.25
CONFIANZA_VENTA_FORZADA=85
PNL_MAX_PERDIDA_IA=-0.5
```

### PNL_MIN_PARA_VENDER_IA

**¿Qué hace?** P&L mínimo (en %) para que la IA pueda ejecutar una venta normal. Garantiza que la venta cubra las comisiones y genere ganancia real.

**Regla de oro:** `PNL_MIN_PARA_VENDER_IA` debe ser mayor que `COMISION_TOTAL_PCT`.

| Valor | Ganancia mínima real |
|-------|---------------------|
| `0.2%` | ~0% (solo cubre comisiones) |
| `0.25%` | ~0.05% de ganancia real |
| `0.5%` | ~0.3% de ganancia real |

### CONFIANZA_VENTA_FORZADA

**¿Qué hace?** Si la IA quiere vender con P&L menor a `PNL_MIN_PARA_VENDER_IA`, solo lo permite si la confianza es mayor a este valor. Es una "venta de emergencia" cuando la IA está muy segura de que el precio va a seguir bajando.

> **Nota:** La guardia de equilibrio sigue aplicando — si el precio está bajo el punto de equilibrio, esta venta también se bloquea.

### PNL_MAX_PERDIDA_IA

**¿Qué hace?** Límite de pérdida para la venta forzada por IA. Si el P&L es peor que este valor, la IA no puede vender (solo el stop-loss puede).

**Ejemplo:** Con `PNL_MAX_PERDIDA_IA=-0.5`, si el P&L es -0.8%, la IA no puede vender aunque tenga 90% de confianza. Solo el stop-loss (configurado en `STOP_LOSS_PCT`) puede cerrar esa posición.

---

## 9. DCA — Dollar Cost Averaging

```ini
DCA_HABILITADO=false
DCA_NIVELES=4
DCA_BAJADA_PCT=0.5
```

### ¿Qué es el DCA?

El DCA (Dollar Cost Averaging) es una estrategia que divide el capital en partes iguales y compra en diferentes niveles de precio. Si el precio baja después de la primera compra, se compra más a precio más bajo, reduciendo el precio promedio de entrada.

**Ventaja principal:** Baja el punto de equilibrio cuando el precio cae, haciendo más fácil salir con ganancia.

### DCA_HABILITADO

**¿Qué hace?** Activa o desactiva el modo DCA.

- `false` — El bot usa todo el `CAPITAL_INICIAL` en una sola compra (comportamiento clásico)
- `true` — El bot divide el capital en `DCA_NIVELES` partes y compra gradualmente

> **IMPORTANTE:** Activar solo cuando tenés el capital completo disponible. Con `CAPITAL_INICIAL=10000` y `DCA_NIVELES=4`, el bot puede comprometer hasta $10.000 en total.

### DCA_NIVELES

**¿Qué hace?** Define en cuántas partes iguales se divide el `CAPITAL_INICIAL`.

**Fórmula:** `capital_por_nivel = CAPITAL_INICIAL / DCA_NIVELES`

| `CAPITAL_INICIAL` | `DCA_NIVELES` | Capital por nivel |
|-------------------|---------------|-------------------|
| $10.000 | 2 | $5.000 |
| $10.000 | 4 | $2.500 |
| $700 | 4 | $175 |
| $700 | 5 | $140 |

### DCA_BAJADA_PCT

**¿Qué hace?** Porcentaje de caída del precio desde la última compra para activar el siguiente nivel DCA.

**Ejemplo completo con `CAPITAL_INICIAL=700`, `DCA_NIVELES=4`, `DCA_BAJADA_PCT=0.5`:**

| Evento | Precio | Capital usado | Precio promedio |
|--------|--------|---------------|-----------------|
| Compra inicial | $60.400 | $175 | $60.400 |
| Precio baja 0.5% | $60.098 | +$175 = $350 | $60.249 |
| Precio baja 0.5% | $59.797 | +$175 = $525 | $60.098 |
| Precio baja 0.5% | $59.498 | +$175 = $700 | $59.948 |
| **Total invertido** | | **$700** | **$59.948** |

El punto de equilibrio bajó de $60.521 (compra única) a $60.068 (con DCA), haciendo mucho más fácil salir con ganancia.

---

## 10. Zona Horaria y Logging

```ini
TIMEZONE=America/Argentina/Buenos_Aires
LOG_NIVEL=INFO
```

| Variable | Descripción |
|----------|-------------|
| `TIMEZONE` | Zona horaria para timestamps en logs y DB |
| `LOG_NIVEL` | Nivel de detalle de los logs: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**Niveles de log:**
- `DEBUG` — Muy detallado, para desarrollo
- `INFO` — Normal, muestra cada ciclo y decisión (recomendado)
- `WARNING` — Solo alertas importantes
- `ERROR` — Solo errores

---

## 11. Flujo de decisión del bot

En cada ciclo (cada `INTERVALO_MINUTOS` minutos), el bot sigue este orden:

```
1. Obtener precio actual e indicadores técnicos
   ↓
2. ¿Hay posición abierta?
   ├── SÍ:
   │   ├── ¿P&L <= -STOP_LOSS_PCT? → VENDER (stop-loss)
   │   ├── ¿Trailing Stop activado y precio sobre equilibrio? → VENDER
   │   ├── ¿P&L >= TAKE_PROFIT_PCT? → VENDER (take-profit)
   │   ├── ¿Ciclos >= CICLOS_MAX_EN_POSICION? → VENDER (timeout)
   │   └── Continuar a paso 4 (consultar IA)
   │
   └── NO:
       ├── ¿Cooldown post stop-loss activo? → ESPERAR
       ├── ¿Condiciones deterministas de compra? → COMPRAR
       └── Continuar a paso 4 (consultar IA)
       
3. Si DCA habilitado y hay posición:
   └── ¿Precio bajó DCA_BAJADA_PCT% y quedan niveles? → COMPRAR más
   
4. Consultar IA
   ├── IA dice COMPRAR:
   │   ├── ¿RSI sobrecomprado? → ESPERAR
   │   └── ¿Confianza >= CONFIANZA_MIN_COMPRA? → COMPRAR
   │
   └── IA dice VENDER:
       ├── ¿Precio bajo punto de equilibrio? → ESPERAR (guardia dura)
       ├── ¿Ciclos < CICLOS_MIN_EN_POSICION? → ESPERAR
       ├── ¿P&L < PNL_MIN_PARA_VENDER_IA?
       │   ├── ¿Confianza >= CONFIANZA_VENTA_FORZADA y P&L >= PNL_MAX_PERDIDA_IA? → VENDER
       │   └── Si no → ESPERAR
       └── Si P&L >= PNL_MIN_PARA_VENDER_IA → VENDER
```

---

## 12. Perfiles de configuración recomendados

### Perfil Conservador (bajo riesgo)
```ini
STOP_LOSS_PCT=2.5
TAKE_PROFIT_PCT=3.0
TRAILING_STOP_ACTIVACION_PCT=1.5
TRAILING_STOP_PROTECCION_PCT=0.5
CICLOS_MAX_EN_POSICION=40
CONFIANZA_MIN_COMPRA=65
DCA_HABILITADO=false
```

### Perfil Moderado (recomendado para empezar)
```ini
STOP_LOSS_PCT=1.5
TAKE_PROFIT_PCT=5.0
TRAILING_STOP_ACTIVACION_PCT=2.0
TRAILING_STOP_PROTECCION_PCT=0.5
CICLOS_MAX_EN_POSICION=20
CONFIANZA_MIN_COMPRA=55
DCA_HABILITADO=false
```

### Perfil Agresivo (mayor rotación de capital)
```ini
STOP_LOSS_PCT=1.0
TAKE_PROFIT_PCT=2.0
TRAILING_STOP_ACTIVACION_PCT=1.0
TRAILING_STOP_PROTECCION_PCT=0.3
CICLOS_MAX_EN_POSICION=10
CONFIANZA_MIN_COMPRA=50
DCA_HABILITADO=true
DCA_NIVELES=4
DCA_BAJADA_PCT=0.3
```

### Perfil DCA (mercado lateral/bajista)
```ini
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=3.0
CICLOS_MAX_EN_POSICION=30
DCA_HABILITADO=true
DCA_NIVELES=5
DCA_BAJADA_PCT=0.5
```

---

*Documento generado automáticamente — CryptoIA Bot v3*
