# Script de contrôle - RK3528 / OrangePi / ARM
# Installation complète avec toutes les dépendances

set -e

echo "=== Voice Control - Setup RK3528 / ARM ==="

# 1. Dépendances système ARM64
echo "[1/6] Installation dépendances système..."
sudo apt update
sudo apt-get install -y \
    python3-pip python3-venv python3-dev \
    python3-numpy \
    portaudio19-dev \
    libasound2-dev \
    libsndfile1 \
    ffmpeg \
    libopenjp2-7-dev \
    build-essential \
    git curl wget \
    espeak espeak-ng \
    mpv mplayer mpg123

# 2. Environnement virtuel
echo "[2/6] Création environnement..."
python3 -m venv venv
source venv/bin/activate

# 3. Dépendances Python core
echo "[3/6] Installation Python..."
pip install --upgrade pip
pip install numpy sounddevice requests

# 4. Audio
echo "[4/6] Installation audio..."
pip install pyaudio pygame

# 5. TTS
echo "[5/6] Installation TTS..."
pip install gtts

# 6. Optionnel: Whisper ARM
if [[ "$1" == "--with-whisper" ]]; then
    echo "[6/6] Installation Whisper (attention: ~20min sur ARM)..."
    # PyTorch CPU pour ARM
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install openai-whisper
else
    echo "[6/6] Whisper optionnel"
fi

echo ""
echo "=== Terminé ==="
echo ""
echo "Activation: source venv/bin/activate"
echo "Lancer:    python voice_control.py --mode test"
echo "Config DNS: python3 ddns_updater.py --setup"
echo "Ports Box:  python3 port_forwarder.py --setup"