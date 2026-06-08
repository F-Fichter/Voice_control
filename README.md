# Voice Control

Application CLI de contrôle vocal : **Whisper** (local ou Groq API) pour la reconnaissance (STT), **Groq API** pour le chat (LLM), **gTTS** pour la synthèse vocale.

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

```bash
cd ~/OPENCODE/voice_control
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Pour la reconnaissance vocale locale (optionnel mais recommandé) :
pip install openai-whisper torch --index-url https://download.pytorch.org/whl/cpu
```

### Activation

```bash
source venv/bin/activate
```

---

## 2. Configuration

### Obtenir une clé Groq (gratuite, sans CB)

1. Va sur [console.groq.com](https://console.groq.com) → inscris-toi
2. Génère une clé API (`gsk_...`)
3. Ajoute-la dans `config.json` :

```json
{
  "groq_api_key": "gsk_ta-clé-ici"
}
```

Avec cette clé, le chat passe par le cloud :
- **Reconnaissance vocale** → Whisper local (modèle `base`), fallback Groq Whisper-large-v3
- **Chat** → Groq Llama 3.3 70B (ou autre modèle au choix)
- **Recherche internet** → DuckDuckGo (intégré au chat, sans clé API)
- **Synthèse vocale** → gTTS (voix Google féminine)

### Fichiers de configuration

| Fichier | Description |
|---------|-------------|
| `config.json` | Configuration principale (clé Groq, audio, wake word) |
| `devices.json` | Appareils connectés |

### Paramètres importants

| Paramètre | Description | Valeur par défaut |
|-----------|-------------|-------------------|
| `groq_api_key` | **Clé Groq** (STT + chat) | `""` |
| `user_location` | Localisation utilisateur (commerces, météo, recherches) | `Surtainville 50270 France` |
| `audio.input_device` | Périphérique d'entrée | `null` (auto) |
| `audio.sample_rate` | Taux d'échantillonnage | `44100` |
| `wake_word` | Mot de réveil | `BOB` |
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
```

Au démarrage, choisis ton modèle Groq :

```
=======================================================
  Modèles Groq disponibles (chat cloud gratuit) :
    [1] Llama 3.3 70B - Ultra performant (recommandé)
    [2] Llama 3.1 8B - Très rapide
    [3] Llama 3 70B - Grande capacité
    [4] Mixtral 8x7B - Bon équilibre
    [d] Défaut (llama-3.3-70b-versatile)
=======================================================
Choix >
```

Puis dis **"BOB"** pour activer l'assistant.

---

## 4. Configuration Audio

### Lister les périphériques

```bash
python voice_control.py --list-audio-devices
```

Sortie :
```
Périphériques audio disponibles:
Index  Nom                                        In   Out  HW
---------------------------------------------------------------------------
  *    0 USB PnP Sound Device: Audio              1    0    hw:0,0
       1 Intel HDMI/DP LPE Audio: -               8    8    hw:1,0
       2 default                                   64   64   hw:2,0
       3 pulse                                     32   32   hw:3,0
```

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
  [#####.....]  -12.3 dB  attente 'BOB'...
```

Couleurs :
- Gris : silence
- Jaune : limité (rate limit)
- Blanc : parole détectée
- Vert : wake word OK

### Commandes

| Commande | Action |
|----------|--------|
| "BOB" + "allume" / "lumière" | Allume une lumière |
| "BOB" + "éteins" / "teins" | Éteint une lumière |
| "BOB" + "télé" / "tv" | Allume la télévision |
| "BOB" + "joue [artiste]" | Lance la musique YouTube |
| "BOB" + "stop" / "arrête" | Arrête musique/livre audio |
| "BOB" + "parle" / "discut" | Mode conversation (Groq LLM) |
| "BOB" + question quelconque | Réponse avec recherche internet si nécessaire |
| "BOB" + "PC" / "ordi" | Commande PC distant |
| "BOB" + "météo [ville]" | Météo du jour + 8 jours de prévisions (Open-Meteo gratuit) → ville inconnue = Surtainville. Marées du jour incluses |
| "BOB" + "pronostic quinté" | Pronostic PMU via recherche web |
| "BOB" + "résultat quinté" | Résultat PMU (arrivée) |
| *(pendant musique)* "stop" / "arrête" | Arrête instantanément sans wake word (fenêtre 3s) |

### Mode conversation

1. Dis "BOB" → "parle" (ou une question directement)
2. Le LLM répond via TTS
3. Parle normalement pour continuer la conversation
4. Dis "quit", "sortir" ou "au revoir" pour quitter
5. Anti-écho : détection automatique des répétitions TTS

### Météo

La météo utilise **Open-Meteo** (API gratuite, sans clé). Le parsing de ville extrait le nom après "météo" :
- "BOB, météo Paris" → météo de Paris
- "BOB, quel temps à Cherbourg" → météo de Cherbourg

**Fallback Surtainville** : si la ville n'est pas reconnue par Open-Meteo (ex. "sur Tainville" mal transcrit par Whisper), le système retente automatiquement avec "Surtainville".

**Prévisions 8 jours** : la réponse inclut les conditions actuelles + les prévisions des 8 prochains jours (min/max, précipitations, vent).

### Marées

Les horaires de marées (pleine mer / basse mer) du jour sont automatiquement inclus dans la réponse météo pour Surtainville. Les données proviennent de [horaire-maree.fr](https://www.horaire-maree.fr/maree/Surtainville/) (gratuit, sans clé).

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

### Anti-écho (mode chat)

- TTS synchrone : `wait=True` (bloquant)
- Pause de 1.5s après chaque réponse TTS
- Détection d'écho : si la transcription ressemble à >60% à la dernière réponse → ignorée

---

## 8. Plugins disponibles

| Plugin | Fonction |
|--------|----------|
| `tts_plugin` | Synthèse vocale (gTTS voix féminine, fallback eSpeak/Piper) |
| `chat_agent_plugin` | Chat IA via Groq API (Llama 3.3, 3.1, Mixtral...) |
| `smart_bulb_plugin` | Ampoules connectées |
| `tv_plugin` | Téléviseurs |
| `music_player_plugin` | Musique YouTube (mpv fullscreen, pipe yt-dlp) |
| `homeassistant_plugin` | Home Assistant |
| `esp32_relay_plugin` | Relais ESP32 |
| `pc_plugin` | Contrôle PC distant |
| `ir_plugin` | Contrôle infrarouge |
| `pmu_plugin` | PMU TurfInfo (programme quinté+) |
| `script_plugin` | Scripts shell |

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

Vérifie ta clé dans `config.json` :

```json
{
  "groq_api_key": "gsk_ta-clé-ici"
}
```

La clé doit commencer par `gsk_`.

### Le wake word n'est pas reconnu

- Vérifie que le micro est bien device[3] avec `--list-audio-devices`
- Parle plus fort ou rapproche-toi du micro
- Vérifie le VU mètre : si tu vois `(silence)` en parlant, le micro est trop faible
- Ajuste le seuil `rms < 0.001` dans `listen_for_wake_word()` de `voice_recognizer.py`

### La musique ne s'arrête pas

- Pendant la musique, dis directement **"stop"** ou **"arrête"** sans "BOB"
- Le système écoute en continu (fenêtre de 3s, ~15 appels/min Groq)
- Si ça ne marche pas, répète "stop" clairement
- Vérifie que le micro capte bien ta voix (le VU mètre doit réagir)

### "Aucun son" en SSH

```bash
python voice_control.py --mode test
```

### Pas de sortie audio HDMI

Utilise `--output-device 1` ou teste avec `--test-audio`.

### Le mode chat fait un monologue (écho)

- Le TTS est maintenant synchrone avec anti-écho intégré
- Si le problème persiste, monte le seuil d'écho dans `_is_echo()` de `voice_control.py`

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
├── voice_control.py          # Application principale
├── voice_recognizer.py       # STT (Whisper local / Groq), VAD, wake word, rate limiter
├── command_parser.py         # Analyse + exécution des commandes (météo, PMU, etc.)
├── plugin_manager.py         # Gestionnaire de plugins
├── test_io.py                # Script de test
├── plugins/
│   ├── tts_plugin.py         # Synthèse vocale (gTTS)
│   ├── chat_agent_plugin.py  # Chat IA (Groq)
│   ├── pmu_plugin.py         # PMU TurfInfo (programme quinté+)
│   ├── smart_bulb_plugin.py
│   ├── tv_plugin.py
│   ├── music_player_plugin.py  # YouTube audio (mpv)
│   └── ...
├── config.json
└── requirements.txt
```
