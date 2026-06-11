#!/bin/bash
# ==============================================================================
# deploy.sh — Script de instalación de CryptoIA en Linux
# Uso: chmod +x deploy.sh && ./deploy.sh
# ==============================================================================

set -e  # Detener si hay algún error

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # Sin color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║         🤖 CryptoIA — Deploy en Linux               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ==============================================================================
# PASO 1: Verificar Python
# ==============================================================================
echo -e "${YELLOW}[1/6] Verificando Python 3.10+...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 no encontrado. Instalando...${NC}"
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip python3-venv
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✅ Python $PYTHON_VERSION encontrado${NC}"

# ==============================================================================
# PASO 2: Crear entorno virtual
# ==============================================================================
echo -e "${YELLOW}[2/6] Creando entorno virtual...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Entorno virtual creado${NC}"
else
    echo -e "${GREEN}✅ Entorno virtual ya existe${NC}"
fi

# Activar entorno virtual
source venv/bin/activate

# ==============================================================================
# PASO 3: Instalar dependencias
# ==============================================================================
echo -e "${YELLOW}[3/6] Instalando dependencias...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}✅ Dependencias instaladas${NC}"

# ==============================================================================
# PASO 4: Configurar .env
# ==============================================================================
echo -e "${YELLOW}[4/6] Configurando variables de entorno...${NC}"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠️  Archivo .env creado desde .env.example${NC}"
        echo -e "${YELLOW}   ➡️  IMPORTANTE: Editá el archivo .env con tus valores reales:${NC}"
        echo -e "${YELLOW}   nano .env${NC}"
    else
        echo -e "${RED}❌ No se encontró .env.example. Creá el archivo .env manualmente.${NC}"
        echo -e "${YELLOW}   Ver README.md para el contenido del .env${NC}"
    fi
else
    echo -e "${GREEN}✅ Archivo .env ya existe${NC}"
fi

# ==============================================================================
# PASO 5: Crear carpetas necesarias
# ==============================================================================
echo -e "${YELLOW}[5/6] Creando carpetas...${NC}"
mkdir -p logs data
echo -e "${GREEN}✅ Carpetas logs/ y data/ listas${NC}"

# ==============================================================================
# PASO 6: Test de conectividad
# ==============================================================================
echo -e "${YELLOW}[6/6] Verificando conectividad...${NC}"
if [ -f ".env" ]; then
    python3 tests/test_conexion.py 2>/dev/null && \
        echo -e "${GREEN}✅ Conectividad verificada${NC}" || \
        echo -e "${YELLOW}⚠️  Test de conectividad falló — verificá el .env y la red${NC}"
else
    echo -e "${YELLOW}⚠️  Saltando test de conectividad (falta .env)${NC}"
fi

# ==============================================================================
# RESUMEN FINAL
# ==============================================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              ✅ Deploy completado                   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Para ejecutar el bot en modo observación:${NC}"
echo -e "  ${CYAN}source venv/bin/activate${NC}"
echo -e "  ${CYAN}python tests/test_observacion.py${NC}"
echo ""
echo -e "${GREEN}Para ejecutar en segundo plano:${NC}"
echo -e "  ${CYAN}nohup python tests/test_observacion.py > logs/bot.log 2>&1 &${NC}"
echo -e "  ${CYAN}echo \$! > logs/bot.pid${NC}"
echo ""
echo -e "${GREEN}Para instalar como servicio systemd:${NC}"
echo -e "  ${CYAN}sudo cp deploy/cryptobot.service /etc/systemd/system/${NC}"
echo -e "  ${CYAN}sudo systemctl enable cryptobot && sudo systemctl start cryptobot${NC}"
echo ""
echo -e "${YELLOW}📖 Ver README.md para más información${NC}"
