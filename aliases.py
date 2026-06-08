#!/usr/bin/env python3
"""
Aliases - Système d'alias pour contrôler les appareils par des noms courts
Ex: "soleil" → lumière salon, "box" → TV, "musique" → playlist
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


class AliasManager:
    def __init__(self, aliases_file: str = None):
        self.aliases_file = aliases_file or str(Path(__file__).parent / "aliases.json")
        self.aliases: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        """Charge les alias"""
        if Path(self.aliases_file).exists():
            with open(self.aliases_file) as f:
                self.aliases = json.load(f)

    def save(self):
        """Sauvegarde les alias"""
        with open(self.aliases_file, 'w') as f:
            json.dump(self.aliases, f, indent=2, ensure_ascii=False)

    def add(self, alias: str, target: str, action: str = None, description: str = ""):
        """Ajoute un alias"""
        alias = alias.lower().strip()
        self.aliases[alias] = {
            "target": target,
            "action": action,
            "description": description
        }
        self.save()

    def remove(self, alias: str):
        """Supprime un alias"""
        alias = alias.lower()
        if alias in self.aliases:
            del self.aliases[alias]
            self.save()
            return True
        return False

    def get(self, alias: str) -> Optional[Dict]:
        """Récupère un alias"""
        return self.aliases.get(alias.lower())

    def resolve(self, alias: str) -> Optional[tuple]:
        """Résout un alias en (target, action)"""
        data = self.get(alias)
        if data:
            return data.get("target"), data.get("action")
        return None

    def list_all(self) -> Dict:
        """Liste tous les alias"""
        return self.aliases

    def expand_command(self, text: str) -> str:
        """Remplace les alias dans une commande"""
        result = text.lower()

        # Trie par longueur (plus long d'abord) pour éviter conflits
        for alias in sorted(self.aliases.keys(), key=len, reverse=True):
            if alias in result:
                target = self.aliases[alias]["target"]
                # Remplace l'alias par le nom de l'appareil
                result = result.replace(alias, target)

        return result

    def expand_command_full(self, text: str) -> Dict:
        """Récupère l'alias résolu avec target et action"""
        text_lower = text.lower()

        for alias, data in self.aliases.items():
            if alias in text_lower:
                return {
                    "alias": alias,
                    "target": data["target"],
                    "action": data.get("action"),
                    "original": text,
                    "expanded": self.expand_command(text)
                }

        return None


# ===========================================
# ALIAS PRÉDÉFINIS
# ===========================================

DEFAULT_ALIASES = {
    # Lumières
    "soleil": {
        "target": "lampe_salon",
        "action": "toggle",
        "description": "Lumière principale du salon"
    },
    "nuit": {
        "target": "lampe_salon",
        "action": "dim",
        "description": "Lampe en mode nuit"
    },
    "jour": {
        "target": "lampe_salon",
        "action": "brighten",
        "description": "Lampe pleine puissance"
    },

    # TV / Multimédia
    "box": {
        "target": "tv_salon",
        "action": "toggle",
        "description": "Télé du salon"
    },
    "cinema": {
        "target": "tv_salon",
        "action": "netflix",
        "description": "Lance Netflix"
    },
    "youtube": {
        "target": "tv_salon",
        "action": "youtube",
        "description": "Lance YouTube"
    },

    # Musique
    "musique": {
        "target": "playlist_rock",
        "action": "play",
        "description": "Lance playlist rock"
    },
    "radio": {
        "target": "radio_fr",
        "action": "play",
        "description": "Radio France"
    },
    "silence": {
        "target": "music",
        "action": "stop",
        "description": "Arrête la musique"
    },

    # PC
    "ordi": {
        "target": "pc_bureau",
        "action": "toggle",
        "description": "PC du bureau"
    },
    "dodo": {
        "target": "pc_bureau",
        "action": "off",
        "description": "Éteint le PC"
    },

    # Relais ESP32
    "porte": {
        "target": "relais_esp32",
        "action": "toggle",
        "description": "Relais ESP32"
    },
    "ventilo": {
        "target": "relais_esp32",
        "action": "toggle",
        "description": "Ventilateur"
    },
    "cafetiere": {
        "target": "relais_esp32",
        "action": "on",
        "description": "Cafetière"
    },

    # Scènes
    "cinéma": {
        "target": "scene_cinema",
        "action": "activate",
        "description": "Scène кино"
    },
    "départ": {
        "target": "scene_depart",
        "action": "activate",
        "description": "Scène départ"
    },
    "retour": {
        "target": "scene_retour",
        "action": "activate",
        "description": "Scène retour"
    },
}


def init_default_aliases():
    """Initialise les alias par défaut"""
    aliases_file = Path(__file__).parent / "aliases.json"

    if not aliases_file.exists():
        with open(aliases_file, 'w') as f:
            json.dump(DEFAULT_ALIASES, f, indent=2, ensure_ascii=False)
        print(f"Alias par défaut créés: {aliases_file}")

    return aliases_file


if __name__ == "__main__":
    import sys

    manager = AliasManager()

    if len(sys.argv) < 2:
        print("Usage: aliases.py <commande> [args]")
        print("")
        print("Commandes:")
        print("  list              Liste les alias")
        print("  add <alias> <target> [action]  Ajoute un alias")
        print("  remove <alias>    Supprime un alias")
        print("  expand <text>    Teste l'expansion")
        print("  init              Initialise alias par défaut")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        for alias, data in manager.list_all().items():
            print(f"  {alias:12} → {data['target']} ({data.get('action', 'toggle')})")

    elif cmd == "add":
        if len(sys.argv) < 4:
            print("Usage: add <alias> <target> [action]")
        else:
            manager.add(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
            print(f"Alias '{sys.argv[2]}' ajouté → {sys.argv[3]}")

    elif cmd == "remove":
        if manager.remove(sys.argv[2]):
            print(f"Alias '{sys.argv[2]}' supprimé")
        else:
            print(f"Alias '{sys.argv[2]}' non trouvé")

    elif cmd == "expand":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "test musique"
        result = manager.expand_command(text)
        print(f"Original: {text}")
        print(f"Étendu:   {result}")

    elif cmd == "init":
        init_default_aliases()
        print("Alias par défaut initialisés")