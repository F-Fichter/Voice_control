#!/usr/bin/env python3
"""
IR Plugin - Contrôle infrarouge pour TVs et appareils
Support: LIRC, Flirc, Broadlink RM, GPIO IR, HDMI-CEC
"""

import subprocess
import socket
import json
from pathlib import Path
from typing import Dict, Optional


class IRPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}
        self.lirc_socket = "/var/run/lirc/lircd"
        self._init_ir()

    def _init_ir(self):
        """Détecte le système IR disponible"""
        self.ir_type = None

        # Vérifie LIRC
        if Path(self.lirc_socket).exists() or subprocess.run(['which', 'irsend'], capture_output=True).returncode == 0:
            self.ir_type = "lirc"
            return

        # Vérifie Flirc
        if subprocess.run(['which', 'flirc_util'], capture_output=True).returncode == 0:
            self.ir_type = "flirc"
            return

        # Vérifie Python-LIRC
        try:
            import lirc
            self.ir_type = "python-lirc"
            return
        except ImportError:
            pass

        # Vérifie Broadlink
        if self._check_broadlink():
            self.ir_type = "broadlink"
            return

        print(f"IR: Aucun système détecté (LIRC/Flirc/Broadlink)")

    def _check_broadlink(self) -> bool:
        """Vérifie Broadlink RM"""
        try:
            from broadlink import discover
            devices = discover(timeout=5)
            return len(devices) > 0
        except:
            return False

    def add_device(self, name: str, config: Dict):
        """Ajoute un appareil IR"""
        self.devices[name] = {
            "type": "ir",
            "brand": config.get("brand", "generic"),
            "remote": config.get("remote", name),  # Fichier LIRC remote
            "mac": config.get("mac"),  # Broadlink
            "ip": config.get("ip"),  # Broadlink IP
            "codes": config.get("codes", {}),  # Codes IR personnalisés
        }

    # === Commandes génériques ===
    def power(self, name: str = None) -> Dict:
        """Power ON/OFF"""
        return self._send_ir("power", name)

    def turn_on(self, name: str = None) -> Dict:
        """Allume"""
        return self._send_ir("power_on", name) or self._send_ir("power", name)

    def turn_off(self, name: str = None) -> Dict:
        """Éteint"""
        return self._send_ir("power_off", name) or self._send_ir("power", name)

    # === Volume ===
    def volume_up(self, name: str = None) -> Dict:
        return self._send_ir("vol_up", name) or self._send_ir("volume_up", name)

    def volume_down(self, name: str = None) -> Dict:
        return self._send_ir("vol_down", name) or self._send_ir("volume_down", name)

    def mute(self, name: str = None) -> Dict:
        return self._send_ir("mute", name)

    # === Navigation ===
    def up(self, name: str = None) -> Dict:
        return self._send_ir("up", name)

    def down(self, name: str = None) -> Dict:
        return self._send_ir("down", name)

    def left(self, name: str = None) -> Dict:
        return self._send_ir("left", name)

    def right(self, name: str = None) -> Dict:
        return self._send_ir("right", name)

    def enter(self, name: str = None) -> Dict:
        return self._send_ir("enter", name) or self._send_ir("ok", name)

    def back(self, name: str = None) -> Dict:
        return self._send_ir("back", name) or self._send_ir("return", name)

    def home(self, name: str = None) -> Dict:
        return self._send_ir("home", name) or self._send_ir("menu", name)

    def source(self, name: str = None) -> Dict:
        """Source/Input"""
        return self._send_ir("source", name) or self._send_ir("input", name)

    # === Apps ===
    def netflix(self, name: str = None) -> Dict:
        return self._send_ir("netflix", name)

    def youtube(self, name: str = None) -> Dict:
        return self._send_ir("youtube", name)

    def prime(self, name: str = None) -> Dict:
        return self._send_ir("prime", name)

    # === Méthodes internes ===
    def _send_ir(self, command: str, name: str = None) -> Dict:
        """Envoie une commande IR"""
        device = self._get_device(name)

        if not device:
            return {"error": f"Appareil '{name}' non trouvé"}

        # Vérifie si commande personnalisée
        if device.get("codes") and command in device["codes"]:
            raw_code = device["codes"][command]
            return self._send_raw(raw_code, device)

        # Envoie via le système détecté
        if self.ir_type == "lirc":
            return self._send_lirc(device, command)
        elif self.ir_type == "flirc":
            return self._send_flirc(device, command)
        elif self.ir_type == "broadlink":
            return self._send_broadlink(device, command)
        elif self.ir_type == "python-lirc":
            return self._send_python_lirc(device, command)

        return {"error": "Système IR non configuré"}

    def _get_device(self, name: str = None):
        if name:
            return self.devices.get(name)
        return next(iter(self.devices.values()), None) if self.devices else None

    def _send_lirc(self, device: Dict, command: str) -> Dict:
        """Envoie via LIRC"""
        remote = device.get("remote", device.get("name", "default"))

        try:
            result = subprocess.run(
                ['irsend', 'SEND_ONCE', remote, command],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                return {"success": True, "command": command}
            return {"error": result.stderr.decode()}
        except Exception as e:
            return {"error": str(e)}

    def _send_flirc(self, device: Dict, command: str) -> Dict:
        """Envoie via Flirc"""
        try:
            result = subprocess.run(
                ['flirc_util', 'send', command],
                capture_output=True,
                timeout=2
            )
            return {"success": result.returncode == 0}
        except Exception as e:
            return {"error": str(e)}

    def _send_broadlink(self, device: Dict, command: str) -> Dict:
        """Envoie via Broadlink RM"""
        try:
            from broadlink import device as bl_device

            host = device.get("ip")
            mac = bytes.fromhex(device.get("mac", "").replace(":", ""))

            if not host:
                return {"error": "IP Broadlink requise"}

            # Décover l'appareil
            dev = bl_device(host, mac)
            dev.auth()

            # Envoie le code si disponible
            codes = device.get("codes", {})
            if command in codes:
                code = codes[command]
                dev.send_data(code)
                return {"success": True, "command": command}

            return {"error": "Code IR non trouvé"}

        except Exception as e:
            return {"error": str(e)}

    def _send_python_lirc(self, device: Dict, command: str) -> Dict:
        """Envoie via Python-LIRC"""
        try:
            import lirc
            sockid = lirc.init("voice_control")
            lirc.set_sockcmd(sockid, "SEND_ONCE", device.get("remote", "default"), command)
            lirc.deinit()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def _send_raw(self, raw_code: bytes, device: Dict) -> Dict:
        """Envoie un code IR brut"""
        if self.ir_type == "broadlink":
            return self._send_broadlink(device, raw_code)
        return {"error": "Envoi code brut non supporté"}

    # === Enregistrement de codes ===
    def learn(self, command: str, name: str = None, output_file: str = None) -> Dict:
        """Enregistre un code IR (mode apprentissage)"""
        device = self._get_device(name)

        print(f"=== Apprentissage IR ===")
        print(f"Appareil: {name or 'défaut'}")
        print(f"Commande: {command}")
        print(f"Appuyez sur la touche à enregistrer...")
        print(f"Ctrl+C pour annuler")

        if self.ir_type == "lirc":
            return self._learn_lirc(command, device)
        elif self.ir_type == "flirc":
            return self._learn_flirc(command, device)
        elif self.ir_type == "broadlink":
            return self._learn_broadlink(command, device)

        return {"error": "Apprentissage non disponible"}

    def _learn_lirc(self, command: str, device: Dict) -> Dict:
        """Apprend via irrecord (LIRC)"""
        remote = device.get("remote", "my_remote") if device else "my_remote"
        config_file = f"/etc/lirc/lircd.conf.d/{remote}.conf"

        try:
            subprocess.run(['irrecord', '-f', '-d', '/dev/lirc0', config_file], timeout=60)
            return {"success": True, "config": config_file}
        except Exception as e:
            return {"error": str(e)}

    def _learn_flirc(self, command: str, device: Dict) -> Dict:
        """Apprend via Flirc"""
        try:
            subprocess.run(['flirc_util', 'record', command], timeout=30)
            return {"success": True, "note": "Code enregistré via Flirc"}
        except Exception as e:
            return {"error": str(e)}

    def _learn_broadlink(self, command: str, device: Dict) -> Dict:
        """Apprend via Broadlink"""
        try:
            from broadlink import device as bl_device

            host = device.get("ip") or input("IP Broadlink: ")
            dev = bl_device(host, bytes(6))

            print("Appuyez sur la touche...")
            dev.enter_learning()

            import time
            time.sleep(5)
            code = dev.check_data()
            print(f"Code acquis: {code.hex()}")

            return {"success": True, "code": code.hex(), "command": command}

        except Exception as e:
            return {"error": str(e)}

    def get_status(self, name: str = None) -> Dict:
        return {
            "type": self.ir_type,
            "devices": list(self.devices.keys()),
            "available": self.ir_type is not None
        }


# === Codes IR pré-configurés pour grandes marques ===
BRAND_CODES = {
    "samsung": {
        "power": "KEY_POWER",
        "vol_up": "KEY_VOLUP",
        "vol_down": "KEY_VOLDOWN",
        "mute": "KEY_MUTE",
        "ch_up": "KEY_CHUP",
        "ch_down": "KEY_CHDOWN",
        "netflix": "KEY_NETFLIX",
        "source": "KEY_SOURCE",
        "home": "KEY_HOME",
        "up": "KEY_UP",
        "down": "KEY_DOWN",
        "left": "KEY_LEFT",
        "right": "KEY_RIGHT",
        "enter": "KEY_ENTER",
        "back": "KEY_RETURN",
        "0": "KEY_0", "1": "KEY_1", "2": "KEY_2", "3": "KEY_3",
        "4": "KEY_4", "5": "KEY_5", "6": "KEY_6",
        "7": "KEY_7", "8": "KEY_8", "9": "KEY_9",
    },
    "lg": {
        "power": "KEY_POWER",
        "vol_up": "KEY_VOLUMEUP",
        "vol_down": "KEY_VOLUMEDOWN",
        "mute": "KEY_MUTE",
        "netflix": "KEY_NETFLIX",
        "home": "KEY_HOME",
        "settings": "KEY_SETTINGS",
    },
    "sony": {
        "power": "KEY_POWER",
        "vol_up": "KEY_VOLUMEUP",
        "vol_down": "KEY_VOLUMEDOWN",
        "mute": "KEY_MUTE",
        "netflix": "KEY_NETFLIX",
        "youtube": "KEY_YOUTUBE",
        "home": "KEY_HOME",
    },
    "philips": {
        "power": "KEY_POWER",
        "vol_up": "KEY_VOLUMEUP",
        "vol_down": "KEY_VOLUMEDOWN",
        "mute": "KEY_MUTE",
        "ambilight": "KEY_AMBILIGHT",
        "source": "KEY_SOURCE",
    },
    "tcl": {
        "power": "KEY_POWER",
        "vol_up": "KEY_VOLUP",
        "vol_down": "KEY_VOLDOWN",
        "mute": "KEY_MUTE",
        "netflix": "KEY_NETFLIX",
    },
    "hisense": {
        "power": "KEY_POWER",
        "vol_up": "KEY_VOLUP",
        "vol_down": "KEY_VOLDOWN",
        "mute": "KEY_MUTE",
        "netflix": "KEY_NETFLIX",
    },
    "sharp": {
        "power": "PWR",
        "vol_up": "VOL_UP",
        "vol_down": "VOL_DOWN",
        "mute": "MUTE",
    },
    "panasonic": {
        "power": "PWR",
        "vol_up": "VOL_UP",
        "vol_down": "VOL_DOWN",
        "mute": "MUTE",
    },
    "thomson": {
        "power": "POWER",
        "vol_up": "VOLUP",
        "vol_down": "VOLDOWN",
        "mute": "MUTE",
    },
}