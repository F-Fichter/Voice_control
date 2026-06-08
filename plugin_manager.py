#!/usr/bin/env python3
"""
Plugin Manager - Gère les plugins de contrôle
"""

import json
from pathlib import Path

from chat_agent_plugin import ChatAgent


class PluginManager:
    def __init__(self, app):
        self.app = app
        self.plugins = {}
        self.devices = []
        self.tts = None
        self.chat_agent = ChatAgent(self)
        self._load_devices()

    def setup_tts(self, tts, output_device: int = None):
        """Connecte le TTS après initialisation"""
        self.tts = tts
        if self.chat_agent:
            self.chat_agent.tts = tts
        if hasattr(tts, 'set_output_device') and output_device is not None:
            tts.set_output_device(output_device)

    def _load_devices(self):
        """Charge les appareils"""
        devices_file = Path(__file__).parent / "devices.json"
        if devices_file.exists():
            with open(devices_file) as f:
                self.devices = json.load(f)

    def add_device(self, name: str, device_type: str, config: dict):
        """Ajoute un appareil"""
        self.devices.append({
            "name": name,
            "type": device_type,
            "config": config
        })

    def list_devices(self):
        return self.devices

    def get_plugin_for_type(self, device_type: str):
        return self.plugins.get(device_type)

    def get_device(self, name: str):
        for d in self.devices:
            if d["name"] == name:
                return d
        return None