#!/usr/bin/env python3
"""
Smart Bulb Plugin - Contrôle d'ampoules connectées
Support: Hue, Tuya, Shelly, LIFX, Hue Emulation
"""

import requests
from typing import Dict, Optional


class SmartBulbPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}
        self.discovery_url = None

    def add_device(self, name: str, config: Dict):
        """Ajoute une ampoule"""
        self.devices[name] = {
            "protocol": config.get("protocol", "http"),  # http, mqtt, hue, lifx
            "host": config.get("host"),
            "port": config.get("port", 80),
            "api_key": config.get("api_key"),
            "device_id": config.get("device_id"),
            "brightness": 100,
            "color": {"r": 255, "g": 255, "b": 255},
            "color_temp": 400,  # Kelvin (warm=2700, cold=6500)
            "on": False
        }

    def _get_device(self, name: str = None):
        """Récupère un appareil"""
        if name:
            return self.devices.get(name)
        return next(iter(self.devices.values()), None) if self.devices else None

    # === Commandes de base ===
    def turn_on(self, name: str = None) -> Dict:
        """Allume l'ampoule"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        result = self._send_command(device, {"on": True})
        if result:
            device["on"] = True
        return {"success": True, "state": "on"}

    def turn_off(self, name: str = None) -> Dict:
        """Éteint l'ampoule"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        result = self._send_command(device, {"on": False})
        if result:
            device["on"] = False
        return {"success": True, "state": "off"}

    def toggle(self, name: str = None) -> Dict:
        """Bascule l'état"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        new_state = not device.get("on", False)
        return self.turn_on(name) if new_state else self.turn_off(name)

    # === Luminosité ===
    def set_brightness(self, level: int, name: str = None) -> Dict:
        """Règle la luminosité (0-100)"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        level = max(0, min(100, level))
        device["brightness"] = level

        result = self._send_command(device, {"bri": int(level * 2.54)})
        return {"success": True, "brightness": level}

    def dim(self, name: str = None) -> Dict:
        """Diminue la luminosité"""
        return self.set_brightness(30, name)

    def brighten(self, name: str = None) -> Dict:
        """Augmente la luminosité"""
        return self.set_brightness(100, name)

    # === Couleur ===
    def set_color(self, r: int, g: int, b: int, name: str = None) -> Dict:
        """Règle la couleur RGB"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
        device["color"] = {"r": r, "g": g, "b": b}

        if device["protocol"] == "hue":
            # Hue API
            hue_cmd = self._rgb_to_hue(r, g, b)
            result = self._send_command(device, hue_cmd)
        else:
            result = self._send_command(device, {"r": r, "g": g, "b": b})

        return {"success": True, "color": device["color"]}

    def set_white(self, name: str = None) -> Dict:
        """Lumière blanche"""
        return self.set_color(255, 255, 255, name)

    def set_warm_white(self, name: str = None) -> Dict:
        """Blanc chaud"""
        return self.set_color(255, 200, 150, name)

    def set_cold_white(self, name: str = None) -> Dict:
        """Blanc froid"""
        return self.set_color(200, 220, 255, name)

    # === Température couleur ===
    def set_color_temp(self, kelvin: int, name: str = None) -> Dict:
        """Règle la température couleur (2700-6500K)"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        device["color_temp"] = kelvin
        # Conversion simple vers RGB
        r, g, b = self._kelvin_to_rgb(kelvin)
        return self.set_color(r, g, b, name)

    # === Couleurs prédéfinies ===
    def set_color_name(self, color_name: str, name: str = None) -> Dict:
        """Règle une couleur par nom"""
        colors = {
            "rouge": (255, 0, 0),
            "vert": (0, 255, 0),
            "bleu": (0, 0, 255),
            "jaune": (255, 255, 0),
            "violet": (128, 0, 128),
            "rose": (255, 100, 150),
            "orange": (255, 165, 0),
            "cyan": (0, 255, 255),
            "ambre": (255, 191, 0),
        }

        color = colors.get(color_name.lower())
        if color:
            return self.set_color(*color, name)
        return {"error": f"Couleur '{color_name}' non reconnue"}

    def get_status(self, name: str = None) -> Dict:
        """Retourne le statut"""
        device = self._get_device(name)
        if not device:
            return {"error": "Ampoule non trouvée"}

        return {
            "on": device.get("on", False),
            "brightness": device.get("brightness", 100),
            "color": device.get("color", {"r": 255, "g": 255, "b": 255}),
            "color_temp": device.get("color_temp", 400)
        }

    # === Méthodes internes ===
    def _send_command(self, device: Dict, cmd: Dict) -> bool:
        """Envoie une commande HTTP"""
        try:
            host = device.get("host")
            if not host:
                return False

            protocol = device.get("protocol", "http")
            port = device.get("port", 80)

            if protocol == "hue":
                url = f"http://{host}/api/{device.get('api_key')}/lights/{device.get('device_id')}/state"
            else:
                url = f"http://{host}:{port}/state"

            response = requests.put(url, json=cmd, timeout=3)
            return response.ok

        except Exception as e:
            print(f"Bulb error: {e}")
            return False

    def _rgb_to_hue(self, r: int, g: int, b: int) -> Dict:
        """Convertit RGB vers Hue"""
        import colorsys
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        return {
            "hue": int(h * 65535),
            "sat": int(s * 254),
            "bri": int(v * 254)
        }

    def _kelvin_to_rgb(self, kelvin: int) -> tuple:
        """Convertit température Kelvin vers RGB"""
        # Approximation
        if kelvin < 4000:
            r = 255
            g = int(99 * (kelvin - 2000) / 700 + 128)
            b = int(55 * (kelvin - 2000) / 700 + 30)
        else:
            r = int(255 - 55 * (kelvin - 4000) / 1500)
            g = 255
            b = int(155 + 100 * (kelvin - 4000) / 1500)
        return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))