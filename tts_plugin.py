#!/usr/bin/env python3
"""Plugin TTS basique"""
class TTSPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.enabled = True

    def speak(self, text, wait=True):
        print(f"TTS: {text}")
        return True

    def confirm(self, action):
        responses = {"on": "Allumé", "off": "Éteint", "error": "Erreur", "stop": "Stopped"}
        print(f"TTS: {responses.get(action, 'OK')}")
        return True

    def speak_async(self, text):
        return self.speak(text, wait=False)