#!/bin/bash
# Script de contrôle vocal - Orange Pi 2W (Allwinner H618, 4Go RAM, ARM64)
# Installation optimisée pour 4 Go de RAM

set -e

echo "=== Voice Control - Orange Pi 2W (4Go RAM) ==="
echo "Chipset: Allwinner H618 (ARM64)"
echo ""

# Vérifier architecture
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" ]]; then
    echo "WARNING: Architecture détectée: $ARCH (aarch64 recommandé)"
    echo "Ce script est optimisé pour Orange Pi 2W (ARM64)"
    read -p "Continuer ? (o/N): " confirm
    if [[ ! "$confirm" =~ ^[Oo]$ ]]; then
        exit 1
    fi
fi

# 1. Dépendances système
echo "[1/7] Installation dépendances système..."
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv python3-dev \
    python3-numpy \
    portaudio19-dev \
    libasound2-dev \
    libsndfile1 \
    ffmpeg \
    libopenjp2-7-dev \
    build-essential \
    git curl wget \
    espeak espeak-ng \
    mpv mplayer mpg123 \
    alsa-utils

# Config ALSA (si micro USB)
echo ""
echo "Configuration audio..."
arecord -l 2>/dev/null || echo "Aucun micro détecté (brancher un micro USB)"

# 2. Environnement virtuel
echo ""
echo "[2/7] Création environnement..."
python3 -m venv venv
source venv/bin/activate

# 3. Dépendances Python core
echo "[3/7] Installation Python core..."
pip install --upgrade pip
pip install numpy sounddevice requests

# 4. Audio
echo "[4/7] Installation audio..."
pip install pyaudio pygame

# 5. TTS
echo "[5/7] Installation TTS..."
pip install gtts

# 6. Whisper (modèle tiny pour 4Go RAM)
echo "[6/7] Installation Whisper..."
if [[ "$1" == "--with-whisper" ]]; then
    echo "Installation Whisper + Torch CPU (optimisé pour 4Go RAM)..."
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install openai-whisper
    echo "Modèle 'tiny' sera utilisé par défaut (~1Go RAM max)"
else
    echo "Whisper non installé (utiliser --with-whisper pour l'activer)"
fi

# 7. Configuration
echo ""
echo "[7/7] Configuration..."
if [ ! -f config.json ]; then
    cp config.json.example config.json
    echo "Configuration créée: config.json"
fi

echo ""
echo "=== Installation terminée ==="
echo ""
echo "Activation: source venv/bin/activate"
echo "Test:       python voice_control.py --mode test"
echo "Vocal:      python voice_control.py --mode interactive"
echo ""
echo "Note: Le modèle Whisper 'tiny' utilise ~1Go RAM"
echo "Pour plus de précision: éditer config.json -> whisper.model = 'base' (~2Go RAM)"
