#!/usr/bin/env python3
"""
TTS Plugin - Synthèse vocale pour réponses
"""

import subprocess
import json
import shutil
import os
from pathlib import Path
from typing import Optional


class TTSPlugin:
    def __init__(self, manager, output_device: int = None):
        self.manager = manager
        self.enabled = True
        self.engine = None
        self.voice = None
        self.rate = 150
        self.volume = 1.0
        self.output_device = output_device
        self._proc: Optional[subprocess.Popen] = None
        self._tmp_file: Optional[str] = None
        self._detect_engine()

    def _detect_engine(self):
        """Détecte le moteur TTS disponible (priorité : gTTS > piper > espeak)"""
        engines = [
            ("gtts", self._check_gtts),
            ("piper", self._check_piper),
            ("espeak", self._check_espeak),
            ("festival", self._check_festival),
        ]

        for name, check_func in engines:
            if check_func():
                self.engine = name
                print(f"TTS: Engine '{name}' sélectionné")
                return

        self.engine = None
        print("TTS: Aucun moteur disponible")

    def _check_piper(self) -> bool:
        """Piper TTS (voix FR naturelle)"""
        if not subprocess.run(['which', 'piper'], capture_output=True).returncode == 0:
            return False
        # Trouve une voix FR si disponible
        voices = list(Path.home().glob(".local/share/piper/voice_*.onnx"))
        if voices:
            self.voice = str(voices[0])
        return True

    def _check_espeak(self) -> bool:
        """eSpeak - rapide mais robotique"""
        return subprocess.run(['which', 'espeak'], capture_output=True).returncode == 0

    def _check_festival(self) -> bool:
        """Festival - qualité moyenne"""
        return subprocess.run(['which', 'festival'], capture_output=True).returncode == 0

    def _check_gtts(self) -> bool:
        """Google TTS - bon mais nécessite internet"""
        try:
            from gtts import gTTS
            return True
        except ImportError:
            return False

    def speak(self, text: str, wait: bool = True) -> bool:
        """Synthétise et joue le texte"""
        if not self.enabled or not text:
            return False

        try:
            if self.engine == "piper":
                return self._speak_piper(text, wait)
            elif self.engine == "espeak":
                return self._speak_espeak(text, wait)
            elif self.engine == "festival":
                return self._speak_festival(text, wait)
            elif self.engine == "gtts":
                return self._speak_gtts(text, wait)
            else:
                return False
        except Exception as e:
            print(f"TTS error: {e}")
            return False

    def set_output_device(self, device_index: int):
        """Règle le périphérique de sortie"""
        self.output_device = device_index

    def _get_aplay_device(self) -> list:
        """Retourne les arguments aplay pour le device de sortie"""
        if self.output_device is not None:
            return ['aplay', '-D', f'plughw:{self.output_device},0']
        return ['aplay']

    def _speak_piper(self, text: str, wait: bool) -> bool:
        """Piper TTS"""
        if not self.voice:
            return False

        try:
            self.stop()
            process = subprocess.Popen(
                ['piper', '--voice', self.voice, '--processor', 'espeak'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            aplay_cmd = self._get_aplay_device()
            self._proc = subprocess.Popen(aplay_cmd, stdin=process.stdout, stderr=subprocess.DEVNULL)
            process.communicate(input=text.encode('utf-8'), timeout=10)
            if wait:
                self._proc.wait()
            return (self._proc.returncode or 0) == 0
        except:
            return False

        try:
            self.stop()  # arrête la lecture précédente si elle traîne
            process = subprocess.Popen(
                ['piper', '--voice', self.voice, '--processor', 'espeak'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            aplay_cmd = self._get_aplay_device()
            self._proc = subprocess.Popen(aplay_cmd, stdin=process.stdout, stderr=subprocess.DEVNULL)
            process.communicate(input=text.encode('utf-8'), timeout=10)
            if wait:
                self._proc.wait()
            return (self._proc.returncode or 0) == 0
        except:
            return False

    def _speak_espeak(self, text: str, wait: bool) -> bool:
        """eSpeak TTS"""
        cmd = ['espeak', '-v', 'fr', '-s', str(self.rate), '--stdout', text]
        aplay_cmd = self._get_aplay_device()
        try:
            self.stop()
            echo = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._proc = subprocess.Popen(aplay_cmd, stdin=echo.stdout, stderr=subprocess.DEVNULL)
            echo.stdout.close()
            if wait:
                self._proc.wait()
            return (self._proc.returncode or 0) == 0
        except:
            return False

    def _speak_festival(self, text: str, wait: bool) -> bool:
        """Festival TTS"""
        self.stop()
        cmd = ['festival', '--tts']
        if wait:
            echo = subprocess.Popen(['echo', text], stdout=subprocess.PIPE)
            self._proc = subprocess.Popen(cmd, stdin=echo.stdout, capture_output=True)
            return self._proc.wait() == 0
        else:
            subprocess.Popen(['echo', text], stdout=subprocess.PIPE).stdout.close()
            subprocess.Popen(cmd)
            return True

    def _speak_gtts(self, text: str, wait: bool) -> bool:
        """Google TTS (gtts) - voix féminine naturelle"""
        from gtts import gTTS
        import tempfile

        try:
            self.stop()
            self._tmp_file = None
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp.close()
            self._tmp_file = tmp.name
            tts = gTTS(text=text, lang='fr', slow=False)
            with open(self._tmp_file, 'wb') as f:
                tts.write_to_fp(f)

            player = 'ffplay'
            if not shutil.which('ffplay'):
                player = 'mpv'
            if player == 'ffplay':
                cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', self._tmp_file]
            else:
                cmd = ['mpv', '--no-video', '--really-quiet', self._tmp_file]
            self._proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if wait:
                self._proc.wait()
            self._cleanup_tmp()
            return (self._proc.returncode or 0) == 0
        except Exception as e:
            print(f"gtts error: {e}")
            self._cleanup_tmp()
            return False

    def _cleanup_tmp(self):
        """Nettoie le fichier temporaire"""
        if self._tmp_file:
            try:
                os.unlink(self._tmp_file)
            except Exception:
                pass
            self._tmp_file = None

    def speak_async(self, text: str):
        """Parle sans attendre"""
        return self.speak(text, wait=False)

    def set_rate(self, rate: int):
        """Règle la vitesse (mots/minute)"""
        self.rate = max(80, min(300, rate))

    def set_voice(self, voice: str):
        """Change la voix"""
        self.voice = voice

    def is_available(self) -> bool:
        """Vérifie si TTS est disponible"""
        return self.engine is not None

    def stop(self):
        """Arrête immédiatement la lecture en cours et nettoie"""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.kill()
                self._proc.wait(timeout=1)
            except Exception:
                pass
            self._proc = None
        self._cleanup_tmp()

    # === Réponses prédéfinies ===
    def confirm(self, action: str) -> bool:
        """Confirme une action"""
        responses = {
            "on": "C'est fait, allumé",
            "off": "C'est fait, éteint",
            "play": "Je joue",
            "stop": "Musique stoppée",
            "next": "Piste suivante",
            "prev": "Piste précédente",
            "error": "Désolé, impossible",
        }
        return self.speak(responses.get(action, "OK"))

    def announce(self, message: str):
        """Annonce un message"""
        return self.speak(message)