#!/usr/bin/env python3
"""
Command Parser - Analyse et execute les commandes vocales
"""

import re
import json
import os
import unicodedata
from datetime import datetime, date, timedelta
from typing import Dict, List, Any


def _sans_accents(t: str) -> str:
    """Enlève les accents et met en minuscule pour le pattern matching"""
    nfkd = unicodedata.normalize("NFKD", t)
    return nfkd.encode("ascii", "ignore").decode("ascii").lower()


MUSIC_PREFIXES = [
    "joue moi", "joue de la", "joue du", "joue de l", "joue les", "joue la",
    "joue", "play",
]

MUSIC_FILLER = [
    "musique", "son", "morceau", "rock", "jazz", "rap", "metal",
    "classique", "pop", "du son", "de la musique",
]


class CommandParser:
    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager
        self.commands = self._build_commands()
        self.alias_manager = None
        self._init_aliases()

    def _init_aliases(self):
        try:
            from aliases import AliasManager
            self.alias_manager = AliasManager()
        except ImportError:
            pass

    def _build_commands(self) -> List[Dict]:
        return [
            {"patterns": [r"stop", r"arr.te", r"pause"], "action": "music_stop", "device_type": "music"},
            {"patterns": [r"\bannul[ée]?\b", r"\bannulation\b", r"\bcancel\b", r"\babort\b"], "action": "cancel", "device_type": "cancel"},
            {"patterns": [r"\bparle[z]?\b", r"discut"], "action": "chat", "device_type": "chat"},
            {"patterns": [r"joue\s+(genre|style|du|de la|des)\b", r"play\s+genre"], "action": "music_play_genre", "device_type": "music"},
            {"patterns": [r"\bjoue[sz]?\b", r"play"], "action": "music_play", "device_type": "music"},
            {"patterns": [r"\blivre\b"], "action": "audiobook_play", "device_type": "audiobook"},
            {"patterns": [r"allume", r"lumiere"], "action": "bulb_on", "device_type": "bulb"},
            {"patterns": [r"teins", r"eteins"], "action": "bulb_off", "device_type": "bulb"},
            {"patterns": [r"tv", r"tele"], "action": "tv_on", "device_type": "tv"},
            {"patterns": [r"relais", r"porte", r"ventilo"], "action": "relay_on", "device_type": "relay"},
            {"patterns": [r"ordi", r"pc"], "action": "pc_on", "device_type": "pc"},
            {"patterns": [r"volume"], "action": "set_volume", "device_type": "volume"},
            {"patterns": [r"meteo", r"temps", r"quel temps"], "action": "weather", "device_type": "weather"},
            {"patterns": [r"pronostic.*quinte", r"quinte.*pronostic", r"pronostic.*pmu", r"prochain.*quinte", r"quinte.*demain", r"quinte.*aujourd", r"quinte.*jour", r"cours[es].*cheval", r"pronostic.*turf"], "action": "pronostic_pmu", "device_type": "pmu"},
            {"patterns": [r"resultat.*quinte", r"arrivee.*quinte", r"dernier.*quinte", r"resultat.*pmu", r"arrivee.*pmu", r"hier.*quinte", r"quinte.*hier"], "action": "resultat_pmu", "device_type": "pmu"},
            {"patterns": [r"recommence", r"rejoues", r"rejoue", r"recommencer", r"repete", r"repeter", r"repet[ée]", r"rejoue"], "action": "repeat", "device_type": "repeat"},
        ]

    def _extract_genre_query(self, text: str) -> str:
        text = text.lower().strip()
        for prefix in ["joue un genre", "joue du genre", "joue genre", "play genre",
                       "joue du", "joue de la", "joue des", "joue style", "joue un style"]:
            if text.startswith(prefix):
                return text[len(prefix):].strip()
        return text

    def _extract_music_query(self, text: str) -> str:
        text = text.lower().strip()
        for prefix in MUSIC_PREFIXES:
            if text.startswith(prefix):
                query = text[len(prefix):].strip()
                break
        else:
            query = text
        for filler in MUSIC_FILLER:
            if query.startswith(filler + " "):
                query = query[len(filler) + 1:].strip()
        return query

    def parse(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower().strip()
        text_flat = _sans_accents(text)
        result = {"success": False, "text": text}

        if self.alias_manager:
            alias_info = self.alias_manager.expand_command_full(text_lower)
            if alias_info:
                result["success"] = True
                result["action"] = alias_info.get("action", "toggle")
                result["device"] = alias_info.get("target")
                return result

        for cmd in self.commands:
            for pattern in cmd["patterns"]:
                if re.search(pattern, text_flat):
                    result["success"] = True
                    result["action"] = cmd["action"]
                    result["device_type"] = cmd["device_type"]
                    if cmd["action"] == "music_play":
                        result["query"] = self._extract_music_query(text_flat)
                    if cmd["action"] == "music_play_genre":
                        result["query"] = self._extract_genre_query(text_flat)
                        if not result["query"]:
                            result["query"] = "musique"
                    if cmd["action"] == "set_volume":
                        m = re.search(r"volume\s+.*?(\d+)", text_flat)
                        result["level"] = int(m.group(1)) if m else 50
                    if cmd["action"] == "weather":
                        city = re.sub(r"^(meteo|temps|le temps|la meteo|quel temps)\s*", "", text_flat).strip()
                        city = re.sub(r"^sur\s+", "", city).strip().title()
                        result["city"] = city if city else "Surtainville"
                    return self._execute(result)

        return result

    def _execute(self, cmd: Dict) -> Dict:
        action = cmd["action"]
        device_type = cmd.get("device_type")

        if action == "cancel":
            return {"success": True, "action": "cancel"}

        if action == "repeat":
            return {"success": True, "action": "repeat"}

        if action == "chat":
            return {"success": True, "action": "chat", "need_input": True}

        if action == "music_play":
            plugin = self.plugin_manager.plugins.get("music")
            if plugin:
                query = cmd.get("query", cmd.get("text", ""))
                if query:
                    result = plugin.play(query, mode="single") or {}
                    return {"success": True, "action": "music_play", "query": query, "result": result}
                return {"success": True, "action": "music_play", "result": {"error": "Aucune musique specifiee"}}
            return {"success": True, "action": "music_play", "result": {"error": "Plugin musique non disponible"}}

        if action == "music_play_genre":
            plugin = self.plugin_manager.plugins.get("music")
            if plugin:
                query = cmd.get("query", "").strip()
                if query:
                    result = plugin.play(query, mode="genre") or {}
                    return {"success": True, "action": "music_play_genre", "query": query, "result": result}
                return {"success": True, "action": "music_play_genre", "result": {"error": "Aucun genre specifie"}}
            return {"success": True, "action": "music_play_genre", "result": {"error": "Plugin musique non disponible"}}

        if action == "audiobook_play":
            plugin = self.plugin_manager.plugins.get("audiobook")
            if plugin:
                query = cmd.get("text", "").lower().strip()
                for prefix in ["livre audio", "livre"]:
                    if query.startswith(prefix):
                        query = query[len(prefix):].strip()
                        break
                if query:
                    result = plugin.play(query) or {}
                    return {"success": True, "action": "audiobook_play", "query": query, "result": result}
                return {"success": True, "action": "audiobook_play", "result": {"error": "Aucun livre specifie"}}
            return {"success": True, "action": "audiobook_play", "result": {"error": "Plugin livre audio non disponible"}}

        if action == "weather":
            city = cmd.get("city", "Surtainville")
            try:
                import requests
                for essai in [city, "Surtainville"]:
                    geo = requests.get(
                        "https://geocoding-api.open-meteo.com/v1/search",
                        params={"name": essai, "count": 1, "language": "fr", "format": "json"},
                        timeout=10
                    ).json()
                    if geo.get("results"):
                        break
                if not geo.get("results"):
                    return {"success": True, "action": "weather", "result": {"error": f"Ville '{city}' introuvable"}}
                lat, lon = geo["results"][0]["latitude"], geo["results"][0]["longitude"]
                city_name = geo["results"][0].get("name", city)
                w = requests.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat, "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,weather_code",
                        "timezone": "auto",
                        "forecast_days": 9
                    },
                    timeout=10
                ).json()
                codes = {0:"Dégagé",1:"Peu nuageux",2:"Partiellement nuageux",3:"Nuageux",
                         45:"Brumeux",48:"Brouillard givrant",51:"Bruine",53:"Bruine modérée",
                         55:"Bruine dense",61:"Pluie faible",63:"Pluie modérée",65:"Pluie forte",
                         71:"Neige faible",73:"Neige modérée",75:"Neige forte",80:"Averses faibles",
                         81:"Averses modérées",82:"Averses fortes",95:"Orage",96:"Orage grêle",
                         99:"Orage grêle fort"}
                jours = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
                c = w.get("current", {})
                wc = codes.get(c.get("weather_code"), "Inconnu")
                temp = c.get("temperature_2m", "?")
                ressenti = c.get("apparent_temperature", "?")
                humidite = c.get("relative_humidity_2m", "?")
                vent = c.get("wind_speed_10m", "?")
                pluie = c.get("precipitation", 0)
                msg = f"A {city_name}, {wc}. {temp} degrés, ressenti {ressenti}. Humidité {humidite} pour cent. Vent {vent} km/h."
                if pluie and float(pluie) > 0:
                    msg += f" Précipitations {pluie} millimètres."
                daily = w.get("daily", {})
                _tide_by_date = {}
                try:
                    _tide_r = requests.get(
                        "https://tideturtle.com/api/v1/tides",
                        params={"lat": lat, "lon": lon},
                        timeout=10
                    )
                    if _tide_r.status_code == 200:
                        _tide_data = _tide_r.json()
                        _extrema = _tide_data.get("tides", {}).get("data", {}).get("extrema", [])
                        if _extrema:
                            for _e in _extrema:
                                _t = _e.get("time", "")
                                try:
                                    _utc = datetime.strptime(_t.replace("Z", "").replace("+00:00", ""), "%Y-%m-%dT%H:%M:%S.%f")
                                except ValueError:
                                    try:
                                        _utc = datetime.strptime(_t.replace("Z", "").replace("+00:00", ""), "%Y-%m-%dT%H:%M:%S")
                                    except Exception:
                                        continue
                                _local = _utc + timedelta(hours=2)
                                _d = _local.strftime("%Y-%m-%d")
                                _hh = _local.hour
                                _mm = _local.minute
                                _typ = "pleine mer" if _e.get("isHigh") else "basse mer"
                                _ht = _e.get("height", "")
                                if _d not in _tide_by_date:
                                    _tide_by_date[_d] = []
                                _tide_by_date[_d].append(f"{_typ} {_hh:02d}h{_mm:02d} ({_ht}m)")
                except Exception:
                    pass
                if daily and daily.get("time"):
                    d = []
                    for i in range(len(daily["time"])):
                        date = daily["time"][i]
                        try:
                            dt = datetime.strptime(date, "%Y-%m-%d")
                            nom = jours[dt.weekday()]
                        except Exception:
                            nom = date
                        tmax = daily["temperature_2m_max"][i]
                        tmin = daily["temperature_2m_min"][i]
                        precip = daily["precipitation_sum"][i] or 0
                        prob = daily["precipitation_probability_max"][i] or 0
                        code = codes.get(daily["weather_code"][i], "")
                        vent_max = daily["wind_speed_10m_max"][i]
                        parts = []
                        if code:
                            parts.append(code)
                        parts.append(f"{tmin} à {tmax} degrés")
                        if precip and float(precip) > 0:
                            parts.append(f"{precip}mm ({prob}%)")
                        entry = f"{nom}: {', '.join(parts)}"
                        if _tide_by_date.get(date):
                            _tide_str = "; ".join(_tide_by_date[date])
                            entry += f" — {_tide_str}"
                        d.append(entry)
                    if _tide_by_date.get(daily["time"][0]) and len(d) > 0:
                        msg += " Marées: " + "; ".join(_tide_by_date[daily["time"][0]]) + "."
                    if len(d) > 1:
                        msg += " Prévisions. " + ". ".join(d[1:]) + "."
                return {"success": True, "action": "weather", "result": {"forecast": msg}}
            except Exception as e:
                return {"success": True, "action": "weather", "result": {"error": f"Erreur meteo: {e}"}}

        if action == "pronostic_pmu":
            if not self.plugin_manager.plugins.get("pmu"):
                return {"success": True, "action": "pronostic_pmu", "result": {"error": "Plugin PMU non disponible"}}
            return {"success": True, "action": "pronostic_pmu", "result": {}}

        if action == "resultat_pmu":
            plugin = self.plugin_manager.plugins.get("pmu")
            if plugin:
                result = plugin.dernier_quinte()
                return {"success": True, "action": "resultat_pmu", "result": result}
            return {"success": True, "action": "resultat_pmu", "result": {"error": "Plugin PMU non disponible"}}

        if action == "set_volume":
            plugin = self.plugin_manager.plugins.get("music")
            if plugin:
                level = cmd.get("level", 50)
                result = plugin.set_volume(level) or {}
                return {"success": True, "action": "set_volume", "result": result}
            return {"success": True, "action": "set_volume", "result": {"error": "Plugin non disponible"}}

        if action == "music_stop":
            plugin = self.plugin_manager.plugins.get("music")
            if plugin:
                result = plugin.stop() or {}
                return {"success": True, "action": "music_stop", "result": result}

        plugin = self.plugin_manager.get_plugin_for_type(device_type)
        if plugin and hasattr(plugin, "toggle"):
            plugin.toggle(cmd.get("device"))
            return {"success": True, "action": action}

        return {"success": True, "action": action}

    def list_commands(self) -> List[str]:
        return [c["action"] for c in self.commands]
