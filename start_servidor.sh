#!/bin/bash
# ==============================================================================
# start_servidor.sh — Inicia el motor de trading y la API en el servidor
#
# Uso:
#   bash start_servidor.sh          → inicia ambos procesos en background
#   bash start_servidor.sh bot      → solo el motor de trading
#   bash start_servidor.sh api      → solo la API
#   bash start_servidor.sh stop     → detiene ambos procesos
#   bash start_servidor.sh status   → muestra el estado de ambos procesos
#   bash start_servidor.sh logs     → muestra los últimos logs
# ==============================================================================

BOT_LOG="logs/motor_real.log"
API_LOG="logs/api.log"
BOT_PID="logs/motor_real.pid"
API_PID="logs/api.pid"

mkdir -p logs

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          🤖 CryptoIA — Control del Servidor          ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

start_bot() {
    if [ -f "$BOT_PID" ] && kill -0 $(cat "$BOT_PID") 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Motor de trading ya está corriendo (PID: $(cat $BOT_PID))${NC}"
        return
    fi
    echo -e "${GREEN}🚀 Iniciando motor de trading...${NC}"
    nohup python3 src/trading/motor_real.py >> "$BOT_LOG" 2>&1 &
    echo $! > "$BOT_PID"
    echo -e "${GREEN}✅ Motor iniciado (PID: $!, log: $BOT_LOG)${NC}"
}

start_api() {
    if [ -f "$API_PID" ] && kill -0 $(cat "$API_PID") 2>/dev/null; then
        echo -e "${YELLOW}⚠️  API ya está corriendo (PID: $(cat $API_PID))${NC}"
        return
    fi
    echo -e "${GREEN}🚀 Iniciando API FastAPI...${NC}"
    nohup python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 >> "$API_LOG" 2>&1 &
    echo $! > "$API_PID"
    echo -e "${GREEN}✅ API iniciada (PID: $!, log: $API_LOG)${NC}"
    echo -e "${CYAN}   Docs: http://192.168.1.8:8000/docs${NC}"
}

stop_bot() {
    if [ -f "$BOT_PID" ]; then
        PID=$(cat "$BOT_PID")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo -e "${RED}🛑 Motor de trading detenido (PID: $PID)${NC}"
        else
            echo -e "${YELLOW}⚠️  Motor no estaba corriendo${NC}"
        fi
        rm -f "$BOT_PID"
    else
        echo -e "${YELLOW}⚠️  No se encontró PID del motor${NC}"
    fi
}

stop_api() {
    if [ -f "$API_PID" ]; then
        PID=$(cat "$API_PID")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo -e "${RED}🛑 API detenida (PID: $PID)${NC}"
        else
            echo -e "${YELLOW}⚠️  API no estaba corriendo${NC}"
        fi
        rm -f "$API_PID"
    else
        echo -e "${YELLOW}⚠️  No se encontró PID de la API${NC}"
    fi
}

show_status() {
    echo -e "${CYAN}=== Estado de los procesos ===${NC}"

    # Motor de trading
    if [ -f "$BOT_PID" ] && kill -0 $(cat "$BOT_PID") 2>/dev/null; then
        echo -e "  Motor de trading: ${GREEN}✅ CORRIENDO${NC} (PID: $(cat $BOT_PID))"
    else
        echo -e "  Motor de trading: ${RED}❌ DETENIDO${NC}"
    fi

    # API
    if [ -f "$API_PID" ] && kill -0 $(cat "$API_PID") 2>/dev/null; then
        echo -e "  API FastAPI:      ${GREEN}✅ CORRIENDO${NC} (PID: $(cat $API_PID))"
        echo -e "  Docs:             ${CYAN}http://192.168.1.8:8000/docs${NC}"
    else
        echo -e "  API FastAPI:      ${RED}❌ DETENIDA${NC}"
    fi

    # Contenedores Ollama
    echo ""
    echo -e "${CYAN}=== Contenedores Ollama ===${NC}"
    for c in ollama_tecnico ollama_fundamental ollama_riesgo ollama_soporte; do
        STATUS=$(docker inspect --format='{{.State.Status}}' "$c" 2>/dev/null || echo "no encontrado")
        if [ "$STATUS" = "running" ]; then
            echo -e "  $c: ${GREEN}✅ running${NC}"
        else
            echo -e "  $c: ${RED}❌ $STATUS${NC}"
        fi
    done
}

show_logs() {
    echo -e "${CYAN}=== Últimas 30 líneas del motor ===${NC}"
    tail -30 "$BOT_LOG" 2>/dev/null || echo "Sin logs del motor"
    echo ""
    echo -e "${CYAN}=== Últimas 10 líneas de la API ===${NC}"
    tail -10 "$API_LOG" 2>/dev/null || echo "Sin logs de la API"
}

# ==============================================================================
# MAIN
# ==============================================================================
print_banner

case "${1:-all}" in
    "bot")
        start_bot
        ;;
    "api")
        start_api
        ;;
    "stop")
        stop_bot
        stop_api
        ;;
    "stop-bot")
        stop_bot
        ;;
    "stop-api")
        stop_api
        ;;
    "status")
        show_status
        ;;
    "logs")
        show_logs
        ;;
    "restart")
        stop_bot
        stop_api
        sleep 2
        start_bot
        sleep 1
        start_api
        ;;
    "all"|*)
        start_bot
        sleep 2
        start_api
        echo ""
        show_status
        ;;
esac
