#!/usr/bin/env bash
# Cross-compilation pour Voice Control sur multi-plateformes
# Support: x86_64, aarch64, armv7l, ESP32

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
PROJECT_NAME="voice-control"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Dépendances cross-compilation
install_cross_deps() {
    info "Installation dépendances cross-compilation..."

    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y \
            build-essential \
            crossbuild-essential-arm64 \
            crossbuild-essential-armhf \
            gcc-arm-linux-gnueabihf \
            gcc-aarch64-linux-gnu \
            python3-pip \
            python3-venv \
            git \
            cmake \
            espeak \
            portaudio19-dev \
            libasound2-dev \
            ffmpeg
    fi
}

# Build pour x86_64
build_x86_64() {
    local output="${BUILD_DIR}/x86_64"

    info "Build x86_64 (PC standard)..."

    mkdir -p "${output}"
    cd "${output}"

    python3 -m venv venv
    source venv/bin/activate

    pip install --upgrade pip
    pip install -r "${SCRIPT_DIR}/requirements.txt"

    # Optionnel: Whisper
    pip install openai-whisper torch

    # Gèle les dépendances
    pip freeze > venv_requirements.txt

    # Crée un exécutable portable
    if command -v pyinstaller &> /dev/null || pip install pyinstaller; then
        pip install pyinstaller
        pyinstaller "${SCRIPT_DIR}/voice_control.py" \
            --onefile \
            --name "${PROJECT_NAME}" \
            --add-data "${SCRIPT_DIR}/plugins:plugins" \
            --hidden-import=whisper \
            --hidden-import=sounddevice \
            --console
    fi

    info "Build x86_64 terminé: ${output}"
    ls -la "${output}"/*.elf 2>/dev/null || ls -la "${output}"/dist/ 2>/dev/null || echo "Vérifiez manuellement"
}

# Build pour ARM64 (RK3528, OrangePi, etc.)
build_aarch64() {
    local output="${BUILD_DIR}/aarch64"

    info "Build ARM64 (RK3528, RK3588, OrangePi 5)..."

    mkdir -p "${output}"
    cd "${output}"

    # Environnement Python ARM64 natif ou cross-compilé
    python3 -m venv venv
    source venv/bin/activate

    pip install --upgrade pip
    # Versions ARM optimisées
    pip install \
        numpy \
        sounddevice \
        requests \
        yt-dlp \
        gtts

    # Whisper léger sur ARM
    pip install openai-whisper

    # Gèle les dépendances
    pip freeze > venv_requirements.txt

    info "Build ARM64 terminé: ${output}/venv"
    info "Copiez ce dossier sur votre RK3528:"
    info "  rsync -avP ${output}/ vospace@192.168.1.X:/home/voice-control/"
}

# Build pour ARM32 (Raspberry Pi)
build_armv7l() {
    local output="${BUILD_DIR}/armv7l"

    info "Build ARM32 (Raspberry Pi 3/4)..."

    mkdir -p "${output}"
    cd "${output}"

    python3 -m venv venv
    source venv/bin/activate

    pip install --upgrade pip
    pip install \
        numpy \
        sounddevice \
        requests \
        yt-dlp

    info "Build ARM32 terminé: ${output}/venv"
}

# Build Docker multi-plateforme
build_docker() {
    info "Build Docker images..."

    # AMD64
    info "  → AMD64..."
    docker build -f "${SCRIPT_DIR}/Dockerfile.amd64" \
        -t "${PROJECT_NAME}:amd64" \
        "${SCRIPT_DIR}"

    # ARM64
    info "  → ARM64..."
    docker build -f "${SCRIPT_DIR}/Dockerfile.arm64" \
        -t "${PROJECT_NAME}:arm64" \
        --platform linux/arm64 \
        "${SCRIPT_DIR}"
}

# Build ESP32 (compilation séparée)
build_esp32() {
    local output="${BUILD_DIR}/esp32"

    info "Build ESP32 Voice Client..."

    mkdir -p "${output}/voice_client"

    cat > "${output}/voice_client/voice_client.ino" << 'EOF'
// Voice Client ESP32 - Client léger pour voice-control
// Utilise l'API HTTP du serveur principal

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* SERVER = "http://VOTRE_SERVEUR:5000";

#define LED_PIN 2
#define BTN_PIN 0

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BTN_PIN, INPUT_PULLUP);

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    }
    digitalWrite(LED_PIN, HIGH);
    Serial.println("Connecté !");
}

void loop() {
    // Bouton pour envoyer commande
    if (digitalRead(BTN_PIN) == LOW) {
        sendCommand("toggle");
        delay(500);
    }

    delay(100);
}

void sendCommand(const char* cmd) {
    HTTPClient http;
    char url[200];
    sprintf(url, "%s/api/command?cmd=%s", SERVER, cmd);

    http.begin(url);
    int code = http.GET();
    if (code == 200) {
        digitalWrite(LED_PIN, LOW);
        delay(100);
        digitalWrite(LED_PIN, HIGH);
    }
    http.end();
}
EOF

    info "ESP32 firmware prêt: ${output}/voice_client/"
    info "Compilez avec PlatformIO ou Arduino IDE"
}

# Installation sur RK3528 via SSH
install_rk3528() {
    local ip=${1:-"192.168.1.100"}
    local user=${2:-"root"}

    info "Installation sur RK3528 (${user}@${ip})..."

    rsync -avP --exclude='venv' --exclude='.git' \
        "${SCRIPT_DIR}/" \
        "${user}@${ip}:~/voice-control/"

    ssh "${user}@${ip}" "cd ~/voice-control && ./setup_rk3528.sh --with-whisper"
}

# Statut
status() {
    echo ""
    echo "=== Voice Control - Builds Disponibles ==="
    echo ""
    echo "Plateformes:"
    echo "  x86_64   - PC standard (Intel/AMD 64-bit)"
    echo "  aarch64  - RK3528, RK3588, OrangePi 5, RockPi"
    echo "  armv7l   - Raspberry Pi 3/4, OrangePi"
    echo "  esp32    - Microcontrôleur ESP32"
    echo "  docker   - Conteneurs multi-plateforme"
    echo ""
    echo "Dossiers de build:"
    ls -la "${BUILD_DIR}" 2>/dev/null || echo "  Aucun build effectué"
    echo ""
}

# Menu principal
usage() {
    echo ""
    echo "Voice Control - Cross-Compilation"
    echo ""
    echo "Usage: $0 [commande]"
    echo ""
    echo "Commandes:"
    echo "  deps          Installe les dépendances"
    echo "  x86_64        Build pour PC standard"
    echo "  aarch64       Build pour ARM64 (RK3528)"
    echo "  armv7l        Build pour ARM32 (RPi)"
    echo "  esp32         Build firmware ESP32"
    echo "  docker        Build images Docker"
    echo "  install       Installe sur RK3528 (ip user)"
    echo "  all           Build tout"
    echo "  status        Affiche le statut"
    echo ""
    echo "Exemples:"
    echo "  $0 deps"
    echo "  $0 x86_64"
    echo "  $0 install 192.168.1.100 root"
    echo ""
}

# Point d'entrée
main() {
    mkdir -p "${BUILD_DIR}"

    case "${1:-}" in
        deps)       install_cross_deps ;;
        x86_64)     build_x86_64 ;;
        aarch64)    build_aarch64 ;;
        armv7l)     build_armv7l ;;
        esp32)      build_esp32 ;;
        docker)     build_docker ;;
        install)    install_rk3528 "${2:-192.168.1.100}" "${3:-root}" ;;
        all)        build_x86_64 && build_aarch64 && build_armv7l ;;
        status)     status ;;
        *)          usage ;;
    esac
}

main "$@"