#!/usr/bin/env python3
"""
Voice Control - Application CLI pour contrôler des objets par la voix
Utilise Whisper pour reconnaissance vocale offline
"""
import sys
import os
from pathlib import Path

_proj = Path(__file__).resolve().parent
_venv_python = _proj / "venv" / "bin" / "python"
if _venv_python.is_file():
    _me = sys.executable or "python"
    if os.path.realpath(_me) != os.path.realpath(str(_venv_python)):
        os.execv(str(_venv_python), [str(_venv_python), *sys.argv])

import argparse
import json
import time
import threading
import subprocess
import wave
import datetime
import re
import numpy as np
import select
import fcntl
import os as _os_mod
from typing import Optional

# Ajouter le chemin du projet
sys.path.insert(0, str(_proj))

from voice_recognizer import VoiceRecognizer
from command_parser import CommandParser
from plugin_manager import PluginManager
from conversation_logger import log_user, log_system, log_action


class VoiceControlApp:
    def __init__(self, config_path: str = None, input_device = None, output_device = None, sample_rate: int = None):
        self.config_path = config_path or str(Path(__file__).parent / "config.json")
        self.config = self.load_config()
        self.recognizer = VoiceRecognizer(self.config, input_device, sample_rate or self.config.get("audio", {}).get("sample_rate"))
        self.plugin_manager = PluginManager(self)
        self.parser = CommandParser(self.plugin_manager)
        self._init_plugins()
        self.running = False
        self._last_music_cmd = 0
        self._last_response = ""
        self._last_media_info = None
        self._cancel = threading.Event()
        self._orig_term = None
        self._start_cancel_listener()

    def load_config(self) -> dict:
        """Charge la configuration"""
        default_config = {
            "whisper": {
                "model": "base",
                "language": "fr",
                "device": "cpu"
            },
            "audio": {
                "input_device": None,
                "sample_rate": 44100,
                "chunk_duration": 6
            },
            "wake_word": "bob",
            "ollama_model": "llama-3.3-70b-versatile",
            "groq_api_key": "",
            "openai_api_key": "",
            "stt_endpoint": "",
            "log_level": "INFO",
            "user_location": "Surtainville 50270 France"
        }

        if os.path.exists(self.config_path):
            with open(self.config_path) as f:
                user_config = json.load(f)
                default_config.update(user_config)

        return default_config

    def save_config(self):
        """Sauvegarde la configuration"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def log(self, message: str):
        """Écrit dans le journal"""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("voice_control.log", "a") as f:
            f.write(f"[{ts}] {message}\n")

    def _clear_screen(self):
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    def _clean_for_tts(self, text: str) -> str:
        t = re.sub(r'[=*#\-_{}()\[\]|/\\<>]', ' ', text)
        t = re.sub(r'\s+', ' ', t).strip()
        return t[:200]

    def print_status(self, message: str, status: str = "INFO"):
        """Affiche un message de statut"""
        colors = {
            "INFO": "\033[96m",
            "SUCCESS": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "VOICE": "\033[95m"
        }
        reset = "\033[0m"
        print(f"{colors.get(status, '')}{status}: {message}{reset}")
        self.log(f"{status}: {message}")

    def _ensure_audio(self):
        """Démute le sink PulseAudio par défaut"""
        try:
            import subprocess
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
                           capture_output=True, timeout=5)
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"],
                           capture_output=True, timeout=5)
        except Exception:
            pass

    def _init_plugins(self):
        self._ensure_audio()
        try:
            from plugins.music_player_plugin import MusicPlayerPlugin
            self.plugin_manager.plugins["music"] = MusicPlayerPlugin(self.plugin_manager)
        except Exception as e:
            self.log(f"Erreur chargement plugin musique: {e}")

        try:
            from plugins.audiobook_plugin import AudiobookPlugin
            self.plugin_manager.plugins["audiobook"] = AudiobookPlugin(self.plugin_manager)
        except Exception as e:
            self.log(f"Erreur chargement plugin livre audio: {e}")

        try:
            from plugins.tts_plugin import TTSPlugin
            tts = TTSPlugin(self.plugin_manager)
            self.plugin_manager.setup_tts(tts)
            self.tts = tts
        except Exception as e:
            self.log(f"Erreur chargement TTS: {e}")
            self.tts = None

        self.wake_engine = None
        try:
            from plugins.wake_word_engine import WakeWordEngine
            self.wake_engine = WakeWordEngine(self.config, self.recognizer)
            if self.wake_engine.is_available():
                self.log("Wake word engine: VAD énergétique + Groq STT")
            else:
                self.log("Wake word engine: audio non disponible")
        except Exception as e:
            self.log(f"Wake word engine non disponible: {e}")

        try:
            from plugins.pmu_plugin import PMUPlugin
            self.plugin_manager.plugins["pmu"] = PMUPlugin(self.plugin_manager)
            self.log("Plugin PMU chargé")
        except Exception as e:
            self.log(f"Erreur chargement PMU: {e}")

    def listen_wake_word(self):
        """Écoute le mot de réveil, ou les commandes directes (musique/livre)"""
        import sounddevice as sd
        wake = self.config.get("wake_word", "bob")
        music_stop_re = re.compile(
            r"stop|ar{1,2}[eèêé]t[eèêé]s?|pause|[eé]teins?|tai[st]?[-\s]toi|silence|fin\b"
        )

        while self.running:
            music = self.plugin_manager.plugins.get("music")
            music_playing = music and music.currently_playing
            book = self.plugin_manager.plugins.get("audiobook")
            book_playing = book and book.currently_playing
            any_media = music_playing or book_playing

            if any_media:
                import select as _sel
                import tty as _tty
                import termios as _termios
                sr = self.recognizer.sample_rate or 44100
                chunk = int(sr * 0.5)
                nf = -100.0
                cooldown = 0.0
                _fd = sys.stdin.fileno()
                _old_tty = _termios.tcgetattr(_fd)
                _tty.setraw(_fd)
                try:
                    for _ in range(120):
                        mu = music and music.currently_playing
                        bo = book and book.currently_playing
                        if not self.running or not (mu or bo):
                            break
                        _r, _, _ = _sel.select([sys.stdin], [], [], 0)
                        if _r:
                            _ch = os.read(_fd, 1)
                            if _ch == b'\x00':
                                self.log("Ctrl+Space: stop")
                                self._stop_all_playback()
                                if self.tts:
                                    self.tts.confirm("stop")
                                break
                        recorded = sd.rec(chunk, samplerate=sr, channels=1, dtype=np.float32, device=None)
                        sd.wait()
                        sd.stop()
                        frame = recorded.flatten()
                        rms = float(np.sqrt(np.mean(frame ** 2)))
                        if np.isnan(rms) or rms < 1e-10:
                            rms = 1e-10
                        rms_db = 20 * np.log10(rms)
                        if nf == -100.0:
                            nf = rms_db
                        nf = 0.92 * nf + 0.08 * min(rms_db, nf + 6)
                        now = time.time()
                        if rms_db > nf + 6 and now >= cooldown:
                            cooldown = now + 3.0
                            audio = sd.rec(int(sr * 2), samplerate=sr, channels=1, dtype=np.float32, device=None)
                            sd.wait()
                            sd.stop()
                            text = self.recognizer.recognize(audio.flatten())
                            if text:
                                tl = text.lower()
                                self.log(f"Lecture directe: {text}")
                                if music_stop_re.search(tl):
                                    self.log(f"Stop lecture: {text}")
                                    if mu:
                                        music.stop()
                                    if bo:
                                        book.stop()
                                    self.tts.confirm("stop")
                                elif wake.lower() in tl:
                                    print(f"\r  \033[92mMot de détection '{wake}' OK\033[0m" + " " * 30)
                                    self.log(f"Wake word detected: {wake}")
                                    if self.tts:
                                        self.tts.speak("Je vous écoute, parlez", wait=True)
                                    return True
                        time.sleep(0.05)
                finally:
                    _termios.tcsetattr(_fd, _termios.TCSADRAIN, _old_tty)
                # Après la boucle média, affiche un statut si la lecture est finie
                mu = music and music.currently_playing
                bo = book and book.currently_playing
                if not mu and not bo:
                    print()
                    self.print_status("Fin de la lecture - Dites 'bob' pour une commande", "INFO")
                continue

            if self.wake_engine and self.wake_engine.is_available():
                result = self.wake_engine.wait_for_wake_word(wake, music_playing=False)
            else:
                result = self.recognizer.listen_for_wake_word(wake, music_playing=False)
            if result:
                print(f"\r  \033[92mMot de détection '{wake}' OK\033[0m" + " " * 30)
                self.log(f"Wake word detected: {wake}")
                if self.tts:
                    self.tts.speak("Je vous écoute, parlez", wait=True)
                return True
        return False

    def _stop_all_playback(self):
        music = self.plugin_manager.plugins.get("music")
        book = self.plugin_manager.plugins.get("audiobook")
        stopped = (music and music.currently_playing) or (book and book.currently_playing)
        if music and music.currently_playing:
            music.stop()
        if book and book.currently_playing:
            book.stop()
        if stopped:
            self.print_status("Stop", "SUCCESS")
        return stopped

    def _start_cancel_listener(self):
        """Lance un thread qui écoute Echap et Ctrl+Space pour annuler toute action.
           Passe le terminal en mode non-canonique (cbreak) pour détecter les touches individuelles."""
        import termios as _termios
        import tty as _tty
        _fd = sys.stdin.fileno()
        try:
            self._orig_term = _termios.tcgetattr(_fd)
            _tty.setcbreak(_fd)
            _fl = fcntl.fcntl(_fd, fcntl.F_GETFL)
            fcntl.fcntl(_fd, fcntl.F_SETFL, _fl | _os_mod.O_NONBLOCK)
        except Exception:
            pass

        self._cancel_stop = threading.Event()

        def _listen():
            _fd = sys.stdin.fileno()
            while not self._cancel_stop.is_set():
                try:
                    _r, _, _ = select.select([sys.stdin], [], [], 0.2)
                    if _r:
                        _ch = _os_mod.read(_fd, 1)
                        if _ch in (b'\x1b', b'\x00'):
                            self._cancel.set()
                            if self.tts:
                                self.tts.stop()
                            self._stop_all_playback()
                except (ValueError, TypeError):
                    break
                except Exception:
                    pass

        self._cancel_listener = threading.Thread(target=_listen, daemon=True)
        self._cancel_listener.start()

    def _blocking_input(self, prompt: str = "") -> str:
        """input() en mode canonique (restaure le temps de la saisie, puis repasse en cbreak)"""
        import termios as _termios
        import tty as _tty
        _fd = sys.stdin.fileno()
        if self._orig_term:
            try:
                _termios.tcsetattr(_fd, _termios.TCSADRAIN, self._orig_term)
                _fl = fcntl.fcntl(_fd, fcntl.F_GETFL)
                fcntl.fcntl(_fd, fcntl.F_SETFL, _fl & ~_os_mod.O_NONBLOCK)
            except Exception:
                pass
        try:
            return input(prompt)
        finally:
            try:
                _tty.setcbreak(_fd)
                _fl = fcntl.fcntl(_fd, fcntl.F_GETFL)
                fcntl.fcntl(_fd, fcntl.F_SETFL, _fl | _os_mod.O_NONBLOCK)
            except Exception:
                pass

    def _is_cancelled(self) -> bool:
        """Vérifie si une annulation a été demandée"""
        if self._cancel.is_set():
            self._cancel.clear()
            return True
        return False

    def cancel(self, msg: str = "Commande annulée"):
        """Annule la commande en cours"""
        self._cancel.set()
        if self.tts:
            self.tts.stop()
        self._stop_all_playback()
        self.print_status(msg, "WARNING")
        if self.tts:
            self.tts.speak(msg, wait=False)

    def _speak_with_cancel(self, msg: str) -> bool:
        """Parle avec annulation possible (Escape + 'annule' vocal) - retourne False si annulé"""
        if not self.tts or not self.tts.is_available():
            return True
        self._last_response = msg
        cancel_re = re.compile(r"\bannul[ée]\b|\bannulation\b|\bcancel\b|\babort\b", re.IGNORECASE)

        t = threading.Thread(target=self.tts.speak, args=(msg, True), daemon=True)
        t.start()

        import sounddevice as sd
        sd.stop()  # nettoie tout stream résiduel
        sr = self.recognizer.sample_rate or 16000
        chunk = int(sr * 0.6)
        while t.is_alive():
            if self._is_cancelled():
                sd.stop()
                self.tts.stop()
                self.print_status("Commande annulée", "WARNING")
                t.join(1)
                return False
            try:
                recorded = sd.rec(chunk, samplerate=sr, channels=1, dtype=np.float32, device=None)
                sd.wait()
                sd.stop()
                audio = recorded.flatten()
                rms = float(np.sqrt(np.mean(audio ** 2)))
                if rms > 0.015:
                    text = self.recognizer.recognize(audio)
                    if text and cancel_re.search(text):
                        self.tts.stop()
                        self.print_status("Commande annulée", "WARNING")
                        self.tts.speak("Commande annulée", wait=False)
                        t.join(1)
                        return False
            except Exception:
                pass
            t.join(0.3)
        return True

    def _speak_with_cancel_and_listen(self, msg: str) -> Optional[str]:
        """Parle avec annulation, puis écoute une commande vocale. Retourne le texte ou None si annulé."""
        if not self._speak_with_cancel(msg):
            return None
        self.print_status("À votre écoute...", "VOICE")
        self.log("Recording after speak...")
        audio_data = self.recognizer.listen(self.config["audio"]["chunk_duration"], show_vu=True)
        if audio_data is None:
            return None
        text = self.recognizer.recognize(audio_data)
        return text

    def process_command(self):
        """Écoute et traite une commande vocale"""
        self._cancel.clear()  # nettoie un éventuel vieux cancel
        self.print_status("À votre écoute...", "VOICE")
        self.log("Recording command...")
        audio_data = self.recognizer.listen(self.config["audio"]["chunk_duration"], show_vu=True)

        if audio_data is None:
            self.print_status("Erreur d'enregistrement", "WARNING")
            return

        self.print_status("Reconnaissance en cours...", "INFO")
        text = self.recognizer.recognize(audio_data)

        if text:
            log_user(text, source="voice")
            self.print_status(f"Vous avez dit: \"{text}\"", "VOICE")
            self.log(f"Commande reconnue: {text}")
            self.execute_command(text)
        else:
            self.print_status("Je n'ai pas compris", "WARNING")
            self.log("Commande non reconnue (silence ou erreur)")

    def execute_command(self, text: str):
        """Exécute une commande"""
        if self._is_cancelled():
            return
        result = self.parser.parse(text)

        if not result["success"] and not result.get("need_input"):
            # Réponse unique via chat, sans entrer dans la boucle persistante
            if self.plugin_manager.chat_agent and self.plugin_manager.chat_agent.is_available():
                response = self.plugin_manager.chat_agent.chat(text, voice=False)
                if response:
                    log_system(response)
                    print(f"\n  \033[92m---\033[0m")
                    for line in response.split("\n"):
                        print(f"  {line}")
                    print(f"  \033[92m---\033[0m\n")
                    self.log(f"Chat: {text} -> {response}")
                    self._speak_with_cancel(response)
            else:
                self.print_status(f"Commande non reconnue", "WARNING")
                self.log(f"Commande non reconnue: {text}")
                self.tts.confirm("error")
            return

        action = result.get("action", "")
        self.log(f"Action: {action}")

        # Annulation
        if action == "cancel":
            self.cancel()
            return

        # Rejouer la dernière réponse
        if action == "repeat":
            if self._last_media_info:
                music = self.plugin_manager.plugins.get("music")
                if music and music.play(**self._last_media_info).get("success"):
                    self.print_status("Relecture de la vidéo", "SUCCESS")
                else:
                    self.tts.speak("Impossible de relire la vidéo")
            elif self._last_response:
                self._speak_with_cancel(self._last_response)
            else:
                self.tts.confirm("error")
            return

        # Mode Chat Agent
        if action == "chat" or result.get("need_input"):
            if self.plugin_manager.chat_agent and self.plugin_manager.chat_agent.is_available():
                self.print_status("Mode conversation - Dites 'quit' pour sortir", "INFO")
                if not self._speak_with_cancel("Oui, je t'écoute"):
                    return
                self._chat_mode(text)
            else:
                self._speak_with_cancel("Le chat n'est pas disponible. Installe Ollama ou configure une clé API.")
                self.print_status("Chat non disponible (installez Ollama)", "WARNING")
            return

        if action == "chat_reset":
            if self.plugin_manager.chat_agent:
                self.plugin_manager.chat_agent.reset()
                self._speak_with_cancel("Conversation réinitialisée")
            else:
                self._speak_with_cancel("Le chat n'est pas disponible")
            return

        if action == "weather":
            res = result.get("result", {})
            if "error" in res:
                log_system(res["error"], source="weather")
                self.print_status(res["error"], "WARNING")
                self._speak_with_cancel(res["error"])
            elif "forecast" in res:
                msg = res["forecast"]
                log_system(msg, source="weather")
                if "Prévisions." in msg:
                    parts = msg.split("Prévisions.", 1)
                    current = parts[0].strip()
                    forecast = parts[1].strip().rstrip(".")
                    print(f"\n  \033[96mMétéo\033[0m")
                    print(f"  {current}")
                    print(f"  \033[93mPrévisions\033[0m")
                    for day in forecast.split(". "):
                        day = day.strip()
                        if day:
                            print(f"    {day}")
                    print()
                else:
                    self.print_status(msg, "INFO")
                self._speak_with_cancel(msg)
            return

        if action in ("pronostic_pmu", "resultat_pmu"):
            res = result.get("result", {})
            if action == "resultat_pmu":
                self.print_status("Recherche résultat PMU...", "INFO")
                pmu = self.plugin_manager.plugins.get("pmu")
                if pmu:
                    res2 = pmu.zone_turf_resultat()
                else:
                    res2 = {"success": False, "message": "Plugin PMU non disponible"}
                if res2.get("success"):
                    msg = res2["message"]
                    log_system(msg, source="pmu")
                    self._clear_screen()
                    print(msg)
                    lines = msg.split('\n')
                    top = self._clean_for_tts(lines[0] if lines else msg)
                    if not self._speak_with_cancel(top):
                        return
                else:
                    if res.get("success"):
                        msg = res["message"]
                        log_system(msg, source="pmu")
                        self._clear_screen()
                        print(msg)
                        top = self._clean_for_tts(msg.split('\n')[0])
                        if not self._speak_with_cancel(top):
                            return
                    else:
                        if not self._speak_with_cancel("Aucun résultat trouvé"):
                            return
            elif action == "pronostic_pmu":
                self.print_status("Recherche pronostics multi-sources...", "INFO")
                pmu = self.plugin_manager.plugins.get("pmu")
                if pmu:
                    res2 = pmu.pronostic_complet()
                else:
                    res2 = {"success": False, "message": "Plugin PMU non disponible"}
                if res2.get("success"):
                    msg = res2["message"]
                    log_system(msg, source="pmu")
                    self._clear_screen()
                    print(msg)
                    top = self._clean_for_tts(msg.split('\n')[0])
                    if not self._speak_with_cancel(f"Pronostic: {top}"):
                        return
                else:
                    err = res2.get("message", "Aucun pronostic trouvé")
                    log_system(err, source="pmu")
                    self._clear_screen()
                    print(err)
                    if not self._speak_with_cancel(err):
                        return
            elif not res.get("success"):
                self.print_status(f"PMU: {res.get('message', '')}", "WARNING")
                self._speak_with_cancel(res.get("message", "Erreur PMU"))
            return

        if action == "set_volume":
            level = result.get("result", {}).get("level", 50)
            self._speak_with_cancel(f"Volume réglé à {level} pour cent")
            return

        if result["success"]:
            self.print_status(f"Commande exécutée: {action}", "SUCCESS")

            # Réponse vocale
            if action == "music_stop":
                m = self.plugin_manager.plugins.get("music")
                if m: m.stop()
            elif action == "audiobook_stop":
                b = self.plugin_manager.plugins.get("audiobook")
                if b: b.stop()
            if action.startswith("music_") or action.startswith("audiobook_"):
                r = result.get("result", {})
                self.log(f"{action} result: {r}")
                self._tts_response(action, r)
            elif "light_on" in action or "bulb_on" in action or "tv_on" in action:
                self.tts.confirm("on")
            elif "light_off" in action or "bulb_off" in action or "tv_off" in action:
                self.tts.confirm("off")
        else:
            self.print_status(f"Commande non reconnue", "WARNING")
            self.tts.confirm("error")

    def _tts_response(self, action: str, result: dict):
        """Génère une réponse TTS appropriée"""
        if not result:
            return

        if action == "music_now":
            if "now_playing" in result:
                self._speak_with_cancel(f"Actuellement, {result['now_playing']}")
        elif action == "music_stop":
            self.tts.confirm("stop")
        elif action == "music_next":
            self.tts.confirm("next")
        elif action == "music_prev":
            self.tts.confirm("prev")
        elif action == "music_play":
            res = result.get("result", {})
            if "error" in res:
                if res["error"] == "Stop":
                    self.tts.confirm("stop")
                else:
                    self._speak_with_cancel(f"Désolé, {res['error']}")
            elif "playing" in res:
                dur = res.get("duration", "")
                msg = f"Je joue {res['playing']}"
                if dur:
                    msg += f", durée {dur}"
                self._speak_with_cancel(msg)
                music = self.plugin_manager.plugins.get("music")
                if music and music.currently_playing:
                    self._last_media_info = {"url": music.currently_playing.get("url")}
        elif action == "music_play_genre":
            res = result.get("result", {})
            if "error" in res:
                self._speak_with_cancel(f"Désolé, {res['error']}")
            elif "playing" in res:
                self._speak_with_cancel(f"Je lance {res['playing']}")
        elif action == "audiobook_play":
            res = result.get("result", {})
            if "error" in res:
                self.log(f"Audiobook error: {res['error']}")
                if res["error"] == "Stop":
                    self.tts.confirm("stop")
                else:
                    self._speak_with_cancel(f"Désolé, {res['error']}")
            elif "playing" in res:
                dur = res.get("duration", "")
                msg = f"Je lis {res['playing']}"
                if dur:
                    msg += f", durée {dur}"
                self._speak_with_cancel(msg)

    def _play_beep(self):
        beep_path = os.path.join(os.path.dirname(__file__), 'beep.wav')
        if os.path.exists(beep_path):
            try:
                subprocess.run(['aplay', '-q', beep_path], timeout=2, capture_output=True)
            except Exception:
                pass

    def _is_echo(self, text: str, last_response: str) -> bool:
        """Détecte si le texte transcrit est un écho de la dernière réponse"""
        if not last_response:
            return False
        t = text.lower().strip()
        r = last_response.lower().strip()
        # Si le texte est contenu dans la réponse (écho partiel)
        if len(t) > 5 and t in r:
            return True
        # Chevauchement de mots significatif
        tw = set(t.split())
        rw = set(r.split())
        if len(tw) > 2 and len(rw) > 2:
            overlap = len(tw & rw) / max(len(tw), len(rw))
            if overlap > 0.6:
                return True
        return False

    def _chat_mode(self, initial_text: str = ""):
        """Mode conversationnel avec le LLM - boucle continue sans echo"""
        agent = self.plugin_manager.chat_agent
        quit_words = ["quit", "sortir", "sort", "au revoir", "ciao", "bye", "annule"]
        last_response = ""

        if initial_text:
            if any(q in initial_text.lower() for q in quit_words):
                return
                response = agent.chat(initial_text, voice=False)
                if response:
                    last_response = response
                    print(f"\n  \033[92m---\033[0m")
                    for line in response.split("\n"):
                        print(f"  {line}")
                    print(f"  \033[92m---\033[0m\n")
                    self._speak_with_cancel(response)
                    self.log(f"bob: {response}")

        while self.running:
            if self._is_cancelled():
                self.log("Chat mode: cancel requested")
                self.tts.speak("Commande annulée")
                break
            try:
                time.sleep(1.5)
                self.print_status("À votre écoute (mode chat)...", "VOICE")
                self.log("Chat mode: recording...")
                audio = self.recognizer.listen(9, show_vu=True)

                if audio is None:
                    continue

                text = self.recognizer.recognize(audio)
                if not text or len(text) < 3:
                    continue

                if self._is_echo(text, last_response):
                    self.log(f"Chat: écho ignoré: {text}")
                    continue

                log_user(text, source="voice")
                self.print_status(f"Vous: {text}", "VOICE")
                self.log(f"Chat: {text}")

                if any(q in text.lower() for q in quit_words):
                    self.log("Chat mode: quit requested")
                    self.tts.speak("Au revoir !")
                    break

                response = agent.chat(text, voice=False)
                if response:
                    log_system(response)
                    last_response = response
                    print(f"\n  \033[92m---\033[0m")
                    for line in response.split("\n"):
                        print(f"  {line}")
                    print(f"  \033[92m---\033[0m\n")
                    if not self._speak_with_cancel(response):
                        break
                    self.log(f"bob: {response}")

            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"Erreur chat: {e}")

    def list_audio_devices(self):
        """Liste les périphériques audio disponibles"""
        try:
            from voice_recognizer import sd
        except ImportError:
            print("Audio non disponible")
            return
        if sd is None:
            print("Audio non disponible")
            return
        devices = sd.query_devices()
        self.print_status("Périphériques audio:", "INFO")
        print(f"{'Index':<6} {'Nom':<50} {'In':<4} {'Out':<4}")
        print("-" * 64)
        for i, dev in enumerate(devices):
            marker = "*" if i == sd.default.device[0] else " "
            print(f"  {marker} {i:<4} {dev['name']:<50} {dev['max_input_channels']:<4} {dev['max_output_channels']:<4}")

    def _resolve_device(self, dev):
        """Convertit un device en entier si possible, sinon le passe tel quel"""
        if dev is None:
            return None
        try:
            return int(dev)
        except (ValueError, TypeError):
            return dev

    def _detect_sample_rate(self, device):
        """Détecte le sample rate natif d'un périphérique d'entrée"""
        try:
            from voice_recognizer import sd
            if sd is None:
                return None
            dev_id = self._resolve_device(device)
            if dev_id is None:
                dev_id = sd.default.device[0]
            info = sd.query_devices(dev_id)
            sr = int(info['default_samplerate'])
            self.print_status(f"Sample rate natif détecté : {sr} Hz", "INFO")
            return sr
        except Exception:
            return None

    def _input_with_timeout(self, prompt, timeout=3):
        import select
        sys.stdout.write(prompt)
        sys.stdout.flush()
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if r:
            return sys.stdin.readline().strip().lower()
        return None

    def _select_ollama_model(self):
        """Sélectionne le modèle de chat au démarrage (Groq > Ollama)"""
        groq_key = self.config.get("groq_api_key", "")
        if groq_key and groq_key.startswith("gsk_"):
            self.print_status("Mode 100% cloud detecte (Groq).", "INFO")
            self._select_groq_model()
            return

        import requests
        try:
            r = requests.get("http://localhost:11434/api/version", timeout=2)
            if r.status_code != 200:
                self.print_status("Ollama ne répond pas correctement", "WARNING")
                return
        except requests.exceptions.ConnectionError:
            self.print_status("Ollama n'est pas lancé (lancez 'ollama serve')", "WARNING")
            return

        # Récupère la liste des modèles
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            models = r.json().get("models", [])
        except Exception as e:
            self.print_status(f"Erreur de récupération des modèles: {e}", "WARNING")
            return

        model_names = sorted(set(m["name"].split(":")[0] if ":" in m["name"] else m["name"] for m in models))

        if model_names:
            print("\n" + "=" * 50)
            print("  Modèles Ollama disponibles :")
            for i, name in enumerate(model_names, 1):
                print(f"    [{i}] {name}")
            print(f"    [p] Télécharger un nouveau modèle")
            print(f"    [d] Utiliser le modèle par défaut (llama3.2)")
            print("=" * 50)

            while True:
                choice = self._input_with_timeout("Choix > ", timeout=3)
                if choice is None:
                    print(" (délai dépassé, modèle par défaut)")
                    selected = "llama3.2"
                    break
                if choice == 'd':
                    selected = "llama3.2"
                    break
                if choice == 'p':
                    selected = self._pull_ollama_model()
                    break
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(model_names):
                        selected = model_names[idx]
                        break
                except ValueError:
                    pass
                print("  Choix invalide")
        else:
            print("\nAucun modèle Ollama trouvé.")
            selected = self._pull_ollama_model()

        if selected:
            self.config["ollama_model"] = selected
            if self.plugin_manager.chat_agent:
                self.plugin_manager.chat_agent.set_model(selected)
                self.plugin_manager.chat_agent.api_type = "ollama"
            self.save_config()
            self.print_status(f"Modèle sélectionné : {selected}", "SUCCESS")
            self._verify_model_loaded(selected)
        else:
            self.print_status("Aucun modèle sélectionné, utilisation du défaut", "INFO")

    def _select_groq_model(self):
        """Propose les modèles Groq (chat cloud gratuit)"""
        groq_models = [
            ("llama-3.3-70b-versatile",              "Llama 3.3 70B - Ultra performant (recommandé)"),
            ("meta-llama/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B - Nouveau"),
            ("qwen/qwen3-32b",                       "Qwen 3 32B - Performant"),
            ("groq/compound",                        "Groq Compound - Généraliste"),
            ("groq/compound-mini",                   "Groq Compound Mini - Léger"),
            ("openai/gpt-oss-20b",                   "OpenAI GPT-OSS 20B - Rapide"),
            ("openai/gpt-oss-120b",                  "OpenAI GPT-OSS 120B - Puissant"),
            ("allam-2-7b",                           "Allam 2 7B - Multilingue"),
            ("llama-3.1-8b-instant",                 "Llama 3.1 8B - Très rapide"),
        ]

        print("\n" + "=" * 55)
        print("  Modèles Groq disponibles (chat cloud gratuit) :")
        for i, (model_id, desc) in enumerate(groq_models, 1):
            print(f"    [{i}] {desc}")
        print(f"    [c] Personnalisé (taper l'ID du modèle)")
        print(f"    [d] Défaut (llama-3.3-70b-versatile)")
        print("=" * 55)

        while True:
            choice = self._input_with_timeout("Choix > ", timeout=3)
            if choice is None:
                print(" (délai dépassé, modèle par défaut)")
                selected = "llama-3.3-70b-versatile"
                break
            if choice == 'd':
                selected = "llama-3.3-70b-versatile"
                break
            if choice == 'c':
                custom = self._blocking_input("  ID du modèle > ").strip()
                if custom:
                    selected = custom
                    break
                print("  ID invalide")
                continue
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(groq_models):
                    selected = groq_models[idx][0]
                    break
            except ValueError:
                pass
            print("  Choix invalide")

        self.config["ollama_model"] = selected
        if self.plugin_manager.chat_agent:
            self.plugin_manager.chat_agent.set_model(selected)
            self.plugin_manager.chat_agent.api_type = "groq"
        self.save_config()
        self.print_status(f"Modèle Groq sélectionné : {selected}", "SUCCESS")

    def _pull_ollama_model(self):
        """Propose de télécharger un modèle Ollama"""
        recommended = [
            "llama3.2",
            "qwen2.5:0.5b",
            "qwen2.5:1.5b",
            "phi3:mini",
            "mistral"
        ]

        print("\nModèles recommandés :")
        for i, name in enumerate(recommended, 1):
            print(f"  [{i}] {name}")
        print("  [a] Annuler")
        print("─" * 40)

        while True:
            choice = self._blocking_input("Quel modèle télécharger ? > ").strip().lower()
            if choice == 'a':
                return None
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(recommended):
                    model_name = recommended[idx]
                    print(f"\nTéléchargement de {model_name}... (cela peut prendre plusieurs minutes)")
                    try:
                        if subprocess.run(["ollama", "pull", model_name], timeout=600).returncode == 0:
                            self.print_status(f"Modèle {model_name} téléchargé !", "SUCCESS")
                            return model_name
                        else:
                            self.print_status(f"Échec du téléchargement de {model_name}", "ERROR")
                            return None
                    except FileNotFoundError:
                        self.print_status("'ollama pull' non trouvé. Assurez-vous qu'Ollama est installé.", "ERROR")
                        return None
            except (ValueError, IndexError):
                pass

    def _verify_model_loaded(self, model_name: str):
        """Vérifie que le modèle répond via un appel API Ollama"""
        import requests
        self.print_status(f"Vérification du modèle {model_name}...", "INFO")
        try:
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": model_name, "prompt": "dis bonjour", "stream": False},
                timeout=30
            )
            if r.status_code == 200:
                response = r.json().get("response", "").strip()
                if response:
                    self.print_status(f"✓ Modèle chargé : \"{response[:80]}\"", "SUCCESS")
                else:
                    self.print_status("✓ Modèle chargé (réponse vide mais OK)", "SUCCESS")
            else:
                self.print_status(f"⚠ Modèle sélectionné mais ne répond pas (code {r.status_code})", "WARNING")
        except requests.exceptions.Timeout:
            self.print_status("⚠ Modèle sélectionné mais lent à répondre (timeout 30s)", "WARNING")
        except Exception as e:
            self.print_status(f"⚠ Modèle sélectionné, mais erreur de vérification : {e}", "WARNING")

    def _spinner(self, stop, label):
        """Animation spinner dans un thread séparé"""
        chars = "-\\|/"
        i = 0
        while not stop.is_set():
            print(f"\r  [{chars[i % len(chars)]}] {label}... ", end='', flush=True)
            stop.wait(0.1)
            i += 1

    def _wait_with_spinner(self, label, blocking_call):
        """Exécute blocking_call avec un spinner animé"""
        stop = threading.Event()
        t = threading.Thread(target=self._spinner, args=(stop, label), daemon=True)
        t.start()
        try:
            blocking_call()
        finally:
            stop.set()
            t.join(0.5)
            print("\r" + " " * (len(label) + 10) + "\r", end='', flush=True)

    def _show_alsa_devices(self):
        """Affiche les cartes ALSA (aplay/arecord)"""
        print("\n--- Cartes ALSA ---")
        for cmd, label in [("aplay", "PLAYBACK"), ("arecord", "CAPTURE")]:
            try:
                r = subprocess.run([cmd, "-l"], capture_output=True, text=True, timeout=5)
                out = (r.stdout or r.stderr).strip()
                if out:
                    print(f"  [{label}]")
                    for line in out.split("\n"):
                        print(f"    {line}")
                else:
                    print(f"  [{label}] Aucune carte")
            except FileNotFoundError:
                print(f"  [{label}] {cmd} non installe")
            except Exception as e:
                print(f"  [{label}] Erreur: {e}")

    def _make_wav(self, path, duration=1.5, freq=440, sr=48000):
        """Crée un fichier WAV avec un sinus 6 canaux"""
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        s = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
        frames = np.column_stack([s] * 6).tobytes()
        with wave.open(path, 'w') as wf:
            wf.setnchannels(6)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(frames)

    def _test_alsa(self, out_dev, in_dev):
        """Test audio via speaker-test / arecord / aplay"""
        wav_path = "/tmp/voice_control_test.wav"
        rec_path = "/tmp/voice_control_rec.wav"

        # Test sortie 1: speaker-test (fiable sur ce matos)
        print()
        self.print_status("→ Test SORTIE (speaker-test)", "INFO")
        try:
            self._wait_with_spinner("speaker-test 6 canaux", lambda: subprocess.run(
                ["speaker-test", "-t", "wav", "-c", "6", "-l", "1", "-r", "48000"],
                timeout=8, capture_output=True))
            self.print_status("✓ Test speaker-test reussi", "SUCCESS")
        except subprocess.TimeoutExpired:
            self.print_status("X Test speaker-test: timeout", "ERROR")
        except FileNotFoundError:
            self.print_status("speaker-test non installe", "WARNING")
        except Exception as e:
            self.print_status(f"X Test speaker-test: {e}", "ERROR")

        # Test sortie 2: aplay avec WAV 6 canaux
        print()
        self.print_status("→ Test SORTIE (aplay 6ch)", "INFO")
        try:
            self._make_wav(wav_path)
            self._wait_with_spinner("aplay 6 canaux", lambda: subprocess.run(["aplay", "-q", wav_path], timeout=5))
            self.print_status("✓ Test aplay reussi", "SUCCESS")
        except FileNotFoundError:
            self.print_status("aplay non installe", "WARNING")
        except subprocess.TimeoutExpired:
            self.print_status("X Test aplay: timeout", "ERROR")
        except Exception as e:
            self.print_status(f"X Test aplay: {e}", "ERROR")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

        # Test entree + sortie
        print()
        self.print_status("→ Test ENTREE (arecord) + rejeu", "INFO")
        try:
            self.print_status("Parlez dans le micro (2s)...", "VOICE")
            self._wait_with_spinner("arecord 2s", lambda: subprocess.run(
                ["arecord", "-q", "-d", "2", "-f", "cd", "-c", "1", rec_path], timeout=10))
            self.print_status("Lecture de l'enregistrement...", "INFO")
            self._wait_with_spinner("aplay playback", lambda: subprocess.run(["aplay", "-q", rec_path], timeout=10))
            self.print_status("✓ Test arecord + aplay reussi", "SUCCESS")
        except FileNotFoundError:
            self.print_status("arecord non installe", "WARNING")
        except subprocess.TimeoutExpired:
            self.print_status("X Test arecord: timeout", "ERROR")
        except Exception as e:
            self.print_status(f"X Test arecord: {e}", "ERROR")
        finally:
            for p in [rec_path]:
                if os.path.exists(p):
                    os.remove(p)

    def test_audio_mode(self):
        """Test les périphériques audio sélectionnés"""
        # 1. Infos ALSA
        self._show_alsa_devices()

        # 2. Tests ALSA (aplay/arecord)
        self._test_alsa(None, None)

        # 3. Tests sounddevice
        try:
            from voice_recognizer import sd
        except ImportError:
            self.print_status("sounddevice non installe, tests ignores", "WARNING")
            self._post_test_prompt(None, None)
            return

        in_dev = self._resolve_device(self.input_device) or sd.default.device[0]
        out_dev = self._resolve_device(self.output_device) or sd.default.device[1]

        print("\n" + "=" * 60)
        self.print_status("Configuration sounddevice detaillee", "INFO")
        print("=" * 60)

        for label, dev_id in [("ENTREE (micro)", in_dev), ("SORTIE (hp)", out_dev)]:
            try:
                info = sd.query_devices(dev_id)
                print(f"\n[{label}] device[{dev_id}]")
                print(f"  Nom               : {info['name']}")
                print(f"  Entrees max       : {info['max_input_channels']}")
                print(f"  Sorties max       : {info['max_output_channels']}")
                print(f"  Sample rate defaut : {info['default_samplerate']} Hz")
            except Exception as e:
                self.print_status(f"Erreur {label}: {e}", "ERROR")

        print("\n" + "-" * 40)
        self.print_status("→ Test SORTIE sounddevice", "INFO")
        try:
            info_out = sd.query_devices(out_dev)
            out_ch = info_out['max_output_channels']
            if out_ch == 0:
                self.print_status("Attention: pas de sortie audio sur ce peripherique", "WARNING")
            sr = int(info_out['default_samplerate'])
            t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
            swave = 0.3 * np.sin(2 * np.pi * 440 * t)
            if out_ch > 1:
                swave = np.column_stack([swave] * min(out_ch, 6))
            self._wait_with_spinner("sd.play 440 Hz", lambda: (sd.play(swave, samplerate=sr, device=out_dev), sd.wait()))
            self.print_status("✓ Test sd.play reussi", "SUCCESS")
        except Exception as e:
            self.print_status(f"X Test sd.play: {e}", "ERROR")

        print("\n" + "-" * 40)
        self.print_status("→ Test ENTREE sounddevice", "INFO")
        try:
            sr = int(sd.query_devices(in_dev)['default_samplerate'])
            self.print_status("Parlez dans le micro (2s)...", "VOICE")
            recorded = sd.rec(int(2 * sr), samplerate=sr, channels=1, device=in_dev)
            self._wait_with_spinner("sd.rec 2s", lambda: sd.wait())
            self.print_status("Lecture de l'enregistrement...", "INFO")
            self._wait_with_spinner("sd.play rejoue", lambda: (sd.play(recorded, samplerate=sr, device=out_dev), sd.wait()))
            self.print_status("✓ Test sd.rec reussi", "SUCCESS")
        except Exception as e:
            self.print_status(f"X Test sd.rec: {e}", "ERROR")

        print("\n" + "=" * 60)
        self.print_status("Test audio termine", "SUCCESS")

        # Post-test prompt
        self._post_test_prompt(in_dev, out_dev)

    def _post_test_prompt(self, in_dev, out_dev):
        """Demande à l'utilisateur quoi faire après le test"""
        while True:
            print()
            print("─" * 50)
            print("  [i] Démarrer l'assistant vocal (mode interactif)")
            print("  [l] Lister les périphériques audio disponibles")
            print("  [q] Quitter")
            print("─" * 50)
            try:
                choice = self._blocking_input("Choix > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                break
            if choice in ('i', 'interactif', ''):
                self.print_status("Lancement du mode interactif...", "INFO")
                self.running = True
                self.interactive_mode()
                break
            elif choice in ('l', 'liste', 'list'):
                self.list_audio_devices()
                continue
            else:
                break

    def list_devices(self):
        """Liste les objets connectés"""
        devices = self.plugin_manager.list_devices()
        self.print_status("Objets disponibles:", "INFO")
        for device in devices:
            print(f"  - {device['name']} ({device['type']})")

    def list_commands(self):
        """Liste les commandes disponibles"""
        commands = self.parser.list_commands()
        self.print_status("Commandes disponibles:", "INFO")
        for cmd in commands:
            print(f"  - {cmd}")

    def add_device(self, name: str, device_type: str, config: str):
        """Ajoute un nouvel objet"""
        try:
            config_dict = json.loads(config) if config else {}
            self.plugin_manager.register_device(name, device_type, config_dict)
            self.print_status(f"Objet '{name}' ajouté", "SUCCESS")
        except Exception as e:
            self.print_status(f"Erreur: {e}", "ERROR")

    def interactive_mode(self):
        """Mode interactif avec wake word"""
        self._select_ollama_model()
        wake = self.config.get("wake_word", "bob")
        self.print_status(f"Mode interactif - Dites '{wake}' pour activer (Ctrl+C=stop, 2xCtrl+C=quitter)", "INFO")
        print()

        while self.running:
            try:
                if self.listen_wake_word():
                    time.sleep(0.3)
                    self.process_command()
                time.sleep(0.1)
            except KeyboardInterrupt:
                if self._stop_all_playback():
                    self.print_status("Stop ok - rappuyez sur Ctrl+C pour quitter", "INFO")
                else:
                    self.running = False
                    break

        self._restore_terminal()
        self.print_status("Arrêt du programme", "INFO")

    def test_mode(self):
        """Mode test - texte uniquement"""
        self._select_ollama_model()
        self.print_status("Mode test - Tapez vos commandes:", "INFO")
        print()

        while self.running:
            try:
                text = self._blocking_input("> ")
                if text.strip():
                    if text.lower() == "quit":
                        break
                    log_user(text, source="text")
                    self.execute_command(text)
            except KeyboardInterrupt:
                self.running = False
                break
            except EOFError:
                break

        self._restore_terminal()

    def run(self):
        """Point d'entrée principal"""
        parser = argparse.ArgumentParser(
            description="Voice Control - Contrôle vocal d'objets connectés"
        )
        parser.add_argument(
            "--mode",
            choices=["interactive", "test", "listen", "info"],
            default="interactive",
            help="Mode d'exécution"
        )
        parser.add_argument("--config", help="Fichier de configuration")
        parser.add_argument("--add-device", help="Ajouter un objet")
        parser.add_argument("--device-type", help="Type d'objet (esp32, homeassistant, etc.)")
        parser.add_argument("--device-config", help="Config JSON de l'objet")
        parser.add_argument("--list-devices", action="store_true", help="Liste les objets")
        parser.add_argument("--list-commands", action="store_true", help="Liste les commandes")
        parser.add_argument("--test-text", help="Test avec texte (pas de voix)")
        parser.add_argument("--sample-rate", type=int, default=None, help="Sample rate (e.g. 44100 for USB mics)")
        parser.add_argument("--test-audio", action="store_true", help="Test les périphériques audio (son + micro)")

        args, _ = parser.parse_known_args()

        if args.config:
            self.config_path = args.config

        # Arrêt rapide si juste une info
        if args.list_devices:
            self.list_devices()
            return
        if args.list_commands:
            self.list_commands()
            return

        # Ajouter un objet
        if args.add_device:
            if not args.device_type:
                self.print_status("Type requis pour ajouter un objet", "ERROR")
                return
            self.add_device(args.add_device, args.device_type, args.device_config)
            return

        # Test audio
        if args.test_audio:
            self.test_audio_mode()
            return

        # Config initiale si premier lancement
        if not os.path.exists(self.config_path):
            self.print_status("Configuration initiale...", "INFO")
            self.save_config()

        self.running = True

        # Mode test texte
        if args.mode == "test" or args.test_text:
            if args.test_text:
                self.execute_command(args.test_text)
            else:
                self.test_mode()
        # Mode info
        elif args.mode == "info":
            print("=== Voice Control ===")
            print(f"Wake word: {self.config.get('wake_word', 'bob')}")
            print(f"Whisper model: {self.config['whisper']['model']}")
            self.list_devices()
        # Mode écoule seul
        elif args.mode == "listen":
            self.process_command()
        # Mode interactif (défaut)
        else:
            self.interactive_mode()

        # Restauration du terminal
        self._restore_terminal()


    def _restore_terminal(self):
        """Restaure les réglages originaux du terminal et arrête le listener"""
        import termios as _termios
        if hasattr(self, '_cancel_stop'):
            self._cancel_stop.set()
        try:
            if self._orig_term:
                _termios.tcsetattr(sys.stdin.fileno(), _termios.TCSADRAIN, self._orig_term)
        except Exception:
            pass


if __name__ == "__main__":
    _pre_parser = argparse.ArgumentParser(add_help=False)
    _pre_parser.add_argument("--list-audio-devices", action="store_true")
    _pre_parser.add_argument("--input-device", default=None)
    _pre_parser.add_argument("--output-device", default=None)
    _pre_parser.add_argument("--sample-rate", type=int, default=None)
    _pre_parser.add_argument("--config", default=None)
    _pre_args, _remaining = _pre_parser.parse_known_args()

    if _pre_args.list_audio_devices:
        import sounddevice as _sd
        print("Périphériques audio disponibles:")
        print(f"{'Index':<6} {'Nom':<45} {'In':<4} {'Out':<4} {'HW'}")
        print("-" * 80)
        for i, dev in enumerate(_sd.query_devices()):
            marker = "*" if i in _sd.default.device else " "
            hw = f"hw:{i},0"
            print(f"  {marker} {i:<4} {dev['name']:<45} {dev['max_input_channels']:<4} {dev['max_output_channels']:<4} {hw}")
        print("\nPour sélectionner, utilisez: --input-device 2 --output-device 0")
        print("Ou en format ALSA: --input-device 'hw:2,0' --output-device 'hw:0,0'")
        sys.exit(0)

    app = VoiceControlApp(
        config_path=_pre_args.config,
        input_device=_pre_args.input_device,
        output_device=_pre_args.output_device,
        sample_rate=_pre_args.sample_rate
    )
    app.run()