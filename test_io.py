#!/usr/bin/env python3
"""
Script de test pour voice_control
Teste: audio (entree/sortie), imports, parsing, plugins, TTS, STT, chat
"""

import sys
import os
import json
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))


# ─── Utilitaires d'affichage ───────────────────────────────────────

def jauge(level: float, width: int = 20, label: str = ""):
    filled = int(level * width)
    bar = "#" * filled + "." * (width - filled)
    pct = int(level * 100)
    print(f"\r  {label} [{bar}] {pct}%  ", end="", flush=True)


def print_title(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ─── Tests ─────────────────────────────────────────────────────────

def test_imports() -> bool:
    print_title("TEST 1 : Imports")
    ok = True
    for mod_name, import_path in [
        ("voice_control", "voice_control"),
        ("VoiceRecognizer", "voice_recognizer"),
        ("CommandParser", "command_parser"),
        ("PluginManager", "plugin_manager"),
        ("TTSPlugin", "plugins.tts_plugin"),
        ("ChatAgent", "plugins.chat_agent_plugin"),
    ]:
        try:
            __import__(import_path, fromlist=[mod_name.split(".")[-1]])
            print(f"  [OK] {mod_name}")
        except Exception as e:
            print(f"  [ERR] {mod_name} : {e}")
            ok = False
    return ok


def test_audio_play(device: Optional[int] = None) -> bool:
    print_title("TEST 2 : Sortie audio (sounddevice)")
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("  sounddevice non installe")
        return False

    if device is None:
        device = sd.default.device[1]

    try:
        info = sd.query_devices(device)
        sr = int(info["default_samplerate"])
        out_ch = info["max_output_channels"]
        print(f"  Sortie : device[{device}] {info['name']}")
        print(f"  Sample rate : {sr} Hz, canaux : {out_ch}")

        t = np.linspace(0, 0.8, int(sr * 0.8), endpoint=False)
        wave = 0.3 * np.sin(2 * np.pi * 440 * t)
        if out_ch > 1:
            wave = np.column_stack([wave] * min(out_ch, 6))

        for i in range(3):
            jauge((i + 1) / 3, label="Lecture")
            sd.play(wave, samplerate=sr, device=device)
            sd.wait()
            time.sleep(0.2)
        print("\n  [OK] Son emis")
        return True
    except Exception as e:
        print(f"\n  [ERR] {e}")
        return False


def test_audio_record(device: Optional[int] = None) -> bool:
    print_title("TEST 3 : Entree audio (sounddevice)")
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("  sounddevice non installe")
        return False

    if device is None:
        device = sd.default.device[0]

    try:
        info = sd.query_devices(device)
        sr = int(info["default_samplerate"])
        print(f"  Entree : device[{device}] {info['name']}")
        print(f"  Sample rate natif : {sr} Hz")
        print("  Parle dans le micro (2s)...")

        duration = 2
        samples = int(duration * sr)
        recorded = sd.rec(samples, samplerate=sr, channels=1, device=device)

        steps = int(duration / 0.1)
        for i in range(steps):
            time.sleep(0.1)
            end = min(int((i + 1) * 0.1 * sr), samples)
            chunk = recorded[max(0, end - int(0.1 * sr)):end]
            if len(chunk) > 0:
                peak = float(np.nanmax(np.abs(chunk)))
                if np.isnan(peak) or peak < 1e-10:
                    peak = 1e-10
                db = 20 * np.log10(peak)
                b = min(int(round(peak * 20, 0)), 20)
                print(f"\r  [{'#' * b}{'.' * (20 - b)}] {db:+.0f} dB  ", end="", flush=True)

        sd.wait()
        audio = recorded.flatten()
        peak = float(np.max(np.abs(audio)))
        db = 20 * np.log10(max(peak, 1e-10))
        print(f"\n  Niveau max : {db:+.0f} dB")
        if peak < 0.01:
            print("  [WARN] Silence detecte (parle plus fort ?)")
        print("  [OK] Enregistrement termine")
        return True
    except Exception as e:
        print(f"\n  [ERR] {e}")
        return False


def test_config_files() -> bool:
    print_title("TEST 4 : Fichiers de configuration")
    base = Path(__file__).parent
    ok = True
    for name in ["config.json", "devices.json"]:
        path = base / name
        if path.exists():
            try:
                with open(path) as f:
                    json.load(f)
                print(f"  [OK] {name}")
            except json.JSONDecodeError as e:
                print(f"  [ERR] {name} (JSON invalide : {e})")
                ok = False
        else:
            print(f"  [--] {name} absent")
    return ok


def test_command_parser() -> bool:
    print_title("TEST 5 : Parsing de commandes")
    try:
        from command_parser import CommandParser
    except ImportError:
        print("  [ERR] command_parser non trouve")
        return False

    class MockPlugin:
        def toggle(self, *a): pass
        def play(self, *a): pass
        def stop(self, *a): pass
    class MockManager:
        plugins = {"music": MockPlugin()}
        def get_plugin_for_type(self, t): return MockPlugin()

    parser = CommandParser(MockManager())
    tests = [
        ("allume la lumiere", True),
        ("éteins le salon",  True),
        ("joue de la musique", True),
        ("parle avec bob",     True),
        ("zfhjkldfg",          False),
    ]
    ok = True
    for cmd, expected in tests:
        result = parser.parse(cmd)
        success = result.get("success", False) if result else False
        if success == expected:
            print(f"  [OK] \"{cmd}\" -> {success}")
        else:
            print(f"  [ERR] \"{cmd}\" -> {success} (attendu {expected})")
            ok = False
    return ok


def test_tts() -> bool:
    print_title("TEST 6 : Synthese vocale (TTS)")
    try:
        from plugins.tts_plugin import TTSPlugin
    except ImportError:
        print("  [ERR] TTSPlugin non trouve")
        return False

    class MockManager:
        pass

    tts = TTSPlugin(MockManager())
    if tts.engine is None:
        print("  [WARN] Aucun moteur TTS disponible")
        print("  Installes : gtts (pip install gtts) ou espeak-ng (apt install espeak-ng) ou piper")
        return False

    print(f"  Moteur : {tts.engine}")
    print(f"  Vitesse : {tts.rate} mots/min")
    ok = True
    for method in ["speak", "speak_async", "confirm", "set_rate", "set_voice", "is_available"]:
        if hasattr(tts, method):
            print(f"  [OK] {method}()")
        else:
            print(f"  [ERR] {method}() manquant")
            ok = False
    return ok


def test_chat() -> bool:
    print_title("TEST 7 : Chat IA (Groq / Ollama / fallback)")
    try:
        from plugins.chat_agent_plugin import ChatAgent
    except ImportError:
        print("  [ERR] ChatAgent non trouve")
        return False

    class MockManager:
        tts = None

    agent = ChatAgent(MockManager())
    print(f"  API : {agent.api_type or 'aucune'}")
    print(f"  Modele : {agent.model or 'aucun'}")
    if agent.is_available():
        resp = agent.chat("dis bonjour", voice=False)
        if resp:
            print(f"  Reponse : \"{resp[:100]}\"")
            print("  [OK] Chat operationnel")
            return True
        else:
            print("  [WARN] Chat disponible mais reponse vide")
            return False
    else:
        print("  [WARN] Chat non disponible")
        return False


def test_stt_api() -> bool:
    print_title("TEST 8 : API STD distante (Groq / OpenAI)")
    cfg_path = Path(__file__).parent / "config.json"
    if not cfg_path.exists():
        print("  [--] config.json absent")
        return False

    with open(cfg_path) as f:
        cfg = json.load(f)

    groq_key = cfg.get("groq_api_key", "")
    openai_key = cfg.get("openai_api_key", "")
    endpoint = cfg.get("stt_endpoint", "")

    if not groq_key and not openai_key and not endpoint:
        print("  [--] Aucune API STT configuree (groq_api_key / openai_api_key / stt_endpoint)")
        return False

    if endpoint:
        print(f"  Endpoint custom : {endpoint}")
        print("  (test manuel requis)")
        return True

    if groq_key:
        print("  API Groq detectee (Whisper-large-v3)")
        try:
            import requests
            r = requests.get("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {groq_key}"},
                             timeout=10)
            if r.status_code == 200:
                models = [m["id"] for m in r.json().get("data", []) if "whisper" in m["id"]]
                print(f"  [OK] Connexion Groq OK, modeles STT : {models}")
                return True
            else:
                print(f"  [ERR] Connexion Groq : {r.status_code} {r.text[:100]}")
                return False
        except Exception as e:
            print(f"  [ERR] Connexion Groq : {e}")
            return False

    if openai_key:
        print("  API OpenAI detectee")
        print("  (test manuel ou verification de cle)")
        return True

    return False


