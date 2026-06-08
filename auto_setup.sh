#!/bin/bash
# Voice Control + SMTP Auto-Setup
# Configure automatiquement DNS dynamique + redirections box

set -e

echo "========================================"
echo "  Voice Control + SMTP Auto-Setup"
echo "  Domain: fichter.eu"
echo "========================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DOMAIN="fichter.eu"
SERVER_IP=""  # À remplir

# Menu
menu() {
    echo ""
    echo "=== Menu ==="
    echo "1) Configuration DDNS (IP dynamique)"
    echo "2) Configuration Box (UPnP)"
    echo "3) Installation SMTP complète"
    echo "4) Installation Voice Control"
    echo "5) Installation Tout-en-Un"
    echo "0) Quitter"
    echo ""
    read -p "Choix: " choice

    case $choice in
        1) setup_ddns ;;
        2) setup_upnp ;;
        3) setup_smtp ;;
        4) setup_voice ;;
        5) setup_all ;;
        0) exit 0 ;;
        *) menu ;;
    esac
}

# 1. DDNS Setup
setup_ddns() {
    echo -e "${BLUE}[1/3] Configuration DDNS${NC}"

    echo ""
    echo "Service DNS dynamique ?"
    echo "1) DuckDNS (gratuit)"
    echo "2) No-IP (gratuit)"
    echo "3) Cloudflare (API requise)"
    echo "4) FreeDNS (gratuit)"
    read -p "Choix [1]: " dns_choice
    dns_choice=${dns_choice:-1}

    echo ""
    echo "Domaines (ex: ${DOMAIN}):"
    read -p "Domaines: " domains

    echo ""
    echo "Token/Clé API:"
    read -s -p "Token: " token
    echo ""

    # Sauvegarde config
    cat > "${SCRIPT_DIR}/ddns.conf" << EOF
{
    "provider": "$(echo $dns_choice | sed 's/1/duckdns/;s/2/noip/;s/3/cloudflare/;s/4/afraid/')",
    "domains": "${domains}",
    "token": "${token}",
    "check_interval": 300
}
EOF

    echo -e "${GREEN}✓ Configuration DDNS sauvegardée${NC}"

    # Test
    echo ""
    echo "Test..."
    python3 "${SCRIPT_DIR}/ddns_updater.py" --config "${SCRIPT_DIR}/ddns.conf" --once --force
}

# 2. UPnP Setup
setup_upnp() {
    echo -e "${BLUE}[2/3] Configuration Box (UPnP)${NC}"

    # Vérifie Python
    if ! command -v python3 &> /dev/null; then
        echo "Python3 requis"
        return 1
    fi

    echo ""
    echo "Recherche de la box..."
    python3 "${SCRIPT_DIR}/port_forwarder.py"

    echo ""
    read -p "Configurer les ports SMTP + Voice Control ? (o/n): " confirm
    if [[ "$confirm" =~ ^[Oo]$ ]]; then
        python3 "${SCRIPT_DIR}/port_forwarder.py" --setup
    fi
}

# 3. SMTP Setup
setup_smtp() {
    echo -e "${BLUE}[3/4] Installation SMTP${NC}"

    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW} sudo requis pour SMTP${NC}"
        echo "Lancez: sudo ./auto_setup.sh"
        return 1
    fi

    echo "Exécution setup_smtp.sh..."
    bash "${SCRIPT_DIR}/setup_smtp.sh"
}

# 4. Voice Control Setup
setup_voice() {
    echo -e "${BLUE}[4/4] Installation Voice Control${NC}"

    arch=$(uname -m)
    echo "Architecture: $arch"

    if [[ "$arch" == "x86_64" ]]; then
        "${SCRIPT_DIR}/setup.sh"
    elif [[ "$arch" == "aarch64" || "$arch" == "armv7l" ]]; then
        "${SCRIPT_DIR}/setup_rk3528.sh"
    else
        echo "Architecture non supportée pour installation auto"
    fi
}

# 5. Tout-en-Un
setup_all() {
    echo -e "${BLUE}=== Installation Complète ===${NC}"

    read -p "Type de machine (1=PC, 2=RK3528/ARM): " machine
    machine=${machine:-1}

    # 1. Mise à jour système
    echo -e "${YELLOW}[1/5] Mise à jour système${NC}"
    if command -v apt-get &> /dev/null; then
        sudo apt update && sudo apt upgrade -y
    fi

    # 2. Dépendances communes
    echo -e "${YELLOW}[2/5] Dépendances${NC}"
    sudo apt install -y python3 python3-pip python3-venv \
        portaudio19-dev libasound2-dev ffmpeg git

    # 3. Voice Control
    echo -e "${YELLOW}[3/5] Voice Control${NC}"
    cd "${SCRIPT_DIR}"
    ./setup.sh

    # 4. DDNS
    echo -e "${YELLOW}[4/5] DDNS${NC}"
    setup_ddns

    # 5. Guide final
    echo ""
    echo -e "${GREEN}=== Installation Terminée ===${NC}"
    echo ""
    echo "Étapes restantes:"
    echo "1. Configurez votre registrar DNS:"
    echo "   - MX: mail.${DOMAIN}"
    echo "   - A: [votre IP]"
    echo ""
    echo "2. Activez UPnP sur votre box:"
    echo "   python3 ${SCRIPT_DIR}/port_forwarder.py --setup"
    echo ""
    echo "3. Installez SMTP (sudo):"
    echo "   sudo bash ${SCRIPT_DIR}/setup_smtp.sh"
    echo ""
    echo "4. Démarrez Voice Control:"
    echo "   cd ${SCRIPT_DIR} && source venv/bin/activate"
    echo "   python3 voice_control.py --mode interactive"
}

# Démarrage auto DDNS
install_ddns_service() {
    echo "Installation service DDNS..."

    cat > /etc/systemd/system/ddns.service << 'EOF'
[Unit]
Description=Dynamic DNS Updater
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /home/fran/OPENCODE/voice_control/ddns_updater.py --config /home/fran/OPENCODE/voice_control/ddns.conf --daemon
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable ddns
    sudo systemctl start ddns

    echo -e "${GREEN}✓ Service DDNS activé${NC}"
}

# Démarrage auto port forwarder
install_upnp_service() {
    echo "Installation service UPnP..."

    cat > /etc/systemd/system/upnp-forwarder.service << 'EOF'
[Unit]
Description=Box Port Forwarder
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/fran/OPENCODE/voice_control/port_forwarder.py --setup
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    # Timer pour vérifier périodiquement
    cat > /etc/systemd/system/upnp-forwarder.timer << 'EOF'
[Unit]
Description=Port Forwarder - runs hourly
Requires=upnp-forwarder.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable upnp-forwarder.timer
    sudo systemctl start upnp-forwarder.timer

    echo -e "${GREEN}✓ UPnP Forwarder programmé${NC}"
}

# Lance le menu si called directement
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    menu
fi