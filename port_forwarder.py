#!/usr/bin/env python3
"""
Box Port Forwarder - Configuration automatique des redirections de ports
Utilise UPnP/IGD pour configurer la box automatiquement
"""

import socket
import struct
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import argparse
import logging
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# Ports à rediriger
DEFAULT_PORTS = [
    {"port": 25, "protocol": "TCP", "name": "SMTP"},
    {"port": 587, "protocol": "TCP", "name": "Submission"},
    {"port": 465, "protocol": "TCP", "name": "SMTPS"},
    {"port": 993, "protocol": "TCP", "name": "IMAPS"},
    {"port": 143, "protocol": "TCP", "name": "IMAP"},
    {"port": 5000, "protocol": "TCP", "name": "VoiceControl"},
]


class UPnPController:
    """Contrôleur UPnP IGD (box internet)"""

    MCAST_ADDR = "239.255.255.250"
    MCAST_PORT = 1900

    def __init__(self, local_ip: str = None):
        self.local_ip = local_ip or self._get_local_ip()
        self.gateway: Optional[Dict] = None
        self.control_url: Optional[str] = None
        self.service_type: Optional[str] = None

    def _get_local_ip(self) -> str:
        """Récupère l'IP locale"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "192.168.1.100"

    def discover(self, timeout: int = 5) -> bool:
        """Découverte de la box (UPnP/IGD)"""
        log.info(f"Recherche de la box (IP locale: {self.local_ip})...")

        # Requête M-SEARCH
        search_msg = (
            b'M-SEARCH * HTTP/1.1\r\n'
            b'HOST: 239.255.255.250:1900\r\n'
            b'MAN: "ssdp:discover"\r\n'
            b'MX: 3\r\n'
            b'ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n'
            b'\r\n'
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)

        try:
            sock.sendto(search_msg, (self.MCAST_ADDR, self.MCAST_PORT))

            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    response = data.decode('utf-8', errors='ignore')

                    if '200 OK' in response:
                        log.info(f"Box trouvée: {addr[0]}")

                        # Parse Location header
                        for line in response.split('\r\n'):
                            if line.lower().startswith('location:'):
                                location = line.split(':', 1)[1].strip()
                                self._parse_device_desc(location)
                                return True

                except socket.timeout:
                    break

        except Exception as e:
            log.error(f"Erreur découverte: {e}")
        finally:
            sock.close()

        log.warning("Box non trouvée via UPnP, tentative alternative...")
        return self._try_alternative_discovery()

    def _try_alternative_discovery(self) -> bool:
        """Tentative alternative --scan des IPs locales communes-"""
        common_ips = ["192.168.1.1", "192.168.0.1", "192.168.1.254", "192.168.2.1"]

        for ip in common_ips:
            try:
                url = f"http://{ip}/IGatewayDevice.xml"
                req = urllib.request.Request(url, headers={'User-Agent': 'UPnP'})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        self._parse_device_desc(url)
                        return True
            except:
                continue

        # Tente l'interface web classique
        for ip in common_ips:
            try:
                url = f"http://{ip}/"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=3):
                    log.info(f"Interface web détectée: {ip}")
                    self.gateway = {"local": ip}
                    return True
            except:
                continue

        return False

    def _parse_device_desc(self, location: str):
        """Parse le descriptor UPnP"""
        try:
            req = urllib.request.Request(location, headers={'User-Agent': 'UPnP'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml = resp.read()

            root = ET.fromstring(xml)
            ns = {'ns': 'urn:schemas-upnp-org:device-1-0'}

            # Cherche l'IGD
            device = root.find('.//ns:device[deviceType="urn:schemas-upnp-org:device:InternetGatewayDevice:1"]', ns)
            if device is None:
                # Cherche tout device
                device = root.find('.//ns:device', ns)

            if device is None:
                log.warning("IGD non trouvé, tentative manuelle")
                self.gateway = {"local": location.split('/')[2].split(':')[0]}
                return

            # Extrait les URLs
            for service in device.findall('.//ns:service', ns):
                st = service.find('ns:serviceType', ns)
                if st is not None and 'WANIPConnection' in st.text:
                    self.service_type = st.text
                    ctrl = service.find('ns:controlURL', ns)
                    if ctrl is not None:
                        base = '/'.join(location.split('/')[:-1])
                        self.control_url = base + ctrl.text
                        log.info(f"Service IGD trouvé: {self.service_type}")
                        return

            # Tente sans namespace
            for service in device.findall('.//service'):
                st = service.find('serviceType')
                if st is not None and 'WANIPConnection' in st.text:
                    ctrl = service.find('controlURL')
                    if ctrl is not None:
                        self.control_url = location.rsplit('/', 1)[0] + '/' + ctrl.text
                        self.service_type = st.text
                        return

            log.warning("Service de redirection non trouvé")

        except Exception as e:
            log.error(f"Erreur parsing: {e}")

    def add_port(self, external_port: int, protocol: str, internal_port: int = None, description: str = "") -> bool:
        """Ajoute une redirection de port"""
        if not self.control_url:
            log.error("Box non connectée - Lancez discover() d'abord")
            return False

        internal_port = internal_port or external_port

        # SOAPE requête
        soap_body = f'''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body>
<u:AddPortMapping xmlns:u="urn:schemas-upnp-org:service:{self.service_type}">
<NewRemoteHost></NewRemoteHost>
<NewExternalPort>{external_port}</NewExternalPort>
<NewProtocol>{protocol.upper()}</NewProtocol>
<NewInternalPort>{internal_port}</NewInternalPort>
<NewInternalClient>{self.local_ip}</NewInternalClient>
<NewEnabled>1</NewEnabled>
<NewPortMappingDescription>{description or 'VoiceControl'}</NewPortMappingDescription>
<NewLeaseDuration>0</NewLeaseDuration>
</u:AddPortMapping>
</s:Body>
</s:Envelope>'''

        headers = {
            'SOAPACTION': f'"urn:schemas-upnp-org:service:{self.service_type}#AddPortMapping"',
            'Content-Type': 'text/xml; charset="utf-8"'
        }

        try:
            req = urllib.request.Request(
                self.control_url,
                data=soap_body.encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info(f"✓ Port {external_port}/{protocol} → {self.local_ip}:{internal_port} redirigé")
                return True

        except urllib.error.HTTPError as e:
            if e.code == 500:
                log.warning(f"Port {external_port} déjà redirigé")
                return True
            log.error(f"Erreur HTTP: {e.code}")
        except Exception as e:
            log.error(f"Erreur: {e}")

        return False

    def remove_port(self, external_port: int, protocol: str) -> bool:
        """Supprime une redirection"""
        if not self.control_url:
            return False

        soap_body = f'''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body>
<u:DeletePortMapping xmlns:u="urn:schemas-upnp-org:service:{self.service_type}">
<NewRemoteHost></NewRemoteHost>
<NewExternalPort>{external_port}</NewExternalPort>
<NewProtocol>{protocol.upper()}</NewProtocol>
</u:DeletePortMapping>
</s:Body>
</s:Envelope>'''

        headers = {
            'SOAPACTION': f'"urn:schemas-upnp-org:service:{self.service_type}#DeletePortMapping"',
            'Content-Type': 'text/xml; charset="utf-8"'
        }

        try:
            req = urllib.request.Request(
                self.control_url,
                data=soap_body.encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info(f"✓ Port {external_port}/{protocol} supprimé")
                return True
        except Exception as e:
            log.error(f"Erreur: {e}")
            return False

    def get_external_ip(self) -> Optional[str]:
        """Récupère l'IP publique"""
        if not self.control_url:
            return None

        soap_body = '''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body>
<u:GetExternalIPAddress xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">
</u:GetExternalIPAddress>
</s:Body>
</s:Envelope>'''

        headers = {
            'SOAPACTION': '"urn:schemas-upnp-org:service:WANIPConnection:1#GetExternalIPAddress"',
            'Content-Type': 'text/xml; charset="utf-8"'
        }

        try:
            req = urllib.request.Request(self.control_url, data=soap_body.encode(), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml = resp.read().decode()
                root = ET.fromstring(xml)
                ip = root.find('.//NewExternalIPAddress')
                if ip is not None:
                    return ip.text
        except Exception as e:
            log.error(f"Erreur IP externe: {e}")

        return None

    def setup_all(self, ports: List[Dict] = None):
        """Configure toutes les redirections"""
        ports = ports or DEFAULT_PORTS

        log.info(f"Configuration de {len(ports)} ports...")
        for p in ports:
            self.add_port(
                p["port"],
                p["protocol"],
                p.get("internal_port"),
                p.get("name", "")
            )


def main():
    parser = argparse.ArgumentParser(description="Box Port Forwarder")
    parser.add_argument("--setup", action="store_true", help="Configure tous les ports")
    parser.add_argument("--status", action="store_true", help="Affiche le statut")
    parser.add_argument("--add", type=int, help="Ajoute un port")
    parser.add_argument("--remove", type=int, help="Supprime un port")
    parser.add_argument("--protocol", default="TCP", help="Protocol (TCP/UDP)")
    parser.add_argument("--local-ip", help="IP locale (détecté automatiquement)")
    parser.add_argument("--list", action="store_true", help="Liste les ports par défaut")

    args = parser.parse_args()

    upnp = UPnPController(args.local_ip)

    if args.list:
        print("\nPorts à configurer:")
        for p in DEFAULT_PORTS:
            print(f"  {p['port']:>5}/{p['protocol']} - {p['name']}")
        return

    if not upnp.discover():
        log.error("Box non trouvée. Solutions:")
        log.error("  - Vérifiez que UPnP est activé sur la box")
        log.error("  - Vérifiez le pare-feu")
        return

    ext_ip = upnp.get_external_ip()
    if ext_ip:
        log.info(f"IP externe: {ext_ip}")

    if args.setup:
        upnp.setup_all()

    elif args.add:
        upnp.add_port(args.add, args.protocol, description="VoiceControl")

    elif args.remove:
        upnp.remove_port(args.remove, args.protocol)

    elif args.status:
        ext_ip = upnp.get_external_ip()
        print(f"\n=== Statut ===")
        print(f"IP locale:  {upnp.local_ip}")
        print(f"IP externe: {ext_ip or 'Inconnue'}")
        print(f"Box:        {upnp.gateway}")

    else:
        print("Usage: port_forwarder.py [--setup|--add PORT|--list]")
        print("\nExemples:")
        print("  --list          Affiche les ports")
        print("  --setup         Configure tous les ports")
        print("  --add 443       Ajoute redirection port 443")


if __name__ == "__main__":
    main()