def test_ollama() -> bool:
    print_title("TEST 9 : Ollama (chat local)")
    try:
        import requests
        r = requests.get("http://localhost:11434/api/version", timeout=2)
        if r.status_code != 200:
            print("  [WARN] Ollama ne repond pas")
            return False
        version = r.json().get("version", "?")
        print(f"  Version : {version}")

        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = r.json().get("models", [])
        if models:
            for m in models:
                print(f"  [OK] Modele : {m['name']}")
        else:
            print("  [WARN] Aucun modele charge")
        return bool(models)
    except Exception as e:
        print(f"  [WARN] Ollama indisponible : {e}")
        return False


# ─── Menu audio ────────────────────────────────────────────────────

def list_devices():
    try:
        import sounddevice as sd
        print(f"\n{'Index':<6} {'Nom':<50} {'In':<4} {'Out':<4}")
        print("-" * 64)
        for i, dev in enumerate(sd.query_devices()):
            m = "*" if i == sd.default.device[0] or i == sd.default.device[1] else " "
            print(f"  {m} {i:<4} {dev['name']:<50} {dev['max_input_channels']:<4} {dev['max_output_channels']:<4}")
    except ImportError:
        print("sounddevice non installe")


def select_device(prompt: str, default: int, kind: str = "input") -> int:
    while True:
        choice = input(f"{prompt} (defaut: {default}, ?=liste) : ").strip()
        if choice == '':
            return default
        if choice == '?':
            list_devices()
            continue
        try:
            idx = int(choice)
            return idx
        except ValueError:
            print("  Entrez un numero ou vide pour le defaut")


