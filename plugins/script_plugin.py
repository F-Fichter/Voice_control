#!/usr/bin/env python3
"""
Plugin générique pour contrôler des scripts shell/executables
Utile pour piloter n'importe quel dispositif via ligne de commande
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Optional


class ScriptPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.devices: Dict[str, Dict] = {}

    def add_device(self, name: str, config: Dict):
        """Ajoute un appareil script"""
        self.devices[name] = {
            "command_on": config.get("command_on", ""),
            "command_off": config.get("command_off", ""),
            "command_status": config.get("command_status", ""),
            "command_toggle": config.get("command_toggle", ""),
            "working_dir": config.get("working_dir", "."),
            "env": config.get("env", {}),
            "timeout": config.get("timeout", 10)
        }

    def _run_script(self, command: str, device_name: str) -> tuple:
        """Exécute un script et retourne (success, output)"""
        device = self.devices.get(device_name)
        if not device or not command:
            return False, "Commande non définie"

        try:
            cwd = device["working_dir"]
            if cwd == ".":
                cwd = Path(__file__).parent.parent

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=device["timeout"],
                env={**subprocess.os.environ, **device["env"]}
            )

            success = result.returncode == 0
            output = result.stdout.strip() or result.stderr.strip()
            return success, output

        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)

    def turn_on(self, device_name: str = None) -> bool:
        """Exécute la commande ON"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False

        cmd = self.devices[device_name].get("command_on")
        success, _ = self._run_script(cmd, device_name)
        return success

    def turn_off(self, device_name: str = None) -> bool:
        """Exécute la commande OFF"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False

        cmd = self.devices[device_name].get("command_off")
        success, _ = self._run_script(cmd, device_name)
        return success

    def toggle(self, device_name: str = None) -> bool:
        """Exécute la commande toggle"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return False

        cmd = self.devices[device_name].get("command_toggle")
        if not cmd:
            # Fallback: toggle avec état
            status = self.get_status(device_name)
            if status.get("state") == "on":
                return self.turn_off(device_name)
            else:
                return self.turn_on(device_name)

        success, _ = self._run_script(cmd, device_name)
        return success

    def get_status(self, device_name: str = None) -> Dict:
        """Retourne le statut"""
        device_name = device_name or list(self.devices.keys())[0] if self.devices else None
        if not device_name:
            return {"error": "Aucun appareil"}

        cmd = self.devices[device_name].get("command_status")
        if not cmd:
            return {"state": "unknown"}

        success, output = self._run_script(cmd, device_name)

        # Tente de parser le JSON si disponible
        try:
            return json.loads(output)
        except:
            return {"state": output if success else "error", "raw": output}