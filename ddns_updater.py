#!/usr/bin/env python3
"""
Dynamic DNS Updater - Mise à jour automatique DNS pour IP dynamique
Support: DuckDNS, No-IP, Cloudflare, FreeDNS (Afraid.org)
"""

import os
import sys
import time
import socket
import argparse
import json
import logging
from pathlib import Path
from typing import Optional

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

# Providers supportés
PROVIDERS = {
    "duckdns": {
        "url": "https://www.duckdns.org/update",
        "params": {"domains": None, "token": None, "ip": None},
        "response_ok": "GOOD"
    },
    "noip": {
        "url": "https://dynupdate.no-ip.com/nic/update",
        "auth": True,
        "params": {"hostname": None, "myip": None},
        "response_ok": ["good", "nochg"]
    },
    "cloudflare": {
        "url": "https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
        "method": "PUT",
        "auth": "bearer",
        "params": {"content": None}
    },
    "afraid": {
        "url": "https://freedns.afraid.org/api/?action=update&address={ip}&style=json",
        "auth": True,
        "params": {},
        "auth_param": "token"  # FreeDNS key
    }
}


def get_current_ip() -> Optional[str]:
    """Récupère l'IP publique actuelle"""
    services = [
        "https://api.ipify.org?format=txt",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
        "https://checkip.dns.he.net"
    ]

    for service in services:
        try:
            import urllib.request
            with urllib.request.urlopen(service, timeout=10) as resp:
                ip = resp.read().decode().strip()
                if is_valid_ip(ip):
                    return ip
        except Exception as e:
            log.debug(f"Service {service} échoué: {e}")
            continue

    return None


def is_valid_ip(ip: str) -> bool:
    """Valide une adresse IP"""
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False