# ─── Main ──────────────────────────────────────────────────────────

def is_cloud_mode() -> bool:
    """Detection mode 100% cloud (Groq)"""
    cfg_path = Path(__file__).parent / "config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
            return bool(cfg.get("groq_api_key", ""))
    return False


def main():
    cloud = is_cloud_mode()
    print(f"\n{'#' * 60}")
    print(f"  TEST DES ENTREES/SORTIES - VOICE CONTROL")
    print(f"{'#' * 60}")
    print(f"\n  Date : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode : {'100% cloud (Groq)' if cloud else 'local (Whisper + Ollama)'}")
    print(f"  Repertoire : {Path(__file__).parent}")

    # Menu peripheriques
    print(f"\n--- Peripheriques audio ---")
    list_devices()

    try:
        import sounddevice as sd
        def_in = sd.default.device[0]
        def_out = sd.default.device[1]
    except ImportError:
        def_in = def_out = 0

    in_dev = select_device("  Entree (micro)", def_in, "input")
    out_dev = select_device("  Sortie (hp)", def_out, "output")
    print(f"\n  Entree : device[{in_dev}]  Sortie : device[{out_dev}]")

    tests = [
        ("Imports",         lambda: test_imports()),
        ("Sortie audio",    lambda: test_audio_play(out_dev)),
        ("Entree audio",    lambda: test_audio_record(in_dev)),
        ("Fichiers config",  lambda: test_config_files()),
        ("Parsing commandes", lambda: test_command_parser()),
        ("TTS",             lambda: test_tts()),
        ("Chat IA",         lambda: test_chat()),
        ("API STT distante", lambda: test_stt_api()),
    ]
    if not cloud:
        tests.append(("Ollama local", lambda: test_ollama()))

    results = []
    for name, func in tests:
        try:
            results.append((name, func()))
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Bilan
    print(f"\n{'=' * 60}")
    print(f"  BILAN")
    print(f"{'=' * 60}")
    passed = sum(1 for _, s in results if s)
    total = len(results)
    for name, success in results:
        print(f"  {'[OK]' if success else '[ERR]'} {name}")
    print(f"\n  {passed}/{total} tests passes")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
