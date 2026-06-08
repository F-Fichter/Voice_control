#!/usr/bin/env python3
"""
Home Assistant Plugin - Contrôle via Home Assistant
"""

import requests
from typing import Dict, Optional


class HomeAssistantPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}
        self.ha_url = None
        self.ha_token = None

    def configure(self, url: str, token: str):
        """Configure la connexion HA"""
        self.ha_url = url.rstrip("/")
        self.ha_token = token

    def add_device(self, name: str, config: Dict):
        """Ajoute un appareil HA"""
        # Récupère config HA si non définie
        if not self.ha_url:
            self.configure(
                config.get("ha_url", "http://homeassistant:8123"),
                config.get("ha_token", "")
            )

        self.devices[name] = {
            "entity_id": config.get("entity_id", f"switch.{name.replace(' ', '_').lower()}"),
        }

    def _ha_request(self, service: str, entity_id: str) -> bool:
        """Appelle un service HA"""
        if not self.ha_url or not self.ha_token:
            return False

        try:
            url = f"{self.ha_url}/api/services/switch/{service}"
            headers = {
                "Authorization": f"Bearer {self.ha_token}",
                "Content-Type": "application/json"
            }
            data = {"entity_id": entity_id}

            response = requests.post(url, json=data, headers=headers, timeout=5)
            return response.status_code == 200

        except Exception as e:
            print(f"Erreur HA: {e}")
            return False

    def turn_on(self, device_name: str = None) -> bool:
        """Allume via HA"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False
        return self._ha_request("turn_on", self.devices[device_name]["entity_id"])

    def turn_off(self, device_name: str = None) -> bool:
        """Éteint via HA"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False
        return self._ha_request("turn_off", self.devices[device_name]["entity_id"])

    def toggle(self, device_name: str = None) -> bool:
        """Bascule via HA"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False
        return self._ha_request("toggle", self.devices[device_name]["entity_id"])

    def get_status(self, device_name: str = None) -> Dict:
        """Statut depuis HA"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return {"error": "Aucun appareil"}

        if not self.ha_url or not self.ha_token:
            return {"error": "HA non configuré"}

        try:
            url = f"{self.ha_url}/api/states/{self.devices[device_name]['entity_id']}"
            headers = {"Authorization": f"Bearer {self.ha_token}"}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                state = response.json()
                return {
                    "state": state.get("state"),
                    "last_changed": state.get("last_changed")
                }

        except Exception as e:
            return {"error": str(e)}

        return {"error": "Impossible d'obtenir le statut"}