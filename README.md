# 🤖 CryptoIA — Bot de Trading con IAs Locales

> Sistema multi-agente de trading de criptomonedas que utiliza modelos de lenguaje (LLMs) corriendo localmente en un servidor GPU para analizar el mercado y tomar decisiones de compra/venta.

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    SERVIDOR DE IAs (192.168.1.8)            │
│                                                             │
│  Puerto 11431 → GPU 0 → 🔵 Analista Técnico                │
│                          (RSI, MACD, Bollinger, EMA)        │
│                                                             │
│  Puerto 11432 → GPU 1 → 🟡 Analista Fundamental            │
│                          (Noticias, Sentimiento)            │
│                                                             │
│  Puerto 11433 → GPU 2 → 🔴 Gestor de Riesgos              │
│                          (Decisión final, SL/TP)            │
└─────────────────────────────────────────────────────────────┘
         ↕ HTTP REST (Ollama API)
┌─────────────────────────────────────────────────────────────┐
│                    BOT (Python)                             │
│                                                             │
│  src/mercado/     → Binance (OHLCV, indicadores técnicos)  │
│  src/noticias/    → RSS feeds (CoinTelegraph, CoinDesk)    │
│  src/agentes/     → Clientes Ollama + normalizador         │
│  src/trading/     → Motor de trading + PostgreSQL ORM      │
└─────────────────────────────────────────────────────────────┘
         ↕ SQLAlchemy
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL 14 (192.168.1.8:5432)               │
│                                                             │
│  ciclos_observacion  │  noticias_cache                     │
│  billetera           │  operaciones                        │
└─────────────────────────────────────────────────────────────┘
```

---

## ✨ Características

- **3 agentes IA especializados** corriendo en GPUs locales (Ollama)
- **Análisis técnico completo**: RSI, MACD, Bandas de Bollinger, EMA 9/21, Volumen relativo
- **Análisis fundamental**: 4 fuentes RSS en tiempo real (CoinTelegraph ES/EN, CoinDesk, Bitcoin Magazine)
- **Gestión de riesgo**: Stop-Loss y Take-Profit dinámicos configurables
- **Persistencia en PostgreSQL**: historial completo de ciclos, noticias, billetera y operaciones
- **Modo observación 24/7**: registra decisiones hipotéticas sin ejecutar operaciones reales
- **Billetera simulada**: seguimiento de rendimiento hipotético con P&L

---

## 📋 Requisitos

### Software
- Python 3.10+
- PostgreSQL 14+ (accesible en red)
- [Ollama](https://ollama.ai) corriendo en el servidor con los modelos cargados

### Modelos Ollama requeridos
```bash
# En el servidor 192.168.1.8
ollama pull qwen2.5:7b   # GPU 0 — Analista Técnico
ollama pull qwen2.5:3b   # GPU 1 — Analista Fundamental
ollama pull qwen2.5:3b   # GPU 2 — Gestor de Riesgos
```

---

## 🚀 Instalación

### Opción A — Script automático (Linux/Mac)
```bash
git clone https://github.com/TU_USUARIO/CryptoIa.git
cd CryptoIa
chmod +x deploy.sh
./deploy.sh
```

### Opción B — Manual
```bash
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/CryptoIa.git
cd CryptoIa

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
nano .env   # Editar con tus valores
```

### Configuración del `.env`
```env
# Servidor de IAs (Ollama)
SERVIDOR_IA=192.168.1.8
PUERTO_GPU0=11431
PUERTO_GPU1=11432
PUERTO_GPU2=11433
MODELO_GPU0=qwen2.5:7b
MODELO_GPU1=qwen2.5:3b
MODELO_GPU2=qwen2.5:3b

# Base de datos PostgreSQL
DB_SERVER=192.168.1.8
DB_PORT=5432
DB_DATABASE=CryptoTrade
DB_USER=Crypto
DB_PASSWORD=TU_PASSWORD

# Trading
EXCHANGE=binance
SIMBOLO=BTC/USDT
TEMPORALIDAD=15m
CAPITAL_INICIAL=10000
STOP_LOSS_PCT=2.5
TAKE_PROFIT_PCT=5.0
```

---

## 🧪 Tests de verificación

```bash
# 1. Verificar conectividad con el servidor de IAs
python tests/test_conexion.py

# 2. Verificar datos de mercado (Binance)
python tests/test_mercado_real.py

# 3. Verificar base de datos PostgreSQL
python tests/test_base_datos.py

