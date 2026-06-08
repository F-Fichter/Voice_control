#!/usr/bin/env bash
# Setup IR (infrarouge) pour voice-control

set -e

echo "=== Voice Control - Setup IR ==="

# LIRC (contrôle infrarouge Linux)
setup_lirc() {
    echo "[1/4] Installation LIRC..."
    sudo apt-get install -y lirc lirc-x

    echo "[2/4] Configuration..."
    # Activation du module lirc
    echo "options lirc_rpi gpio_in_pin=23" | sudo tee /etc/modprobe.d/lirc.conf

    echo "[3/4] Démarrage service..."
    sudo systemctl enable lircd
    sudo systemctl start lircd

    echo "[4/4] Configuration terminée"
    echo "Pour enregistrer une télécommande: irrecord -f -d /dev/lirc0 ~/myremote.conf"
}

# Broadlink RM
setup_broadlink() {
    echo "Installation python-broadlink..."
    pip install broadlink
    echo "Lancez 'python -m broadlink.cli discover' pour trouver vos appareils"
}

# Flirc
setup_flirc() {
    echo "Installation Flirc..."
    wget -qO - https://flirc.tv/FLIRClamAV.asc | sudo apt-key add -
    echo "deb https://flirc.tv/linux/debian bullseye firmware" | sudo tee /etc/apt/sources.list.d/flirc.list
    sudo apt-get update
    sudo apt-get install -y flirc
}

menu() {
    echo ""
    echo "Quel système IR utilisez-vous?"
    echo "1) LIRC (Raspberry Pi / Linux)"
    echo "2) Broadlink RM"
    echo "3) Flirc"
    echo "4) Skip (pas d'IR)"
    read -p "Choix [1-4]: " choice

    case $choice in
        1) setup_lirc ;;
        2) setup_broadlink ;;
        3) setup_flirc ;;
        *) echo "Skipped" ;;
    esac
}

menu

echo ""
echo "=== IR Setup Terminé ==="
echo "Mettez à jour devices.json avec vos codes IR"