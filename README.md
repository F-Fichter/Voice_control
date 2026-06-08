# Voice Control

Application CLI de contrôle vocal : **Groq API** (Whisper-large-v3) pour la reconnaissance (STT), **Groq API** pour le chat (LLM), **gTTS** pour la synthèse vocale. Fonctionne sur x86_64 et ARM64.

## Table des matières

1. [Installation](#1-installation)
2. [Configuration](#2-configuration)
3. [Lancement rapide](#3-lancement-rapide)
4. [Configuration audio](#4-configuration-audio)
5. [Options de démarrage](#5-options-de-démarrage)
6. [Commandes vocales](#6-commandes-vocales)
7. [Fonctionnement détaillé](#7-fonctionnement-détaillé)
8. [Plugins disponibles](#8-plugins-disponibles)
9. [Résolution de problèmes](#9-résolution-de-problèmes)

---

## 1. Installation

### Dépendances système (x86_64 / ARM64)

```bash
sudo apt install -y python3 python3-pip python3-venv portaudio19-dev libasound2-dev \
    ffmpeg mpv
```

### Python

```bash
cd ~/OPENCODE/voice_control
python3 -m venv venv
source venv/bin/activate
pip install numpy sounddevice requests gtts yt-dlp ddgs beautifulsoup4 lxml Pillow
```

Pour la reconnaissance locale (optionnel) :
```bash
pip install openai-whisper torch --index-url https://download.pytorch.org/whl/cpu
```

### Activation

```bash
source venv/bin/activate
```

### Architecture ARM64

Le projet tourne sur ARM64 (Orange Pi, RK3528, Raspberry Pi). Scripts dédiés :
- `setup_orangepi2w.sh` — Orange Pi 2W (Allwinner H618, 4GB RAM)
- `setup_rk3528.sh` — RK3528
- `Dockerfile.arm64` — Build Docker multi-arch

---

## 2. Configuration

### Obtenir une clé Groq (gratuite, sans CB)

1. Va sur [console.groq.com](https://console.groq.com) → inscris-toi
2. Génère une clé API (`gsk_...`)
3. Copie `config.json.example` → `config.json` → ajoute ta clé

```json
{
  "groq_api_key": "gsk_ta-clé-ici"
}
```

> **Note** : `config.json` est dans `.gitignore` pour ne pas exposer ta clé.

Avec cette clé :
- **Reconnaissance vocale** → Groq Whisper-large-v3 (cloud)
- **Chat** → Groq (9 modèles disponibles au choix)
- **Recherche internet** → DuckDuckGo (intégré au chat, sans clé API)
- **Synthèse vocale** → gTTS (voix Google féminine)

### Fichiers de configuration

| Fichier | Description |
|---------|-------------|
| `config.json` | Configuration principale (clé Groq, audio, wake word) — **hors git** |
| `config.json.example` | Exemple de configuration |
| `devices.json` | Appareils connectés |

### Paramètres importants

| Paramètre | Description | Valeur par défaut |
|-----------|-------------|-------------------|
| `groq_api_key` | **Clé Groq** (STT + chat) | `""` |
| `user_location` | Localisation utilisateur (commerces, météo, recherches) | `Surtainville 50270 France` |
| `audio.input_device` | Périphérique d'entrée (null = auto) | `null` |
| `audio.input_devices` | **Plusieurs micros** (liste d'indices) | `[3, 4]` |
| `audio.sample_rate` | Taux d'échantillonnage | `44100` |
| `wake_word` | Mot de réveil | `bob` |
| `whisper.model` | Modèle Whisper local | `base` |
| `whisper.language` | Langue STT | `fr` |
| `ollama_model` | Modèle de chat choisi | `llama-3.3-70b-versatile` |

---

## 3. Lancement rapide

```bash
source venv/bin/activate

# Mode interactif (recommandé)
python voice_control.py --input-device 3

# Test audio avant de commencer
python voice_control.py --input-device 3 --test-audio

# Mode test texte (sans micro)
python voice_control.py --mode test --test-text "météo Surtainville"
```

Au démarrage, choisis ton modèle Groq :

```

=======================================================
  Modèles Groq disponibles (chat cloud gratuit) :
    [1] Llama 3.3 70B - Ultra performant (recommandé)
    [2] Llama 3.1 8B - Très rapide
    [3] Llama 4 Scout 17B - Scout
    [4] Qwen 3 32B - Qwen
    [5] Compound  - Compound
    [6] Compound Mini - Compound Mini
    [7] GPT OSS 20B - GPT OSS 20B
    [8] GPT OSS 120B - GPT OSS 120B
    [9] Allam 2 7B - Allam
    [c] Personnalisé
    [d] Défaut (llama-3.3-70b-versatile)
=======================================================
Choix >
```

Puis dis **"bob"** pour activer l'assistant.

---

## 4. Configuration Audio

### Lister les périphériques

```bash
python voice_control.py --list-audio-devices
```

Sortie typique :
```
Périphériques audio disponibles:
Index  Nom                                        In   Out  HW
---------------------------------------------------------------------------
  *    0 rockchip-hdmi0                           0    2    hw:0,0
       1 USB PnP Sound Device: Audio              1    0    hw:1,0
       2 USB PnP Sound Device: Audio              1    0    hw:2,0
       3 sysdefault                                0    128
       7 pulse                                     32   32
      12 default                                   32   32
```

### Double micro

La config supporte **deux micros simultanément** via `input_devices` (liste) :
```json
"audio": {
  "input_devices": [1, 2],
  "sample_rate": 44100
}
```

Le système enregistre sur les deux entrées et moyenne les signaux pour une meilleure couverture.

### Sample rate

Le sample rate natif du micro est détecté automatiquement (ex. 44100 Hz pour micro USB).

### Micro USB faible

Si le micro USB a un signal très faible (–46 dB typique) :
- Le gain matériel est maxé automatiquement (16/16, 24 dB)
- Une normalisation logicielle amplifie le signal à –12 dBFS avant envoi à Groq
- Le VAD (Voice Activity Detection) utilise openWakeWord (Silero via ONNX) + fallback WebRTC

---

## 5. Options de démarrage

### Syntaxe

```bash
python voice_control.py [OPTIONS]
```

### Options

| Option | Description | Exemple |
|--------|-------------|---------|
| `--input-device X` | Micro | `3`, `"hw:1,0"`, `default` |
| `--output-device X` | Haut-parleurs | `0`, `"hw:0,0"`, `default` |
| `--sample-rate X` | Sample rate | `44100` |
| `--mode MODE` | Mode | `interactive`, `test`, `listen`, `info` |
| `--test-audio` | Test complet entrée/sortie | - |
| `--test-text "..."` | Test sans micro | `"allume la lumière"` |
| `--list-audio-devices` | Liste les périphériques | - |

### Modes

| Mode | Description | Commande |
|------|-------------|----------|
| `interactive` | Wake word + vocal (défaut) | `python voice_control.py` |
| `test` | Texte seulement | `python voice_control.py --mode test` |
| `listen` | Une commande vocale | `python voice_control.py --mode listen` |
| `info` | Infos système | `python voice_control.py --mode info` |

---

## 6. Commandes vocales

### Mot de réveil

Dis **"BOB"** pour activer l'écoute.

Pendant la lecture YouTube, tu peux aussi dire directement **"stop"**, **"arrête"**, **"pause"**, **"silence"** sans dire "BOB". L'écoute est continue (fenêtre de 3s, ~15 appels/min) pour un arrêt rapide.

### Retour visuel

Un VU mètre s'affiche en temps réel :

```
  [#####.....]  -12.3 dB  attente 'bob'...
```

Couleurs :
- Gris : silence
- Jaune : limité (rate limit)
- Blanc : parole détectée
- Vert : wake word OK

### Commandes

| Commande | Action |
|----------|--------|
| "bob" + "allume" / "lumière" | Allume une lumière |
| "bob" + "éteins" / "teins" | Éteint une lumière |
| "bob" + "télé" / "tv" | Allume la télévision |
| "bob" + "joue [artiste]" | Lance la musique YouTube |
| "bob" + "stop" / "arrête" | Arrête musique/livre audio |
| "bob" + "parle" / "discut" | Mode conversation (Groq LLM) |
| "bob" + question quelconque | Réponse avec recherche internet si nécessaire |
| "bob" + "PC" / "ordi" | Commande PC distant |
| "bob" + "météo [ville]" | Météo + 8 jours de prévisions + **marées par jour** (7 jours, TideTurtle API) |
| "bob" + "pronostic quinté" | Pronostic PMU via recherche web |
| "bob" + "résultat quinté" | Résultat PMU (arrivée) |
| "bob" + "annule" | Annule toute action en cours (TTS, musique) |
| "bob" + "recommence" | Rejoue la dernière vidéo ou répète le dernier TTS |
| *(pendant lecture)* **Escape** / **Ctrl+Space** | Annulation immédiate |
| *(pendant lecture)* **"annule"** (sans bob) | Annulation vocale immédiate |

### Mode conversation

1. Dis "bob" → "parle" (ou une question directement)
2. Le LLM répond via TTS
3. Parle normalement pour continuer la conversation
4. Dis "quit", "sortir" ou "au revoir" pour quitter
5. Anti-écho : détection automatique des répétitions TTS

### Annulation immédiate

| Méthode | Portée | Comment ça marche |
|---------|--------|-------------------|
| **Escape** | Tout moment | Thread daemon lit stdin en mode cbreak + non-bloquant, détecte `\x1b`, tue TTS + média |
| **Ctrl+Space** | Tout moment | Même mécanisme, détecte `\x00` |
| **"bob annule"** | Todo | Déclenche l'action `cancel` |
| **"annule"** (sans bob) | Pendant TTS | `_speak_with_cancel()` enregistre + reconnaît le micro toutes les ~0.9s |

Après annulation, le système revient à l'écoute du wake word "bob". Un annuler précédent ne peut pas annuler la commande suivante.

### Météo

La météo utilise **Open-Meteo** (API gratuite, sans clé). Le parsing de ville extrait le nom après "météo" :
- "bob, météo Paris" → météo de Paris
- "bob, quel temps à Cherbourg" → météo de Cherbourg

**Fallback Surtainville** : si la ville n'est pas reconnue par Open-Meteo (ex. "sur Tainville" mal transcrit par Whisper), le système retente automatiquement avec "Surtainville".

**Prévisions 9 jours** : la réponse inclut les conditions actuelles + les prévisions des 9 prochains jours (min/max, précipitations, vent).

### Marées

Les horaires de marées (pleine mer / basse mer) proviennent de **TideTurtle API** (gratuite, sans clé, 7 jours de données Open-Meteo Marine).

**Par jour** : chaque jour de prévision dans la limite de 7 jours affiche ses propres marées à côté des conditions météo :
```
A Surtainville, Nuageux. 14.1 degrés...
Marées: pleine mer 14h19 (0.84m); basse mer 21h03 (-1.63m).
Prévisions. mercredi: Bruine — basse mer 00h44 (-2.01m); pleine mer 06h27 (1.18m)...
```

Aujourd'hui = après les conditions actuelles, avant les prévisions.
Jours 8+ (au-delà de 7j TideTurtle) = météo seule, sans marées.

### PMU (pronostics / résultats)

Deux commandes distinctes :

| Commande | Source | Comportement |
|----------|--------|-------------|
| `pronostic quinté` | Recherche web (via LLM) | Le LLM cherche sur canalturf, geny, zone-turf → réponse vocale riche |
| `résultat quinté` | API PMU TurfInfo | Arrivée officielle du dernier quinté+ couru |

Le pronostic passe par une recherche web car les noms de chevaux ne sont pas disponibles via l'API PMU (CloudFront bloque les endpoints participants).

### Recherche internet

Le chat peut chercher sur internet via DuckDuckGo (gratuit, sans clé API).
Pose une question factuelle :

- "BOB, qui a gagné le dernier match ?" → recherche sport → réponse vocale
- "BOB, c'est quoi la Tour Eiffel ?" → recherche Wikipedia → réponse vocale

Le LLM décide automatiquement s'il doit chercher sur internet ou répondre de tête.

---

## 7. Fonctionnement détaillé

### Pipeline de détection du wake word

1. Capture audio 1s sur le micro USB (44100 Hz)
2. Seuil d'énergie : si RMS < 0.001 et peak < 0.002 → silence, ignoré
3. Normalisation à –12 dBFS
4. **openWakeWord VAD** (Silero via ONNX, fallback WebRTC) : détection de parole
5. Rate limiter : max 15 appels/min (2/min pendant musique)
6. Transcription : **Whisper local** (modèle `base`) si installé, fallback **Groq Whisper-large-v3**
7. Vérification : le texte contient-il "BOB" ?

### Rate limiting Groq

| Type | Limite | Contexte |
|------|--------|----------|
| Wake word | 15/min | Normal |
| Wake word (musique) | 2/min | Pendant lecture YouTube |
| Commandes directes (musique) | 15/min | Stop/arrête sans wake word, fenêtre 3s |
| Chat LLM | 30/min | Modèle de chat séparé |

### Annulation clavier

Le thread `_cancel_listener` surveille stdin en mode **non-canonique** (`tty.setcbreak`) + **non-bloquant** (`fcntl.O_NONBLOCK`). Détecte les touches brutes :
- `\x1b` → **Escape**
- `\x00` → **Ctrl+Space**

Appelle directement `tts.stop()` + `_stop_all_playback()`.

> Note : `stdin=subprocess.DEVNULL` est passé aux players (gtts, mpv) pour qu'ils ne consomment pas stdin.

### Anti-écho (mode chat)

- TTS synchrone : `wait=True` (bloquant)
- Pause de 1.5s après chaque réponse TTS
- Détection d'écho : si la transcription ressemble à >60% à la dernière réponse → ignorée

---

## 8. Plugins disponibles

| Plugin | Fonction |
|--------|----------|
| `tts_plugin` | Synthèse vocale (gTTS voix féminine, stop() kill process + nettoyage tmp) |
| `chat_agent_plugin` | Chat IA via Groq API (9 modèles + personnalisé) + recherche web DuckDuckGo avec récupération contenu pages |
| `music_player_plugin` | Musique YouTube (yt-dlp \| mpv, `--no-keep-open --loop=no`) |
| `audiobook_plugin` | Livres audio (YouTube + litteratureaudio.com) |
| `smart_bulb_plugin` | Ampoules connectées (Hue, Tuya, Shelly, LIFX) |
| `tv_plugin` | Téléviseurs (Samsung, LG, Chromecast) |
| `homeassistant_plugin` | Home Assistant |
| `esp32_relay_plugin` | Relais ESP32 |
| `pc_plugin` | Contrôle PC distant (WoL, SSH, API Flask) |
| `ir_plugin` | Contrôle infrarouge (LIRC, Broadlink, Flirc) |
| `pmu_plugin` | PMU TurfInfo (programme quinté+) |
| `script_plugin` | Scripts shell |
| `wake_word_engine` | Détection wake word avec VAD (openWakeWord / WebRTC) |
| `conversation_logger` | Log des conversations en Markdown |

---

## 9. Résolution de problèmes

### "Module not found: gtts"

```bash
pip install gtts
```

### "Module not found: sounddevice"

```bash
pip install sounddevice
```

### "Invalid sample rate"

Utilise `--sample-rate 44100` ou supprime l'option (détection auto) :

```bash
python voice_control.py --input-device default
```

### "Groq connection error"

Vérifie ta clé dans `config.json` (hors git, à créer depuis `config.json.example`) :

```bash
cp config.json.example config.json
# édite config.json → mets ta clé gsk_...
```

La clé doit commencer par `gsk_`.

### Le wake word n'est pas reconnu

- Vérifie les indices micros avec `--list-audio-devices`
- Configure `input_devices` dans `config.json` (ex. `[1, 2]` pour deux micros USB)
- Parle plus fort ou rapproche-toi du micro
- Vérifie le VU mètre : si tu vois `(silence)` en parlant, le micro est trop faible
- Ajuste le seuil `rms < 0.001` dans `listen_for_wake_word()` de `voice_recognizer.py`

### La musique ne s'arrête pas

- Pendant la musique, dis directement **"stop"**, **"arrête"** ou **"annule"** sans "bob"
- **Escape** ou **Ctrl+Space** au clavier pour annulation immédiate
- Le système écoute en continu (fenêtre de 3s, ~15 appels/min Groq)
- Si ça ne marche pas, répète "stop" clairement
- Vérifie que le micro capte bien ta voix (le VU mètre doit réagir)

### "Aucun son" en SSH

```bash
python voice_control.py --mode test
```

### Pas de sortie audio HDMI

Utilise `--output-device 0` ou teste avec `--test-audio`.

### Le mode chat fait un monologue (écho)

- Le TTS est synchrone avec anti-écho intégré
- Si le problème persiste, monte le seuil d'écho dans `_is_echo()` de `voice_control.py`

### "pkill: Exec format error" (ARM64)

Le binaire `pgrep` (symlink cible de `pkill`) peut être corrompu. Réinstalle `procps` :
```bash
sudo apt install --reinstall procps
```

---

## Script de test

Teste tous les composants d'un coup :

```bash
python test_io.py
```

Affiche le mode (cloud/local), teste l'audio, les imports, le parsing, le TTS, le chat et l'API Groq.

---

## Architecture

```
voice_control/
├── voice_control.py          # Application principale (cancel, TTS, mode interactif)
├── voice_recognizer.py       # STT (Groq Whisper-large-v3), double micro, VAD, wake word
├── command_parser.py         # Analyse + exécution des commandes (météo, marées TideTurtle, PMU, etc.)
├── plugin_manager.py         # Gestionnaire de plugins
├── test_io.py                # Script de test
├── thumbnail_display.py      # Sélection visuelle YouTube (Firefox + voix)
├── conversation_logger.py    # Log des échanges en Markdown
├── key_helper.py             # Lecture clavier raw (non-canonique)
├── config.json               # Configuration (clé Groq, audio, localisation) **hors git**
├── config.json.example       # Exemple de config
├── requirements.txt          # Dépendances Python
├── .gitignore                # config.json, venv, logs, pycache exclus
├── Dockerfile.amd64          # Build Docker x86_64
├── Dockerfile.arm64          # Build Docker ARM64
├── setup.sh                  # Installation x86_64
├── setup_orangepi2w.sh       # Installation Orange Pi 2W (ARM64)
├── setup_rk3528.sh           # Installation RK3528 (ARM64)
├── plugins/
│   ├── tts_plugin.py         # Synthèse vocale (gTTS, stop() kill process)
│   ├── chat_agent_plugin.py  # Chat IA (Groq, 9 modèles)
│   ├── music_player_plugin.py  # YouTube audio (mpv + yt-dlp)
│   ├── audiobook_plugin.py   # Livres audio YouTube / litteratureaudio.com
│   ├── pmu_plugin.py         # PMU TurfInfo
│   ├── smart_bulb_plugin.py  # Ampoules (Hue, Tuya, etc.)
│   ├── tv_plugin.py          # Téléviseurs (Samsung, LG, Chromecast)
│   ├── pc_plugin.py          # PC distant (WoL, SSH, API)
│   ├── ir_plugin.py          # IR (LIRC, Broadlink, Flirc)
│   ├── esp32_relay_plugin.py # Relais ESP32
│   ├── homeassistant_plugin.py  # Home Assistant
│   ├── http_plugin.py        # Périphériques HTTP
│   ├── script_plugin.py      # Scripts shell
│   └── wake_word_engine.py   # VAD (openWakeWord / WebRTC)
└── venv/                     # Virtualenv (hors git)
```
