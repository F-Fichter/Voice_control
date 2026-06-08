# 🎙️ Voice Control - Guide Rapide

## Lancement

```bash
# Activer l'environnement
source ~/.voice-control/venv/bin/activate

# Mode test (texte)
python ~/.voice-control/voice_control.py --mode test

# Mode interactif (vocal)
python ~/.voice-control/voice_control.py --mode interactive
```

## Commandes Essentielles

| Quand vous dites... | Action |
|-------------------|--------|
| **BOB** | Active l'écoute |
| **soleil** | Toggle lampe salon |
| **box** | Toggle TV |
| **cinema** | Lance Netflix |
| **musique** | Joue musique |
| **silence** | Arrête musique |
| **allume la lumière** | Lumière ON |
| **éteins la TV** | TV OFF |
| **plus fort** | Volume + |
| **parlons** | Chat IA |
| **quit** | Quitte le mode |

## Configuration

- **Config** : `~/.voice-control/config.json`
- **Appareils** : `~/.voice-control/devices.json`
- **Aliases** : `~/.voice-control/aliases.json`

## Installation Audio (Optionnel)

```bash
# Nécessite sudo
sudo apt install portaudio19-dev libasound2-dev

# Puis (dans venv)
pip install sounddevice pyaudio openai-whisper torch
```

## Alias par Défaut

```
soleil  → Toggle lampe     | box     → Toggle TV
musique → Joue musique  | cinema → Netflix
silence → Stop musique  | ordi   → Toggle PC
```

## Dépannage

```bash
# Logs
tail -f ~/.voice-control/logs/*.log

# Vérifier audio
python -c "import sounddevice; print(sounddevice.query_devices())"

# Réinstaller Whisper
pip install --force-reinstall openai-whisper torch
```

## Pour Aller Plus Loin

- **Chat IA** : Installez [Ollama](https://ollama.com)
- **Email** : `./setup_smtp.sh` (sudo requis)
- **DNS** : `python ddns_updater.py --setup`

---
*Voice Control v1.0*