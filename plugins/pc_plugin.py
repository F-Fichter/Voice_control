#!/usr/bin/env python3
"""
PC Plugin - Contrôle d'autres PC Linux (Wake-on-LAN, SSH, API)
"""

import socket
import subprocess
import requests
import json
from typing import Dict, Optional
from pathlib import Path


class PCPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}

    def add_device(self, name: str, config: Dict):
        """Ajoute un PC"""
        self.devices[name] = {
            "host": config.get("host", "localhost"),
            "port": config.get("port", 5000),
            "mac": config.get("mac"),
            "ssh_user": config.get("ssh_user"),
            "ssh_key": config.get("ssh_key"),
            "api_key": config.get("api_key"),
            "arch": config.get("arch", "x86_64"),  # x86_64, aarch64, armv7l
            "platform": config.get("platform", "linux"),
        }

    def _get_device(self, name: str = None):
        if name:
            return self.devices.get(name)
        return next(iter(self.devices.values()), None) if self.devices else None

    # === Alimentation ===
    def turn_on(self, name: str = None) -> Dict:
        """Wake-on-LAN"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        mac = device.get("mac")
        if not mac:
            return {"error": "MAC requise"}

        try:
            mac_bytes = bytes.fromhex(mac.replace(":", ""))
            packet = b'\xff' * 6 + mac_bytes * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (device.get("host", "<broadcast>"), 9))
            sock.close()
            return {"success": True, "action": "wake_on_lan"}
        except Exception as e:
            return {"error": str(e)}

    def turn_off(self, name: str = None) -> Dict:
        """Arrête le PC (via SSH ou API)"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        # Essaie API d'abord
        result = self._api_request(device, "/power/off")
        if result:
            return result

        # Sinon SSH
        return self._ssh_command("sudo shutdown -h now", device)

    def reboot(self, name: str = None) -> Dict:
        """Redémarre le PC"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        result = self._api_request(device, "/power/reboot")
        if result:
            return result

        return self._ssh_command("sudo reboot", device)

    def suspend(self, name: str = None) -> Dict:
        """Suspend le PC"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        return self._ssh_command("systemctl suspend", device)

    # === Commandes SSH ===
    def execute(self, command: str, name: str = None) -> Dict:
        """Exécute une commande SSH"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        return self._ssh_command(command, device)

    def _ssh_command(self, command: str, device: Dict) -> Dict:
        """Exécute via SSH"""
        user = device.get("ssh_user")
        host = device.get("host")
        key = device.get("ssh_key")

        if not user or not host:
            return {"error": "SSH: user et host requis"}

        try:
            cmd = ["ssh"]
            if key:
                cmd.extend(["-i", key])
            cmd.extend([f"{user}@{host}", command])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {"error": str(e)}

    # === API Voice Control Server ===
    def _api_request(self, device: Dict, endpoint: str) -> Optional[Dict]:
        """Requête API voice-control distant"""
        host = device.get("host")
        port = device.get("port", 5000)
        api_key = device.get("api_key")

        if not host:
            return None

        try:
            url = f"http://{host}:{port}{endpoint}"
            headers = {"X-API-Key": api_key} if api_key else {}

            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                return r.json()
            return {"error": f"API: {r.status_code}"}
        except:
            return None

    def command_remote(self, command: str, name: str = None) -> Dict:
        """Envoie une commande voice-control au PC distant"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        result = self._api_request(device, f"/command?cmd={command}")
        return result or {"error": "API indisponible"}

    # === Monitoring ===
    def get_status(self, name: str = None) -> Dict:
        """Statut du PC"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        # Vérifie si joignable
        host = device.get("host")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            online = sock.connect_ex((host, 22)) == 0 or self._api_request(device, "/status")
            sock.close()
        except:
            online = False

        return {
            "name": name,
            "online": online,
            "host": host,
            "arch": device.get("arch"),
            "platform": device.get("platform")
        }

    def get_system_info(self, name: str = None) -> Dict:
        """Info système via SSH"""
        device = self._get_device(name)
        if not device:
            return {"error": "PC non trouvé"}

        cpu = self._ssh_command("cat /proc/cpuinfo | grep 'model name' | head -1", device)
        mem = self._ssh_command("free -h | grep Mem", device)
        disk = self._ssh_command("df -h / | tail -1", device)
        uptime = self._ssh_command("uptime", device)

        return {
            "cpu": cpu.get("output", "?").strip(),
            "memory": mem.get("output", "?").strip(),
            "disk": disk.get("output", "?").strip(),
            "uptime": uptime.get("output", "?").strip()
        }


# ============================================
# SERVEUR CENTRAL - Pour coordination multi-PC
# ============================================

class VoiceControlServer:
    """Serveur API pour coordination entre machines"""

    def __init__(self, host="0.0.0.0", port=5000):
        self.host = host
        self.port = port
        self.devices = {}
        self.running = False

    def register_device(self, name: str, config: Dict):
        """Enregistre un appareil distant"""
        self.devices[name] = config

    def start(self):
        """Démarre le serveur"""
        try:
            from flask import Flask, request, jsonify
            from flask_cors import CORS
        except ImportError:
            print("pip install flask flask-cors")
            return

        app = Flask(__name__)
        CORS(app)

        @app.route('/status')
        def status():
            return jsonify({
                "status": "online",
                "devices": list(self.devices.keys()),
                "platform": "server"
            })

        @app.route('/command')
        def command():
            api_key = request.headers.get('X-API-Key')
            cmd = request.args.get('cmd', '')

            # Vérifie auth si configurée
            # if api_key != expected_key: return 401

            # Exécute localement
            from command_parser import CommandParser
            from plugin_manager import PluginManager

            pm = PluginManager(None)
            parser = CommandParser(pm)

            result = parser.parse(cmd)
            return jsonify(result)

        @app.route('/device/<name>/execute')
        def device_execute(name):
            if name not in self.devices:
                return jsonify({"error": "Device not found"}), 404

            device = self.devices[name]
            command = request.args.get('cmd', '')

            # Forward vers l'appareil
            return jsonify({"forwarded": name, "cmd": command})

        print(f"Serveur démarré sur http://{self.host}:{self.port}")
        app.run(host=self.host, port=self.port, debug=False)

    def stop(self):
        self.running = False