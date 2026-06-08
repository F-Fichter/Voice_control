#!/usr/bin/env python3
"""
HTTP Plugin - Contrôle via requêtes HTTP génériques
"""

import requests
from typing import Dict, Optional


class HttpPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}

    def add_device(self, name: str, config: Dict):
        """Ajoute un appareil HTTP"""
        self.devices[name] = {
            "base_url": config.get("base_url", "http://localhost"),
            "on_endpoint": config.get("on_endpoint", "/on"),
            "off_endpoint": config.get("off_endpoint", "/off"),
            "status_endpoint": config.get("status_endpoint", "/status"),
            "headers": config.get("headers", {}),
            "auth": config.get("auth", None)
        }

    def _request(self, device_name: str, endpoint: str, method: str = "GET") -> Optional[Dict]:
        """Requête HTTP"""
        device = self.devices.get(device_name)
        if not device:
            return None

        try:
            url = device["base_url"] + endpoint
            kwargs = {"headers": device["headers"], "timeout": 5}

            if device["auth"]:
                kwargs["auth"] = tuple(device["auth"])

            if method == "GET":
                response = requests.get(url, **kwargs)
            elif method == "POST":
                response = requests.post(url, **kwargs)
            else:
                return None

            return {"status_code": response.status_code, "ok": response.ok}

        except Exception as e:
            print(f"Erreur HTTP: {e}")
            return None

    def turn_on(self, device_name: str = None) -> bool:
        """Allume via HTTP"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        result = self._request(device_name, self.devices[device_name]["on_endpoint"], "POST")
        return result is not None and result.get("ok")

    def turn_off(self, device_name: str = None) -> bool:
        """Éteint via HTTP"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        result = self._request(device_name, self.devices[device_name]["off_endpoint"], "POST")
        return result is not None and result.get("ok")

    def toggle(self, device_name: str = None) -> bool:
        """Bascule via HTTP"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        device = self.devices.get(device_name)
        if device and "toggle_endpoint" in device:
            result = self._request(device_name, device["toggle_endpoint"], "POST")
            return result is not None
        return False

    def get_status(self, device_name: str = None) -> Dict:
        """Statut via HTTP"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        result = self._request(device_name, self.devices[device_name]["status_endpoint"], "GET")
        return result or {"error": "Impossible d'obtenir le statut"}