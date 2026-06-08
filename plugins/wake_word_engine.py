"""
Wake Word Engine - Detection par seuil energétique adaptatif + Groq STT
Enregistre 1s, normalise, vérifie énergie, envoie à Groq si actif
"""

import time
import numpy as np


class WakeWordEngine:
    def __init__(self, config, recognizer):
        self.config = config
        self.recognizer = recognizer
        self._sd_ok = False
        self._check_audio()

    def _check_audio(self):
        try:
            import sounddevice as sd
            sd.check_input_settings()
            self._sd_ok = True
        except Exception:
            self._sd_ok = False

    def is_available(self) -> bool:
        return self._sd_ok

    def wait_for_wake_word(self, wake_word: str, music_playing: bool = False) -> bool:
        return self._listen_loop(wake_word)

    @staticmethod
    def _normalize(audio: np.ndarray, target_db: float = -12.0) -> np.ndarray:
        peak = float(np.nanmax(np.abs(audio)))
        if np.isnan(peak) or np.isinf(peak) or peak < 1e-10:
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

    def _listen_loop(self, wake_word: str) -> bool:
        import sounddevice as sd

        ww_config = self.config.get("wake_word_engine", {})
        energy_ratio = ww_config.get("energy_ratio", 2.5)
        noise_floor_alpha = ww_config.get("noise_floor_alpha", 0.92)

        sr = self.recognizer.sample_rate or 44100
        chunk_ms = ww_config.get("chunk_ms", 1000)
        chunk_size = int(sr * chunk_ms / 1000)
        bar_len = 12

        noise_floor_db = -100.0
        bar_count = 0
        cooldown_until = 0.0

        while True:
            try:
                recorded = sd.rec(chunk_size, samplerate=sr, channels=1,
                                  dtype=np.float32)
                sd.wait()
                sd.stop()
                frame = recorded.flatten()

                peak = float(np.nanmax(np.abs(frame)))
                if np.isnan(peak) or np.isinf(peak) or peak < 1e-10:
                    peak = 1e-10

                rms = float(np.sqrt(np.mean(frame ** 2)))
                if np.isnan(rms) or np.isinf(rms) or rms < 1e-10:
                    rms = 1e-10

                db = 20 * np.log10(peak)
                rms_db = 20 * np.log10(rms)

                if noise_floor_db == -100.0:
                    noise_floor_db = rms_db
                noise_floor_db = noise_floor_alpha * noise_floor_db + (1 - noise_floor_alpha) * min(rms_db, noise_floor_db + 6)

                has_energy = rms_db > noise_floor_db + 20 * np.log10(energy_ratio)

                bar_count = int((db + 60) / 4)
                bar_count = max(0, min(bar_len, bar_count))

                now = time.time()
                if now < cooldown_until:
                    label = f"pause {cooldown_until - now:.0f}s..."
                else:
                    label = "vérification..." if has_energy else f"'{wake_word}'..."
                print(f"\r  [{'#' * bar_count + '.' * (bar_len - bar_count)}] {db:+.0f} dB  {label}   ", end='', flush=True)

                if has_energy and now >= cooldown_until:
                    audio = self._normalize(frame)
                    print(f"\r  \033[90m(vérification...)\033[0m" + " " * 30, end='', flush=True)
                    text = self.recognizer.recognize(audio)
                    if text and wake_word.lower() in text.lower():
                        print(f"\r  \033[92m\"{text}\"\033[0m" + " " * 20, end='', flush=True)
                        print()
                        cooldown_until = time.time() + 5.0
                        return True
                    print(f"\r  \033[90m\"{text}\"\033[0m" + " " * 30, end='', flush=True)

            except KeyboardInterrupt:
                print()
                raise
            except Exception as e:
                if not hasattr(self, '_last_we_error') or time.time() - self._last_we_error > 3:
                    print(f"\r  \033[91mErreur: {e}\033[0m" + " " * 30, end='', flush=True)
                    self._last_we_error = time.time()
                continue

    def cleanup(self):
        pass
