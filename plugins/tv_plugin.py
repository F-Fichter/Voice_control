#!/usr/bin/env python3
"""
TV Plugin - Contrôle de télévisions
Support: Samsung Tizen, LG webOS, Chromecast, generic HTTP
"""

import socket
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Optional


class TVPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}
        self._ssdp_cache = {}

    def add_device(self, name: str, config: Dict):
        """Ajoute une TV"""
        self.devices[name] = {
            "type": config.get("type", "samsung"),  # samsung, lg, chromecast, http
            "host": config.get("host"),
            "port": config.get("port", 55000),
            "mac": config.get("mac"),
            "api_key": config.get("api_key"),
            "name": config.get("name", name),
        }

    def _get_device(self, name: str = None):
        if name:
            return self.devices.get(name)
        return next(iter(self.devices.values()), None) if self.devices else None

    # === Commandes de base ===
    def turn_on(self, name: str = None) -> Dict:
        """Allume la TV (WoL)"""
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        mac = device.get("mac")
        if not mac:
            return {"error": "Adresse MAC requise pour WoL"}

        try:
            # Wake on LAN
            mac_bytes = bytes.fromhex(mac.replace(":", ""))
            packet = b'\xff' * 6 + mac_bytes * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, ('<broadcast>', 9))
            sock.close()
            return {"success": True, "action": "power_on"}
        except Exception as e:
            return {"error": str(e)}

    def turn_off(self, name: str = None) -> Dict:
        """Éteint la TV"""
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        tv_type = device.get("type")

        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_POWEROFF")
        elif tv_type == "lg":
            return self._lg_send(device, "off")
        else:
            return {"error": "Type TV non supporté pour power off"}

    def toggle(self, name: str = None) -> Dict:
        """Toggle ON/OFF"""
        # Tente d'envoyer power (certaines TV permettent)
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        tv_type = device.get("type")
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_POWER")
        elif tv_type == "lg":
            return self._lg_key(device, "MUTE_POWER")
        return {"error": "Toggle non supporté"}

    # === Volume ===
    def volume_up(self, name: str = None) -> Dict:
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        tv_type = device.get("type")
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_VOLUP")
        elif tv_type == "lg":
            return self._lg_key(device, "VOL_UP")
        return {"error": "Type non supporté"}

    def volume_down(self, name: str = None) -> Dict:
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        tv_type = device.get("type")
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_VOLDOWN")
        elif tv_type == "lg":
            return self._lg_key(device, "VOL_DOWN")
        return {"error": "Type non supporté"}

    def mute(self, name: str = None) -> Dict:
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        tv_type = device.get("type")
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_MUTE")
        elif tv_type == "lg":
            return self._lg_key(device, "MUTE")
        return {"error": "Type non supporté"}

    # === Navigation ===
    def home(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_HOME")
        elif tv_type == "lg":
            return self._lg_key(device, "HOME")
        return {"error": "Non supporté"}

    def back(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_RETURN")
        elif tv_type == "lg":
            return self._lg_key(device, "BACK")
        return {"error": "Non supporté"}

    def enter(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_ENTER")
        elif tv_type == "lg":
            return self._lg_key(device, "ENTER")
        return {"error": "Non supporté"}

    # === Navigation directions ===
    def up(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_UP")
        elif tv_type == "lg":
            return self._lg_key(device, "UP")
        return {"error": "Non supporté"}

    def down(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_DOWN")
        elif tv_type == "lg":
            return self._lg_key(device, "DOWN")
        return {"error": "Non supporté"}

    def left(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_LEFT")
        elif tv_type == "lg":
            return self._lg_key(device, "LEFT")
        return {"error": "Non supporté"}

    def right(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type", "samsung") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_RIGHT")
        elif tv_type == "lg":
            return self._lg_key(device, "RIGHT")
        return {"error": "Non supporté"}

    # === Apps / Sources ===
    def launch_app(self, app_id: str, name: str = None) -> Dict:
        """Lance une application"""
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        tv_type = device.get("type")
        if tv_type == "samsung":
            return self._samsung_send(device, f"KEY_{app_id.upper()}")
        elif tv_type == "lg":
            return self._lg_app(device, app_id)
        return {"error": "Type non supporté"}

    def netflix(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_NETFLIX")
        elif tv_type == "lg":
            return self._lg_app(device, "Netflix")
        return {"error": "Non supporté"}

    def youtube(self, name: str = None) -> Dict:
        device = self._get_device(name)
        tv_type = device.get("type") if device else "samsung"
        if tv_type == "samsung":
            return self._samsung_send(device, "KEY_YOUTUBE")
        elif tv_type == "lg":
            return self._lg_app(device, "youtube.leanback.launcher")
        return {"error": "Non supporté"}

    # === Chromecast ===
    def cast_url(self, url: str, name: str = None) -> Dict:
        """Cast une URL vers Chromecast"""
        device = self._get_device(name)
        if not device:
            return {"error": "TV non trouvée"}

        if device.get("type") != "chromecast":
            return {"error": "Pas une Chromecast"}

        try:
            import pychromecast
            mc = pychromecast.get_chromecasts()[0]
            mc.play_media(url)
            return {"success": True, "action": "cast", "url": url}
        except Exception as e:
            return {"error": str(e)}

    # === Samsung Tizen ===
    def _samsung_send(self, device: Dict, key: str) -> Dict:
        """Envoie une touche Samsung"""
        import base64

        host = device.get("host")
        if not host:
            return {"error": "Host requis"}

        try:
            # Génère token si nécessaire
            access_token = device.get("api_key") or self._samsung_auth(host)
            if not access_token:
                return {"error": "Auth Samsung requise"}

            # Construit la requête
            data = f'<?xml version="1.0" encoding="utf-8"?><command>< cruises_API_Key="'+access_token+'"><Cmd>Click</Cmd><Data value="{key}"/></cruises_API_Key></command>'

            url = f"http://{host}:8001/api/v2/channels/samsung.remote.control"
            requests.post(url, data=data.encode(), headers={"Content-Type": "application/xml"}, timeout=3)
            return {"success": True, "action": key}

        except Exception as e:
            return {"error": str(e)}

    def _samsung_auth(self, host: str) -> Optional[str]:
        """Authentification Samsung"""
        try:
            url = f"http://{host}:8001/api/v2/"
            r = requests.get(url, timeout=3)
            info = r.json()
            token = info.get("device", {}).get("Token")
            if token:
                # Confirme le token via l'écran TV
                confirm_url = f"http://{host}:8001/api/v2/pairing/guide/{token}"
                requests.post(confirm_url, timeout=3)
            return token
        except:
            return None

    # === LG webOS ===
    def _lg_key(self, device: Dict, key: str) -> Dict:
        """Envoie une touche LG"""
        host = device.get("host")
        port = device.get("port", 3000)
        client_key = device.get("api_key")

        if not host or not client_key:
            return {"error": "Host et API key requis"}

        try:
            url = f"http://{host}:{port}/api/v2/keys"
            requests.post(url, json={"type": "button", "name": key}, headers={
                "Authorization": f"Bearer {client_key}",
                "Content-Type": "application/json"
            }, timeout=3)
            return {"success": True, "action": key}
        except Exception as e:
            return {"error": str(e)}

    def _lg_app(self, device: Dict, app_id: str) -> Dict:
        """Lance app LG"""
        host = device.get("host")
        port = device.get("port", 3000)
        client_key = device.get("api_key")

        try:
            url = f"http://{host}:{port}/api/v2/launcher"
            requests.post(url, json={"id": app_id}, headers={
                "Authorization": f"Bearer {client_key}",
                "Content-Type": "application/json"
            }, timeout=3)
            return {"success": True, "app": app_id}
        except Exception as e:
            return {"error": str(e)}

    def _lg_send(self, device: Dict, cmd: str) -> Dict:
        """Commande LG directe"""
        host = device.get("host")
        port = device.get("port", 3000)
        client_key = device.get("api_key")

        if not host or not client_key:
            return {"error": "Configuration requise"}

        try:
            url = f"http://{host}:{port}/api/v2/{cmd}"
            requests.post(url, headers={"Authorization": f"Bearer {client_key}"}, timeout=3)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self, name: str = None) -> Dict:
        """Statut de la TV"""
        return {"online": True, "type": "tv"}