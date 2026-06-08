#!/bin/bash
# Script d'installation pour voice-control (x86_64)
# Toutes les dépendances sont incluses

set -e

echo "=== Voice Control - Installation Complete ==="

# 1. Dépendances système
echo "[1/6] Installation dépendances système..."

if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y \
        python3 python3-pip python3-venv \
        portaudio19-dev libasound2-dev libopenjp2-7-dev \
        ffmpeg mpv mplayer \
        espeak espeak-ng \
        git curl wget
elif command -v pacman &> /dev/null; then
    sudo pacman -S python python-pip portaudio ffmpeg mpv mplayer espeakup git
elif command -v dnf &> /dev/null; then
    sudo dnf install python3 python3-pip portaudio-devel ffmpeg mpv espeakup git
fi

# 2. Environnement virtuel
echo "[2/6] Création environnement virtuel..."
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate

# 3. Dépendances Python core
echo "[3/6] Installation dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. TTS
echo "[4/6] Installation TTS..."
pip install gtts

# 5. Audio players
echo "[5/6] Installation players audio..."
if ! command -v mpv &> /dev/null; then
    sudo apt-get install -y mpv mplayer mpg123 2>/dev/null || true
fi

# 6. Optionnel: Whisper
echo "[6/6] Whisper (reconnaissance vocale offline)..."
if [[ "$1" == "--with-whisper" ]]; then
    echo "Installation Whisper (peut prendre plusieurs minutes)..."
    pip install openai-whisper torch
elif [[ "$1" == "--with-torch" ]]; then
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install openai-whisper
else
    echo ""
    echo "Whisper optionnel - options:"
    echo "  ./setup.sh --with-whisper    # Avec GPU acceleration"
    echo "  ./setup.sh --with-torch      # Torch CPU"
fi

echo ""
echo "=== Installation Terminee ==="
echo ""
echo "Activation: source venv/bin/activate"
echo "Lancer:    python voice_control.py --mode test"
echo "Setup complet: ./auto_setup.sh"
echo ""