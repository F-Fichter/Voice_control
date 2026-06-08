#!/usr/bin/env python3
"""
Voice Recognizer - Reconnaissance vocale Whisper optimisé pour Orange Pi 2W (4Go RAM)
"""

import io
import gc
import wave
import time
import numpy as np
from typing import Optional
import warnings
warnings.filterwarnings('ignore')

# sounddevice optionnel (requiert PortAudio)
sd = None
_HAS_AUDIO = False
try:
    import sounddevice as sd_module
    sd = sd_module
    _HAS_AUDIO = True
except (ImportError, OSError):
    print("Note: audio désactivé (installez portaudio19-dev pour le vocal)")


def _resolve_dev(dev):
    """Convertit un device en entier si possible"""
    if dev is None:
        return None
    try:
        return int(dev)
    except (ValueError, TypeError):
        return dev


class VoiceRecognizer:
    def __init__(self, config: dict, input_device = None, sample_rate: int = 16000):
        self.config = config
        self.input_devices = self._resolve_devices(input_device, config)
        self.sample_rate = sample_rate
        self.model = None
        self.is_wake_word_ready = False
        self._transcribe_count = 0
        self._gc_interval = config.get("gc_interval", 300)
        self._w = config.get("whisper", {})
        self._groq_key = config.get("groq_api_key", "")
        self._openai_key = config.get("openai_api_key", "")
        self._api_endpoint = config.get("stt_endpoint", "")
        self._use_api = bool(self._api_endpoint or self._groq_key or self._openai_key)
        self._api_provider = None
        self._wake_calls_this_minute = 0
        self._wake_minute_start = time.time()
        self._cmd_calls_this_minute = 0
        self._cmd_minute_start = time.time()
        self._oww = None
        if self._use_api:
            self._init_api()
        else:
            self._init_whisper()

    def _init_api(self):
        """Configure la reconnaissance via API distante"""
        if self._api_endpoint:
            print(f"STT: endpoint distant -> {self._api_endpoint}")
        elif self._groq_key:
            print("STT: API Groq (cloud) - Whisper-large-v3")
            self._api_provider = "groq"
        else:
            print("STT: API OpenAI Whisper (cloud)")
            self._api_provider = "openai"
        self.is_wake_word_ready = True
        print("Mode cloud: Whisper local non charge")

    def _init_whisper(self):
        """Initialise Whisper local (CPU)"""
        try:
            import whisper
            model_name = self._w.get("model", "tiny")
            device = self._w.get("device", "cpu")

            print(f"Chargement Whisper '{model_name}' sur {device}...")
            if device == "cuda":
                import torch
                if not torch.cuda.is_available():
                    print("CUDA non disponible, chargement sur CPU")
                    device = "cpu"
            self.model = whisper.load_model(model_name, device=device)
            self.is_wake_word_ready = True
            print("Whisper chargé")

        except ImportError:
            print("Whisper non installé. pip install openai-whisper")
        except Exception as e:
            print(f"Erreur Whisper: {e}")

    def _resolve_devices(self, input_device, config):
        devices = config.get("audio", {}).get("input_devices", input_device)
        if devices is None:
            return [None]
        if isinstance(devices, list):
            return [_resolve_dev(d) for d in devices]
        if isinstance(devices, str) and "," in devices:
            return [_resolve_dev(d.strip()) for d in devices.split(",")]
        return [_resolve_dev(devices)]

    def _record_mix(self, duration, show_vu=False):
        samples = int(duration * self.sample_rate)
        recorded = sd.rec(samples, samplerate=self.sample_rate, channels=1,
                          dtype=np.float32, device=None)
        bar_len = 20
        if show_vu:
            steps = int(duration / 0.1)
            for i in range(steps):
                time.sleep(0.1)
                end = min(int((i + 1) * 0.1 * self.sample_rate), samples)
                chunk = recorded[max(0, end - int(0.1 * self.sample_rate)):end]
                if len(chunk) > 0:
                    self._print_vu(chunk, bar_len)
            print()

        sd.wait()
        sd.stop()
        audio = recorded.flatten()

        if show_vu:
            peak = float(np.nanmax(np.abs(audio)))
            db = 20 * np.log10(max(peak, 1e-10))
            b = int((db + 60) / 4)
            b = max(0, min(bar_len, b))
            print(f"  Niveau max: [{'#' * b}{'.' * (bar_len - b)}] {db:+.0f} dB")

        return self._normalize(audio)

    def _print_vu(self, chunk, bar_len):
        peak = float(np.nanmax(np.abs(chunk)))
        if np.isnan(peak) or np.isinf(peak) or peak < 1e-10:
            peak = 1e-10
        db = min(max(20 * np.log10(peak), -100), 20)
        b = int((db + 60) / 4)
        b = max(0, min(bar_len, b))
        print(f"\r  [{('#' * b) + ('.' * (bar_len - b))}] {db:+.0f} dB", end='', flush=True)

    def _normalize(self, audio: np.ndarray, target_db: float = -12.0) -> np.ndarray:
        peak = float(np.nanmax(np.abs(audio)))
        if np.isnan(peak) or peak < 1e-10:
            return audio
        current_db = 20 * np.log10(peak)
        gain_db = target_db - current_db
        if gain_db > 0:
            gain = 10 ** (gain_db / 20)
            audio = audio * gain
            peak = float(np.nanmax(np.abs(audio)))
            if peak > 1.0:
                audio = audio / peak
        return audio

    def listen(self, duration: int = 2, show_vu: bool = False) -> Optional[np.ndarray]:
        """Enregistre audio (durée réduite pour économiser RAM)"""
        if not _HAS_AUDIO:
            return None

        try:
            audio = self._record_mix(duration, show_vu)
            return audio
        except Exception as e:
            print(f"Erreur: {e}")
            return None

    def recognize(self, audio: np.ndarray) -> str:
        """Reconnaissance vocale (API distante ou Whisper local)"""
        if self._use_api:
            return self._recognize_api(audio)
        if self.model is None:
            return ""

        try:
            import whisper
            audio = audio.astype(np.float32)
            audio = whisper.audio.pad_or_trim(audio)
            result = self.model.transcribe(
                audio,
                language=self._w.get("language", "fr"),
                fp16=False,
                temperature=0.0
            )
            self._transcribe_count += 1
            self._maybe_gc()
            return result["text"].strip()
        except Exception as e:
            print(f"Erreur: {e}")
            return ""

    def _audio_to_wav(self, audio: np.ndarray, sr: int = 16000) -> bytes:
        """Convertit un tableau numpy en WAV bytes"""
        import struct
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes((audio * 32767).astype(np.int16).tobytes())
        return buf.getvalue()

    def _recognize_api(self, audio: np.ndarray) -> str:
        """Reconnaissance via API distante (Groq / endpoint custom / OpenAI)"""
        import requests

        # Envoi direct au sample rate natif, pas de rééchantillonnage
        wav_bytes = self._audio_to_wav(audio, self.sample_rate)

        try:
            # 1. Endpoint custom (priorité max)
            if self._api_endpoint:
                r = requests.post(
                    self._api_endpoint,
                    files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                    timeout=30
                )
                if r.status_code == 200:
                    return r.json().get("text", "").strip()
                print(f"STT endpoint error ({r.status_code}): {r.text[:100]}")
                return ""

            # 2. Groq API (gratuit, Whisper-large-v3)
            if self._groq_key:
                for attempt in range(3):
                    r = requests.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self._groq_key}"},
                        files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                        data={
                            "model": "whisper-large-v3",
                            "language": self._w.get("language", "fr"),
                        },
                        timeout=60
                    )
                    if r.status_code == 200:
                        return r.json().get("text", "").strip()
                    if r.status_code == 429:
                        print(f"\r  \033[93mRate limit, pause 5s...\033[0m" + " " * 20, end='', flush=True)
                        time.sleep(5)
                    else:
                        print(f"Groq STT error ({r.status_code}): {r.text[:200]}")
                        break
                return ""

            # 3. OpenAI Whisper API
            if self._openai_key:
                r = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._openai_key}"},
                    files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                    data={
                        "model": "whisper-1",
                        "language": self._w.get("language", "fr"),
                        "response_format": "json"
                    },
                    timeout=60
                )
                if r.status_code == 200:
                    return r.json().get("text", "").strip()
                print(f"OpenAI STT error ({r.status_code}): {r.text[:200]}")
                return ""

        except requests.exceptions.Timeout:
            print("STT API: timeout")
        except Exception as e:
            print(f"STT API error: {e}")
        return ""

    def _has_speech(self, audio: np.ndarray) -> bool:
        # openWakeWord VAD (Silero via ONNX) - plus robuste sur micro faible
        if self._oww is None:
            try:
                import os as _os
                _os.environ['ORT_LOG_LEVEL'] = '3'
                from openwakeword import VAD as OWWVAD
                self._oww = OWWVAD()
            except Exception:
                self._oww = False
        if self._oww:
            try:
                from scipy.signal import resample
                audio16 = resample(audio, int(len(audio) * 16000 / self.sample_rate)).astype(np.float32)
                audio16 = (audio16 * 32767).astype(np.int16)
                frame_size = 480
                frames = len(audio16) // frame_size
                if frames == 0:
                    return False
                audio16 = audio16[:frames * frame_size]
                score = self._oww.predict(audio16)
                return score > 0.25
            except Exception:
                pass

        # Fallback WebRTC VAD
        try:
            import webrtcvad
            from scipy.signal import resample
            audio16 = resample(audio, int(len(audio) * 16000 / self.sample_rate)).astype(np.float32)
            audio16 = (audio16 * 32767).astype(np.int16)
            vad = webrtcvad.Vad(2)
            frame_len = 480
            speech_frames = 0
            total_frames = 0
            for i in range(0, len(audio16) - frame_len, frame_len):
                frame = audio16[i:i+frame_len].tobytes()
                if vad.is_speech(frame, 16000):
                    speech_frames += 1
                total_frames += 1
            ratio = speech_frames / max(total_frames, 1)
            return ratio > 0.2
        except Exception:
            pass
        return True

    def _wake_rate_ok(self, music_playing: bool = False) -> bool:
        now = time.time()
        if now - self._wake_minute_start > 60:
            self._wake_calls_this_minute = 0
            self._wake_minute_start = now
        max_calls = 2 if music_playing else 15
        return self._wake_calls_this_minute < max_calls

    def _wake_call_made(self):
        self._wake_calls_this_minute += 1

    def listen_for_wake_word(self, wake_word: str = "bob", threshold: float = 0.5, music_playing: bool = False) -> bool:
        """Écoute mot de réveil - local d'abord, Groq en confirmation"""
        if not _HAS_AUDIO:
            return True
        if not self._use_api and self.model is None:
            return True

        wake_duration = self.config.get("wake_chunk_duration", 1)
        try:
            samples = int(wake_duration * self.sample_rate)
            devs = self.input_devices or [None]

            if len(devs) == 1:
                recorded = sd.rec(samples, samplerate=self.sample_rate, channels=1,
                                  dtype=np.float32, device=devs[0])
            else:
                recorded = [sd.rec(samples, samplerate=self.sample_rate, channels=1,
                                   dtype=np.float32, device=d) for d in devs]

            bar_len = 12
            steps = int(wake_duration / 0.1)
            for i in range(steps):
                time.sleep(0.1)
                if len(devs) == 1:
                    end = min(int((i + 1) * 0.1 * self.sample_rate), samples)
                    chunk = recorded[max(0, end - int(0.1 * self.sample_rate)):end]
                else:
                    chunk = None
                    peak = 0.0
                    for r in recorded:
                        end = min(int((i + 1) * 0.1 * self.sample_rate), samples)
                        c = r[max(0, end - int(0.1 * self.sample_rate)):end]
                        if len(c) > 0:
                            p = float(np.nanmax(np.abs(c)))
                            if not np.isnan(p) and not np.isinf(p):
                                peak = max(peak, p)
                    if peak == 0.0:
                        peak = 1e-10
                if len(devs) == 1 and len(chunk) > 0:
                    peak = float(np.nanmax(np.abs(chunk)))
                    if np.isnan(peak) or np.isinf(peak) or peak < 1e-10:
                        peak = 1e-10
                db = min(max(20 * np.log10(max(peak, 1e-10)), -100), 20)
                b = int((db + 60) / 4)
                b = max(0, min(bar_len, b))
                print(f"\r  [{('#' * b) + ('.' * (bar_len - b))}] {db:+.0f} dB  attente '{wake_word}'...", end='', flush=True)

            sd.wait()

            if len(devs) == 1:
                raw = recorded.flatten()
            else:
                raw = sum(r.flatten() for r in recorded) / len(devs)

            peak = float(np.nanmax(np.abs(raw)))
            rms = float(np.sqrt(np.mean(raw**2)))
            if np.isnan(peak):
                peak = 0.0

            if rms < 0.001 and peak < 0.002:
                print(f"\r  \033[90m(silence)\033[0m" + " " * 30, end='', flush=True)
                return False

            audio = self._normalize(raw)

            if not self._has_speech(audio):
                print(f"\r  \033[90m(bruit)\033[0m" + " " * 30, end='', flush=True)
                time.sleep(0.3)
                return False

            if not self._wake_rate_ok(music_playing):
                print(f"\r  \033[93m(limité, pause 4s)\033[0m" + " " * 20, end='', flush=True)
                time.sleep(4)
                return False

            self._wake_call_made()
            text = self.recognize(audio)
            if text:
                found = wake_word.lower() in text.lower()
                if found:
                    print(f"\r  \033[92m✓ \"{text}\"\033[0m" + " " * 20, end='', flush=True)
                else:
                    print(f"\r  \033[90m\"{text}\"\033[0m" + " " * 20, end='', flush=True)
            else:
                print(f"\r  \033[90m(rien)\033[0m" + " " * 30, end='', flush=True)
            return wake_word.lower() in text.lower() if text else False
        except Exception as e:
            if not hasattr(self, '_last_error_time') or time.time() - self._last_error_time > 3:
                print(f"\r  \033[91mErreur: {e}\033[0m" + " " * 30, end='', flush=True)
                self._last_error_time = time.time()
            return False

    def _resample_to_16k(self, audio):
        target_rate = 16000
        try:
            from scipy.signal import resample
            num = int(len(audio) * target_rate / self.sample_rate)
            return resample(audio, num).astype(np.float32)
        except ImportError:
            num = int(len(audio) * target_rate / self.sample_rate)
            x_old = np.linspace(0, 1, len(audio))
            x_new = np.linspace(0, 1, num)
            return np.interp(x_new, x_old, audio).astype(np.float32)

    def _maybe_gc(self):
        """Garbage collector périodique pour éviter fuite RAM"""
        if self._transcribe_count % self._gc_interval == 0:
            gc.collect()

    def get_audio_devices(self):
        """Liste périphériques"""
        return sd.query_devices() if _HAS_AUDIO else []


def check_dependencies():
    """Vérifie deps"""
    missing = []
    try:
        import whisper
    except ImportError:
        missing.append("openai-whisper")
    return len(missing) == 0
