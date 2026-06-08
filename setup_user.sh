#!/usr/bin/env bash
# Installation sans sudo - tout dans ~/.local/
# Fonctionne sur x86_64, aarch64, armv7l sans droits root

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.voice-control"

echo "========================================"
echo "  Voice Control - Installation User"
echo "  (sans droits sudo)"
echo "========================================"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 1. Déterminer l'arch
echo -e "${BLUE}[1/7] Détection système${NC}"
ARCH=$(uname -m)
echo "Architecture: $ARCH"

PYTHON=$(command -v python3 || command -v python)
echo "Python: $PYTHON"

# 2. Créer l'environnement
echo -e "${BLUE}[2/7] Création environnement${NC}"
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

$PYTHON -m venv venv
source venv/bin/activate

# 3. Dépendances Python (dans venv)
echo -e "${BLUE}[3/7] Installation Python${NC}"

pip install --upgrade pip

# Core (dans le venv, pas --user)
pip install \
    numpy \
    sounddevice \
    requests \
    pygame \
    yt-dlp \
    gtts \
    flask \
    flask-cors

# pyaudio optionnel (nécessite portaudio.h = sudo)
if [[ "$1" == "--with-pyaudio" ]]; then
    pip install pyaudio || echo "pyaudio nécessite sudo apt install portaudio19-dev"
fi

# 4. Vérifier les outils audio
echo -e "${BLUE}[4/7] Vérification audio${NC}"

check_audio_tool() {
    command -v "$1" &> /dev/null && echo "  ✓ $1" || echo "  ✗ $1 (optionnel)"
}

check_audio_tool mpv
check_audio_tool ffplay
check_audio_tool aplay
check_audio_tool mpg123

# 5. TTS
echo -e "${BLUE}[5/7] TTS${NC}"
if command -v espeak &> /dev/null; then
    echo "  ✓ espeak disponible"
else
    echo "  ✗ espeak non installé"
    echo "  Option: Installez espeak via votre package manager"
fi

# 6. Copier les fichiers
echo -e "${BLUE}[6/7] Configuration${NC}"

mkdir -p "${INSTALL_DIR}/plugins"
mkdir -p "${INSTALL_DIR}/.config"

# Copie si pas déjà présent
if [ ! -f "${INSTALL_DIR}/voice_control.py" ]; then
    cp -r "${SCRIPT_DIR}"/* "${INSTALL_DIR}/"
fi

# Crée les configs par défaut
if [ ! -f "${INSTALL_DIR}/config.json" ]; then
    cp "${SCRIPT_DIR}/config.json.example" "${INSTALL_DIR}/config.json" 2>/dev/null || true
fi

if [ ! -f "${INSTALL_DIR}/aliases.json" ]; then
    cp "${SCRIPT_DIR}/aliases.json.example" "${INSTALL_DIR}/aliases.json" 2>/dev/null || true
fi

# 7. Whiser (optionnel)
echo -e "${BLUE}[7/7] Whisper (optionnel)${NC}"
if [[ "$1" == "--with-whisper" ]]; then
    echo "Installation Whisper..."
    pip install --user openai-whisper torch
elif [[ "$1" == "--with-torch" ]]; then
    echo "Installation PyTorch + Whisper..."
    pip install --user torch --index-url https://download.pytorch.org/whl/cpu
    pip install --user openai-whisper
else
    echo "Whisper optionnel - ajoutez avec: --with-whisper"
fi

# Symlink pratique
echo ""
echo -e "${BLUE}=== Alias de commande${NC}"
cat << 'EOF' >> "${HOME}/.bashrc" 2>/dev/null || true

# Voice Control
export VOICE_CONTROL_DIR="${INSTALL_DIR}"
alias vc="cd ${INSTALL_DIR} && source venv/bin/activate && python voice_control.py"
alias voice="cd ${INSTALL_DIR} && source venv/bin/activate"
alias vctest="cd ${INSTALL_DIR} && source venv/bin/activate && python voice_control.py --mode test"
EOF

echo ""
echo -e "${GREEN}=== Installation Terminee ===${NC}"
echo ""
echo "Emplacement: ${INSTALL_DIR}"
echo ""
echo "Pour activer:"
echo "  source ${INSTALL_DIR}/venv/bin/activate"
echo ""
echo "Pour lancer:"
echo "  python ${INSTALL_DIR}/voice_control.py --mode test"
echo ""
echo "Ou avec l'alias (après reload shell):"
echo "  voice          # Active l'environnement"
echo "  vc             # Lance l'app"
echo "  vctest         # Mode test"
echo ""
echo -e "${YELLOW}Prochaines etapes:${NC}"
echo "  1. pip install --user openai-whisper  # Si vous voulez la reconnaissance vocale"
echo "  2. ./auto_setup.sh                     # Configuration DNS/Box"
echo "  3. ./setup_smtp.sh                     # Si serveur email (requiert sudo)"
echo ""