class DNSUpdater:
    """Mise à jour DNS automatique"""

    def __init__(self, config_file: str = None):
        self.config_file = config_file or str(Path.home() / ".ddns.conf")
        self.config = self.load_config()
        self.last_ip = None

    def load_config(self) -> dict:
        """Charge la configuration"""
        default = {
            "provider": "duckdns",
            "domains": "",
            "token": "",
            "check_interval": 300,
            "log_file": "/var/log/ddns.log",
            "use_ipv6": False
        }

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    user = json.load(f)
                    default.update(user)
            except Exception as e:
                log.error(f"Erreur lecture config: {e}")

        return default

    def save_config(self):
        """Sauvegarde la configuration"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def update_duckdns(self, ip: str) -> bool:
        """Mise à jour DuckDNS"""
        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({
            "domains": self.config["domains"],
            "token": self.config["token"],
            "ip": ip
        })

        url = f"https://www.duckdns.org/update?{params}"

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                result = resp.read().decode().strip()
                return result == "OK" or result == "GOOD"
        except Exception as e:
            log.error(f"DuckDNS erreur: {e}")
            return False

    def update_noip(self, ip: str) -> bool:
        """Mise à jour No-IP"""
        import urllib.request

        url = f"https://dynupdate.no-ip.com/nic/update"
        credentials = f"{self.config['domains']}:{self.config['token']}"

        req = urllib.request.Request(url, data=f"hostname={self.config['domains']}&myip={ip}".encode())
        req.add_header("Authorization", f"Basic {credentials}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.read().decode().split()[0]
                return result in ["good", "nochg"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning("No-IP: Rate limited, attendez 5 min")
            return False
        except Exception as e:
            log.error(f"No-IP erreur: {e}")
            return False

    def update_cloudflare(self, ip: str) -> bool:
        """Mise à jour Cloudflare"""
        import urllib.request
        import json

        # Récupère les identifiants
        zone_id = self.config.get("zone_id")
        record_id = self.config.get("record_id")
        api_key = self.config.get("token")
        domain = self.config.get("domains")

        if not all([zone_id, record_id, api_key]):
            log.error("Cloudflare: token, zone_id, record_id requis")
            return False

        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"

        data = json.dumps({
            "type": "A",
            "name": domain,
            "content": ip,
            "ttl": 120,
            "proxied": False
        }).encode()

        req = urllib.request.Request(url, data=data, method="PUT")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result.get("success", False)
        except Exception as e:
            log.error(f"Cloudflare erreur: {e}")
            return False

    def update_afraid(self, ip: str) -> bool:
        """Mise à jour FreeDNS (afraid.org)"""
        import urllib.request

        # Utilise le token direct
        token = self.config.get("token")

        url = f"https://freedns.afraid.org/nic/update?hostname={self.config['domains']}&address={ip}"

        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Basic {token}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.read().decode()
                return "OK" in result or "has changed" in result or "unchanged" in result
        except Exception as e:
            log.error(f"FreeDNS erreur: {e}")
            return False

    def update(self, force: bool = False) -> bool:
        """Met à jour le DNS si nécessaire"""
        current_ip = get_current_ip()

        if not current_ip:
            log.error("Impossible d'obtenir l'IP publique")
            return False

        if not force and current_ip == self.last_ip:
            log.debug(f"IP inchangée: {current_ip}")
            return True

        log.info(f"Ancienne IP: {self.last_ip or 'N/A'} → Nouvelle IP: {current_ip}")

        provider = self.config.get("provider", "duckdns")
        success = False

        if provider == "duckdns":
            success = self.update_duckdns(current_ip)
        elif provider == "noip":
            success = self.update_noip(current_ip)
        elif provider == "cloudflare":
            success = self.update_cloudflare(current_ip)
        elif provider == "afraid":
            success = self.update_afraid(current_ip)
        else:
            log.error(f"Provider inconnu: {provider}")

        if success:
            self.last_ip = current_ip
            log.info(f"✓ DNS mis à jour: {current_ip}")
        else:
            log.error(f"✗ Échec mise à jour DNS")

        return success

    def run_daemon(self):
        """Mode daemon - mise à jour continue"""
        log.info(f"DDNS daemon démarré - Intervalle: {self.config['check_interval']}s")

        while True:
            try:
                self.update()
            except Exception as e:
                log.error(f"Erreur: {e}")

            time.sleep(self.config["check_interval"])

    def setup_interactive(self):
        """Configuration interactive"""
        print("\n=== Configuration DDNS ===\n")

        print("Provider? (1=DuckDNS, 2=No-IP, 3=Cloudflare, 4=FreeDNS):")
        choice = input("Choix [1]: ").strip() or "1"

        providers = {"1": "duckdns", "2": "noip", "3": "cloudflare", "4": "afraid"}
        self.config["provider"] = providers.get(choice, "duckdns")

        print(f"\nProvider: {self.config['provider']}")

        if self.config["provider"] in ["duckdns", "noip", "afraid"]:
            self.config["domains"] = input("Domain(s) (ex: mondomaine.duckdns.org): ")
            self.config["token"] = input("Token/API Key: ")
        elif self.config["provider"] == "cloudflare":
            self.config["domains"] = input("Domain (ex: mondomaine.com): ")
            self.config["token"] = input("Cloudflare API Token: ")
            self.config["zone_id"] = input("Zone ID: ")
            self.config["record_id"] = input("Record ID: ")

        self.config["check_interval"] = int(input("\nIntervalle检查 (secondes) [300]: ") or "300")

        self.save_config()
        print("\n✓ Configuration sauvegardée dans ~/.ddns.conf")

        # Test immédiat
        print("\nTest de mise à jour...")
        self.update(force=True)


def main():
    parser = argparse.ArgumentParser(description="Dynamic DNS Updater")
    parser.add_argument("--config", help="Fichier config")
    parser.add_argument("--daemon", action="store_true", help="Mode daemon")
    parser.add_argument("--setup", action="store_true", help="Configuration interactive")
    parser.add_argument("--force", action="store_true", help="Force mise à jour")
    parser.add_argument("--ip", help="IP manuelle")
    parser.add_argument("--once", action="store_true", help="Mise à jour unique puis exit")

    args = parser.parse_args()

    updater = DNSUpdater(args.config)

    if args.setup:
        updater.setup_interactive()
    elif args.daemon:
        updater.run_daemon()
    elif args.once:
        updater.update(force=args.force)
    else:
        # Mode once par défaut
        updater.update(force=args.force)


if __name__ == "__main__":
    main()