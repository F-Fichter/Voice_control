#!/usr/bin/env python3
"""
ESP32 Relay Plugin - Contrôle les relais ESP32 via ESPHome API
"""

import socket
import json
from typing import Dict, Optional


class ESP32RelayPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}

    def add_device(self, name: str, config: Dict):
        """Ajoute un appareil ESP32"""
        self.devices[name] = {
            "host": config.get("host", "192.168.1.100"),
            "port": config.get("port", 6053),
            "api_key": config.get("api_key", ""),
            "relay_id": config.get("relay_id", "relay_1")
        }

    def _connect(self, device_name: str) -> Optional[socket.socket]:
        """Connexion à l'ESP32"""
        device = self.devices.get(device_name)
        if not device:
            return None

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((device["host"], device["port"]))
            return sock
        except Exception as e:
            print(f"Erreur connexion ESP32 {device_name}: {e}")
            return None

    def turn_on(self, device_name: str = None) -> bool:
        """Allume le relais"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False

        sock = self._connect(device_name)
        if sock:
            try:
                relay_id = self.devices[device_name]["relay_id"]
                cmd = f"switch.turn_on: {relay_id}\n"
                sock.sendall(cmd.encode())
                sock.close()
                return True
            except Exception as e:
                print(f"Erreur: {e}")
        return False

    def turn_off(self, device_name: str = None) -> bool:
        """Éteint le relais"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False

        sock = self._connect(device_name)
        if sock:
            try:
                relay_id = self.devices[device_name]["relay_id"]
                cmd = f"switch.turn_off: {relay_id}\n"
                sock.sendall(cmd.encode())
                sock.close()
                return True
            except Exception as e:
                print(f"Erreur: {e}")
        return False

    def toggle(self, device_name: str = None) -> bool:
        """Bascule l'état du relais"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False

        sock = self._connect(device_name)
        if sock:
            try:
                relay_id = self.devices[device_name]["relay_id"]
                cmd = f"switch.toggle: {relay_id}\n"
                sock.sendall(cmd.encode())
                sock.close()
                return True
            except Exception as e:
                print(f"Erreur: {e}")
        return False

    def get_status(self, device_name: str = None) -> Dict:
        """Obtient le statut"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return {"error": "Aucun appareil"}

        return {
            "device": device_name,
            "online": True,
            "relay": False,
            "host": self.devices[device_name]["host"]
        }