# 4. Test completo del comité de IAs
python tests/test_comite_real.py
```

---

## ▶️ Ejecución

### Modo observación (recomendado para empezar)
```bash
# Ejecuta el bot en modo observación — NO realiza operaciones reales
# Registra decisiones cada 15 minutos en PostgreSQL + CSV
python tests/test_observacion.py
```

### En segundo plano (Linux)
```bash
# Con nohup
nohup python tests/test_observacion.py > logs/bot.log 2>&1 &
echo $! > logs/bot.pid

# Con screen (podés reconectarte)
screen -S cryptobot
python tests/test_observacion.py
# Ctrl+A, D para desconectarte
# screen -r cryptobot para volver

# Con systemd (se reinicia automáticamente)
sudo cp deploy/cryptobot.service /etc/systemd/system/
sudo systemctl enable cryptobot
sudo systemctl start cryptobot
```

---

## 📊 Consultar evoluciones en PostgreSQL

```sql
-- Últimos 20 ciclos
SELECT ciclo, timestamp, precio_btc, rsi, decision_final, tiempo_ciclo_seg
FROM ciclos_observacion
ORDER BY id DESC LIMIT 20;

-- Distribución de decisiones
SELECT decision_final, COUNT(*) as cantidad, AVG(rsi) as rsi_promedio
FROM ciclos_observacion
GROUP BY decision_final;

-- Cuándo el comité decidió COMPRA
SELECT ciclo, timestamp, precio_btc, rsi, rsi_zona, macd_cruce
FROM ciclos_observacion
WHERE decision_final = 'COMPRA'
ORDER BY timestamp DESC;

-- Evolución del precio en el tiempo
SELECT timestamp, precio_btc, rsi, decision_final
FROM ciclos_observacion
ORDER BY timestamp;

-- Estado de la billetera hipotética
SELECT timestamp, usdt, btc, valor_total_usdt, ganancia_total, evento
FROM billetera
ORDER BY id DESC LIMIT 20;
```

---

## 📁 Estructura del Proyecto

```
CryptoIa/
├── config.py                    # Configuración centralizada (lee .env)
├── run_bot.py                   # Punto de entrada principal
├── requirements.txt             # Dependencias Python
├── deploy.sh                    # Script de instalación para Linux
├── hoja_de_ruta.md              # Plan de desarrollo detallado
│
├── src/
│   ├── mercado/
│   │   └── binance_client.py    # Datos OHLCV + RSI/MACD/Bollinger/EMA
│   ├── noticias/
│   │   └── feed_manager.py      # RSS feeds (CoinTelegraph, CoinDesk, etc.)
│   ├── agentes/
│   │   └── normalizador.py      # Normaliza respuestas de las IAs
│   └── trading/
│       └── base_datos.py        # ORM SQLAlchemy para PostgreSQL
│
├── tests/
│   ├── test_conexion.py         # Verifica conectividad con el servidor
│   ├── test_mercado_real.py     # Test de datos de Binance
│   ├── test_base_datos.py       # Test de PostgreSQL
│   ├── test_comite_real.py      # Test del comité completo
│   └── test_observacion.py      # Modo observación 24/7
│
├── logs/                        # Logs y CSV de respaldo (no en git)
└── data/                        # Datos locales (no en git)
```

---

## 🗺️ Hoja de Ruta

| Fase | Descripción | Estado |
|------|-------------|--------|
| FASE 0 | Configuración del entorno | ✅ Completada |
| FASE 1 | Módulo de mercado (RSI, MACD, Bollinger) | ✅ Completada |
| FASE 2 | Módulo de noticias (4 fuentes RSS) | 🔄 Parcial |
| FASE 3 | Comité de IAs refactorizado | 🔄 Parcial |
| FASE 4 | Motor de trading + PostgreSQL | 🔄 Parcial |
| FASE 5 | Dashboard de monitoreo | ⬜ Pendiente |
| FASE 6 | Mejoras avanzadas (backtesting, multi-activo) | 🔮 Futuro |

Ver [hoja_de_ruta.md](hoja_de_ruta.md) para el detalle completo.

---

## ⚠️ Advertencias

- Este bot opera en **modo simulación** — no ejecuta operaciones reales hasta que se configure explícitamente
- **NUNCA** subas el archivo `.env` al repositorio
- Los modelos de Ollama deben estar **precargados** en el servidor antes de iniciar
- Respetar los rate limits de Binance (máximo 1200 requests/minuto)

---

## 📄 Licencia

Uso personal. No distribuir sin autorización.

---

*Desarrollado con Python 3.10 + Ollama + PostgreSQL*
