import re
import locale
import requests
from datetime import date, timedelta, datetime as dt
from typing import Dict, Optional, List, Tuple
from bs4 import BeautifulSoup

try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except:
    pass


class PMUPlugin:
    def __init__(self, manager):
        self.manager = manager
        self._api_base = "https://online.turfinfo.api.pmu.fr/rest/client/1/programme"
        self._headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    def _soup_get(self, url: str) -> Optional[BeautifulSoup]:
        try:
            r = requests.get(url, timeout=15, headers=self._headers)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            print(f"PMU fetch error: {e}")
        return None

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    # ============================================================
    # SOURCE 1: zone-turf.fr
    # ============================================================
    def _scrape_zone_turf(self) -> Optional[dict]:
        soup = self._soup_get("https://www.zone-turf.fr/pronostics/quinte/")
        if not soup:
            return None
        hippo = ""
        h1 = soup.find("h1")
        if h1:
            hippo = self._clean_text(h1.get_text())
            if ":" in hippo:
                hippo = hippo.split(":", 1)[1].strip()
        if not hippo:
            title = soup.find("title")
            if title:
                txt = title.get_text()
                for p in ["Tiercé Quarté Quinté : partants, pronostics et rapports |",
                          "Tiercé Quarté Quinté + :"]:
                    if p in txt:
                        hippo = txt.replace(p, "").strip()
                        break
        prono_selection = ""
        prono_table = soup.find("table", class_=re.compile(r"prono", re.I))
        if prono_table:
            strongs = prono_table.find_all("strong")
            nums = [s.get_text(strip=True) for s in strongs
                    if re.match(r'^\d+$', s.get_text(strip=True))]
            if nums:
                prono_selection = nums[:8]
        horses = []
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                num = self._clean_text(cells[0].get_text())
                if not re.match(r'^\d{1,3}$', num):
                    continue
                b = row.find("b")
                nom = self._clean_text(b.get_text()) if b else ""
                cote = ""
                for cell in cells:
                    txt = self._clean_text(cell.get_text())
                    mc = re.search(r'(\d+[.,]\d+)', txt)
                    if mc:
                        cote = mc.group(1).replace(",", ".")
                        break
                if not cote:
                    for cell in cells:
                        txt = self._clean_text(cell.get_text())
                        mn = re.search(r'\b(\d{1,2})\b', txt)
                        if mn and mn.group(1) != num:
                            cote = mn.group(1)
                            break
                if nom:
                    horses.append({"num": num, "nom": nom, "cote": cote})
        if not horses:
            return None
        return {"hippodrome": hippo, "selection": prono_selection, "chevaux": horses}

    # ============================================================
    # SOURCE 2: turf-fr.com (30+ press sources + consensus)
    # ============================================================
    def _find_turf_fr_quinte_url(self) -> Optional[str]:
        soup = self._soup_get("https://www.turf-fr.com/")
        if not soup:
            return None
        today_str = dt.now().strftime("%d/%m")
        best = None
        links = soup.find_all("a", href=True)
        for a in links:
            href = a["href"]
            if "/pronostics/quinte-turf-fr/" not in href:
                continue
            txt = a.get_text(strip=True)
            ctx = txt + " " + (a.find_parent(["div","li","td"]) or a.parent or a).get_text(strip=True)
            full = href if href.startswith("http") else f"https://www.turf-fr.com{href}"
            if today_str in ctx:
                return full
            if not best:
                best = full
        return best

    def _scrape_turf_fr(self) -> Optional[dict]:
        url = self._find_turf_fr_quinte_url()
        if not url:
            return None
        soup = self._soup_get(url)
        if not soup:
            return None
        hippo = ""
        h1s = soup.find_all("h1")
        if h1s:
            hippo = self._clean_text(h1s[0].get_text())
            if len(h1s) > 1 and len(h1s[1].get_text()) > len(hippo):
                hippo = self._clean_text(h1s[1].get_text())
        tables = soup.find_all("table")
        presse = []
        consensus = []
        chevaux = []
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue
            first_cells = rows[0].find_all(["td", "th"])
            header_cols = [self._clean_text(c.get_text()) for c in first_cells]
            header_text = " ".join(header_cols).lower()

            if "media" in header_text or "col." in header_text:
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    media = self._clean_text(cells[0].get_text())
                    nums = [self._clean_text(c.get_text()) for c in cells[1:]
                            if re.match(r'^\d{1,2}$', self._clean_text(c.get_text()))]
                    if media and nums:
                        presse.append({"media": media, "selection": nums[:8]})
            elif "classement" in header_text or "cite" in header_text or "nombre" in header_text:
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    num = self._clean_text(cells[0].get_text())
                    count = self._clean_text(cells[1].get_text())
                    if re.match(r'^\d{1,3}$', num):
                        m = re.search(r'(\d+)', count)
                        consensus.append({"num": num, "count": int(m.group(1)) if m else 0})
            elif "n" in header_cols[:2] or "chevaux" in header_text or "n°" in header_text:
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    num = self._clean_text(cells[0].get_text())
                    nom = self._clean_text(cells[1].get_text())
                    if re.match(r'^\d{1,3}$', num):
                        nom = re.sub(r'\s*NP\s*$', '', nom).strip()
                        chevaux.append({"num": num, "nom": nom})
        return {
            "hippodrome": hippo,
            "presse": presse,
            "consensus": consensus,
            "chevaux": chevaux,
        }

    # ============================================================
    # SOURCE 3: turfomania.fr (synthèse presse)
    # ============================================================
    def _scrape_turfomania(self) -> Optional[dict]:
        soup = self._soup_get("https://www.turfomania.fr/pronostics/synthese-de-la-presse.php")
        if not soup:
            return None
        text = soup.get_text()
        nums_ordered = re.findall(r'(\d{1,2})\s*[-–]\s+(\d{1,2})', text)
        seen = set()
        chevaux = []
        for a, b in nums_ordered:
            if a not in seen and 1 <= int(a) <= 18:
                seen.add(a)
                chevaux.append({"num": a})
            if b not in seen and 1 <= int(b) <= 18:
                seen.add(b)
                chevaux.append({"num": b})
        if not chevaux:
            nums_all = re.findall(r'\b(\d{1,2})\b', soup.get_text())
            for n in nums_all:
                if n not in seen and 1 <= int(n) <= 18:
                    seen.add(n)
                    chevaux.append({"num": n})
        h1 = soup.find("h1")
        hippo = self._clean_text(h1.get_text()) if h1 else ""
        return {"hippodrome": hippo, "chevaux": chevaux[:16]}

    # ============================================================
    # SOURCE 4: equidia.fr (notes)
    # ============================================================
    def _scrape_equidia(self) -> Optional[dict]:
        soup = self._soup_get("https://www.equidia.fr/pronostics/les-notes-equidia")
        if not soup:
            return None
        hippo = ""
        cards = soup.find_all(class_=lambda c: c and "note-card" in c)
        horses = []
        for card in cards:
            txt = card.get_text()
            m = re.search(r'(\d+)\s*([A-Z][A-Z\s.\'-]+)', txt)
            if m:
                num = m.group(1)
                nom = self._clean_text(m.group(2))
                note_m = re.search(r'Note\s*:\s*(\d+)/20', txt)
                note = note_m.group(1) if note_m else ""
                if re.match(r'^\d{1,3}$', num) and nom:
                    horses.append({"num": num, "nom": nom[:25], "note": note})
        h2s = soup.find_all("h2")
        for h2 in h2s:
            t = h2.get_text(strip=True)
            if "mieux" in t.lower():
                hippo = t
                break
        return {"hippodrome": hippo, "chevaux": horses[:16]}

    # ============================================================
    # SOURCE 5: canalturf.com
    # ============================================================
    def _find_canalturf_quinte_url(self) -> Optional[str]:
        soup = self._soup_get("https://www.canalturf.com/")
        if not soup:
            return None
        links = soup.find_all("a", href=True)
        for a in links:
            href = a["href"]
            if "/pronostics-PMU/" in href and "quinte" not in href.lower():
                full = href if href.startswith("http") else f"https://www.canalturf.com{href}"
                return full
        for a in links:
            href = a["href"]
            if "/pronostics-PMU/" in href:
                full = href if href.startswith("http") else f"https://www.canalturf.com{href}"
                return full
        return None

    def _scrape_canalturf(self) -> Optional[dict]:
        url = self._find_canalturf_quinte_url()
        if not url:
            return None
        soup = self._soup_get(url)
        if not soup:
            return None
        hippo = ""
        h1 = soup.find("h1")
        if h1:
            hippo = self._clean_text(h1.get_text())
        text = soup.get_text()
        selections = re.findall(r'(?:s[eé]lection|s[eé]lectionnez)\s*(?:[:\s]+)([\d\s-]{5,})', text, re.I)
        chevaux = []
        seen = set()
        for sel in selections:
            nums = re.findall(r'\d{1,2}', sel)
            for n in nums:
                if n not in seen and 1 <= int(n) <= 18:
                    seen.add(n)
                    chevaux.append({"num": n})
        if not chevaux:
            for h3 in soup.find_all(["h3", "h4", "strong"]):
                t = h3.get_text(strip=True)
                m = re.search(r'(?:^|\s)(\d{1,2})\s*[-–]\s*(\d{1,2})\s*[-–]\s*(\d{1,2})', t)
                if m:
                    nums = [m.group(i) for i in range(1, 4)]
                    for n in nums:
                        if n not in seen:
                            seen.add(n)
                            chevaux.append({"num": n})
        if not chevaux:
            return None
        return {"hippodrome": hippo, "chevaux": chevaux[:16]}

    # ============================================================
    # SOURCE 6: prono-turf-gratuit.fr (synthèse presse multi-source)
    # ============================================================
    def _scrape_prono_turf_gratuit(self, target_date: str = None) -> Optional[dict]:
        if not target_date:
            target_date = date.today().isoformat()
        d = dt.fromisoformat(target_date)
        url = (
            f"https://prono-turf-gratuit.fr/presse-pmu/"
            f"meilleurs-pronostics-de-la-presse-quinte-du-"
            f"{d.strftime('%A').lower()}-{d.strftime('%d')}-"
            f"{d.strftime('%B').lower()}-{d.strftime('%Y')}/"
        )
        soup = self._soup_get(url)
        if not soup:
            return None
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue
            presse = []
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                media = self._clean_text(cells[0].get_text())
                nums = [self._clean_text(c.get_text()) for c in cells[1:]
                        if re.match(r'^\d{1,2}$', self._clean_text(c.get_text()))]
                if media and nums and media.lower() not in ("cookie", "durée", "description"):
                    presse.append({"media": media, "selection": nums[:8]})
            if presse:
                return {"hippodrome": "", "presse": presse, "selection": presse[0].get("selection", [])}
        return None

    # ============================================================
    # SOURCE 7: turfjeusimple.fr (table chevaux + cotes)
    # ============================================================
    def _scrape_turfjeusimple(self, target_date: str = None) -> Optional[dict]:
        if not target_date:
            target_date = date.today().isoformat()
        d = dt.fromisoformat(target_date)
        url = (
            f"https://www.turfjeusimple.fr/{d.strftime('%Y')}/{d.strftime('%m')}/"
            f"pronostic-quinte-pmu-{d.strftime('%A').lower()}-{d.strftime('%d')}-"
            f"{d.strftime('%B').lower()}-{d.strftime('%Y')}.html"
        )
        soup = self._soup_get(url)
        if not soup:
            return None
        hippo = ""
        h2s = soup.find_all("h2")
        for h2 in h2s:
            t = h2.get_text()
            m = re.search(r"hippodrome\s+de\s+(\w[-\w]+)", t, re.I)
            if m:
                hippo = m.group(1).strip()
                break
        chevaux = []
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                num = self._clean_text(cells[0].get_text())
                if not re.match(r'^\d{1,2}$', num):
                    continue
                nom = self._clean_text(cells[1].get_text()) if len(cells) > 1 else ""
                nom = re.sub(r'\s*\(.*?\)\s*', '', nom).strip()
                cote = ""
                for cell in cells:
                    txt = self._clean_text(cell.get_text())
                    mc = re.search(r'(\d+)/(\d+)', txt)
                    if mc:
                        cote = f"{float(mc.group(1))/float(mc.group(2)):.1f}"
                        break
                if nom:
                    chevaux.append({"num": num, "nom": nom, "cote": cote})
        if not chevaux:
            return None
        return {"hippodrome": hippo, "chevaux": chevaux[:16]}

    # ============================================================
    # SOURCE 8: PMU API officielle
    # ============================================================
    def _get_next_quinte_info(self) -> Optional[dict]:
        for i in range(7):
            jour = (date.today() + timedelta(days=i)).isoformat()
            data = self._get_programme(jour)
            if not data:
                continue
            for q in self._trouver_quinte(data):
                if q["statut"] not in ("FIN_COURSE", "ARRIVEE_DEFINITIVE_COMPLETE"):
                    return {"date": jour, "detail": q}
        return None

    def _scrape_pmu_api(self, target_date: str = None) -> Optional[dict]:
        start = date.fromisoformat(target_date) if target_date else date.today()
        for i in range(7):
            jour = (start + timedelta(days=i)).isoformat()
            try:
                r = requests.get(f"{self._api_base}/{jour}", timeout=15, headers=self._headers)
                if r.status_code != 200:
                    continue
                data = r.json()
            except Exception:
                continue
            prog = data.get("programme", {})
            for rep in prog.get("reunions", []):
                hippo_lib = rep.get("hippodrome", {}).get("libelleCourt",
                          rep.get("hippodrome", {}).get("libelleLong", "?"))
                for c in rep.get("courses", []):
                    statut = c.get("statut", "")
                    if statut in ("FIN_COURSE", "ARRIVEE_DEFINITIVE_COMPLETE"):
                        continue
                    paris = c.get("paris", [])
                    if any(p.get("typePari") == "QUINTE_PLUS" for p in paris):
                        partants = c.get("partants", []) or c.get("participants", [])
                        chevaux = []
                        for p in partants[:16]:
                            num = str(p.get("num") or p.get("numCheval") or p.get("numero", ""))
                            nom = p.get("nom") or p.get("libelle") or p.get("cheval", {}).get("nom", "")
                            cote_ref = p.get("coteReference", "")
                            if num and nom:
                                chevaux.append({"num": num, "nom": nom, "cote": str(cote_ref)})
                        if chevaux:
                            return {
                                "hippodrome": hippo_lib,
                                "libelle": c.get("libelle", ""),
                                "distance": c.get("distance", ""),
                                "chevaux": chevaux,
                                "statut": statut,
                                "date": jour,
                                "horaire": c.get("heureDepart") or c.get("horaire", ""),
                            }
        return None

    # ============================================================
    # PRONOSTIC COMBINE (multi-sources)
    # ============================================================
    def pronostic_complet(self) -> Dict:
        next_info = self._get_next_quinte_info()
        target_date = next_info["date"] if next_info else date.today().isoformat()
        target_detail = (next_info or {}).get("detail", {})

        sources = []

        api = self._scrape_pmu_api(target_date=target_date)
        if api:
            sources.append(("PMU API", api))
        elif next_info:
            chevaux = []
            for p in target_detail.get("partants", [])[:16]:
                num = str(p.get("num") or p.get("numCheval") or p.get("numero", ""))
                nom = p.get("nom") or p.get("libelle") or p.get("cheval", {}).get("nom", "")
                cote_ref = p.get("coteReference", "")
                if num and nom:
                    chevaux.append({"num": num, "nom": nom, "cote": str(cote_ref)})
            sources.append(("PMU API", {
                "hippodrome": target_detail.get("hippodrome", ""),
                "libelle": target_detail.get("libelle", ""),
                "distance": target_detail.get("distance", ""),
                "chevaux": chevaux,
                "horaire": target_detail.get("horaire", ""),
            }))

        zone = self._scrape_zone_turf()
        if zone:
            sources.append(("Zone-Turf", zone))

        turf = self._scrape_turf_fr()
        if turf:
            sources.append(("Turf-FR (Presse)", turf))

        toman = self._scrape_turfomania()
        if toman:
            sources.append(("Turfomania", toman))

        canal = self._scrape_canalturf()
        if canal:
            sources.append(("Canalturf", canal))

        ptg = self._scrape_prono_turf_gratuit(target_date=target_date)
        if ptg:
            sources.append(("Synthèse Presse", ptg))

        tjs = self._scrape_turfjeusimple(target_date=target_date)
        if tjs:
            sources.append(("TurfJeuSimple", tjs))

        if not sources:
            pq = self.prochain_quinte()
            if pq.get("success"):
                return pq
            return {"success": False, "message": "Aucune source disponible pour le pronostic."}

        # Build target race info (API > target_detail)
        race_date_obj = dt.fromisoformat(target_date)
        date_str = race_date_obj.strftime("%A %d %B %Y")
        race_heure = self._format_heure(
            (api or {}).get("horaire", "") or target_detail.get("horaire", "")
        )
        if race_heure:
            date_str += f" à {race_heure}"

        race_hippo = (api or {}).get("hippodrome", "") or target_detail.get("hippodrome", "")
        race_libelle = (api or {}).get("libelle", "") or target_detail.get("libelle", "")

        # Filter web sources: only keep those matching the target race's hippodrome
        target_hippo_lower = race_hippo.lower().strip()
        filtered = []
        for name, data in sources:
            if name == "PMU API":
                filtered.append((name, data))
                continue
            src_hippo = (data.get("hippodrome", "") or "").lower().strip()
            if target_hippo_lower and src_hippo:
                if target_hippo_lower in src_hippo or src_hippo in target_hippo_lower:
                    filtered.append((name, data))
            elif not target_hippo_lower and src_hippo:
                filtered.append((name, data))
            elif target_hippo_lower and not src_hippo:
                # Keep sources without hippodrome (e.g., press consensus covering the day's quinté)
                filtered.append((name, data))
            else:
                filtered.append((name, data))
        sources = filtered

        # Check if we have any useful data (horses from web sources matching target race)
        has_web_pronos = any(
            data.get("selection") or data.get("consensus") or data.get("presse")
            or (data.get("chevaux") and data.get("chevaux")[0].get("nom"))
            for n, data in sources if n != "PMU API"
        )
        api_has_horses = bool(next((d.get("chevaux") for n, d in sources if n == "PMU API"), None))

        lines = []
        header_extra = " — ".join(p for p in [race_hippo, race_libelle] if p)
        lines.append(f"QUINTÉ+ {date_str}{' — ' + header_extra if header_extra else ''}")
        lines.append(f"{'='*60}")

        if not has_web_pronos and not api_has_horses:
            lines.append("Pronostics non encore disponibles pour cette course.")
            return {"success": True, "message": "\n".join(lines)}

        lines.append(f"Sources consultées: {len(sources)}")
        lines.append("")

        hippo = race_hippo
        chevaux_map = {}
        qp_horses = set()
        for name, data in sources:
            if name != "Equidia":
                for h in data.get("chevaux", []):
                    if h["num"].isdigit():
                        qp_horses.add(h["num"])

        for name, data in sources:
            if data.get("hippodrome") and not hippo:
                hippo = data["hippodrome"]
            for h in data.get("chevaux", []):
                n = h["num"]
                if name == "Equidia" and qp_horses and n not in qp_horses:
                    continue
                if n not in chevaux_map:
                    chevaux_map[n] = {"num": n, "nom": h.get("nom", ""), "cotes": {}, "notes": [], "sources": []}
                if h.get("nom") and not chevaux_map[n]["nom"]:
                    chevaux_map[n]["nom"] = h["nom"]
                if h.get("cote"):
                    chevaux_map[n]["cotes"][name] = h["cote"]
                if h.get("note") and h["note"].isdigit():
                    chevaux_map[n]["notes"].append(int(h["note"]))
                chevaux_map[n]["sources"].append(name)

        # --- Détail par source ---
        for name, data in sources:
            lines.append(f"📰 {name}:")
            sel = data.get("selection", [])
            prv = data.get("presse", [])
            con = data.get("consensus", [])
            chev = data.get("chevaux", [])

            if con:
                top8 = con[:8]
                lines.append(f"   📊 Consensus presse: {' - '.join(c['num'] for c in top8)}")
                if prv:
                    for m in prv[:5]:
                        lines.append(f"      {m.get('media','')[:20]:20s} {' - '.join(m.get('selection',[])[:8])}")
            elif prv and len(prv) > 1:
                lines.append(f"   Consensus presse:")
                for m in prv[:8]:
                    if isinstance(m, dict):
                        lines.append(f"      {m.get('media','')[:20]:20s} {' - '.join(m.get('selection',[])[:8])}")
            elif sel:
                lines.append(f"   Sélection: {' - '.join(sel[:8])}")
                if chev:
                    parts = [f"{c['num']}-{c.get('nom', '')[:15]}" for c in chev[:8]]
                    lines.append(f"   Top: {', '.join(parts)}")
            elif prv:
                for m in prv[:5]:
                    if isinstance(m, dict):
                        lines.append(f"   {m.get('media','')}: {' - '.join(m.get('selection',[])[:8])}")
            elif chev:
                top8 = chev[:8]
                parts = [f"{c['num']}{'-'+c.get('nom','')[:12] if c.get('nom') else ''}" for c in top8]
                lines.append(f"   Partants: {', '.join(parts)}")
            lines.append("")

        # --- Vote pondéré multi-source ---
        poids = [10, 8, 6, 5, 4, 3, 2, 1]
        scores = {}

        for name, data in sources:
            sel = data.get("selection", [])
            con = data.get("consensus", [])
            prv = data.get("presse", [])
            chev = data.get("chevaux", [])

            ranking = []
            if con:
                ranking = [c["num"] for c in con]
            elif sel:
                ranking = sel
            elif prv:
                ranking = [c.get("selection", []) for c in prv if isinstance(c, dict)]
                if ranking and isinstance(ranking[0], list):
                    freq = {}
                    for sel_list in ranking:
                        for i, n in enumerate(sel_list[:8]):
                            freq[n] = freq.get(n, 0) + (8 - i)
                    ranking = sorted(freq, key=freq.get, reverse=True)
                else:
                    ranking = [r for r in ranking if isinstance(r, str)]
            elif chev:
                ranking = [c["num"] for c in chev]

            for i, n in enumerate(ranking[:8]):
                scores[n] = scores.get(n, 0) + (poids[i] if i < len(poids) else 1)

        ranked = sorted(scores.items(), key=lambda x: -x[1])

        lines.append(f"{'='*50}")
        lines.append("🏆 PRONOSTIC FINAL (vote pondéré multi-sources):")
        lines.append("")
        if not chevaux_map:
            lines.append("  Partants non encore déclarés pour cette course.")
        else:
            for i, (num, pts) in enumerate(ranked[:10], 1):
                h = chevaux_map.get(num, {})
                nom = h.get("nom", "")
                src_count = len(h.get("sources", []))
                cotes = h.get("cotes", {})
                cote_str = f" - cote: {cotes.get('Zone-Turf', '?')}"
                lines.append(f"  {i:>2}e  {num:<2} {nom:<20}{cote_str}  ({pts} pts, {src_count} sources)")

            np_chevaux = [c for num, c in sorted(chevaux_map.items())
                          if num not in [r[0] for r in ranked[:10]]]
            if np_chevaux:
                lines.append("")
                lines.append("  Autres partants:")
                for h in np_chevaux[:6]:
                    lines.append(f"     {h['num']} - {h['nom']}")

        return {"success": True, "message": "\n".join(lines)}

    # ============================================================
    # ZONE TURF (legacy, for specific queries)
    # ============================================================
    def zone_turf_pronostic(self) -> Dict:
        data = self._scrape_zone_turf()
        if not data:
            return {"success": False, "message": "Impossible de charger zone-turf.fr"}
        now = dt.now()
        date_str = now.strftime("%A %d %B %Y")
        lines = [f"PRONOSTIC QUINTÉ+ — {date_str}"]
        if data.get("hippodrome"):
            lines[0] = f"PRONOSTIC QUINTÉ+ {date_str} — {data['hippodrome']}:"
        lines.append(f"{'='*45}")
        if data.get("selection"):
            lines.append(f"Sélection Zone-Turf: {' - '.join(data['selection'][:8])}")
        lines.append("")
        for h in data.get("chevaux", []):
            cote_str = f" (cote: {h['cote']})" if h.get("cote") else ""
            lines.append(f"  {h['num']} - {h['nom']}{cote_str}")
        return {"success": True, "message": "\n".join(lines)}

    def _extract_zt_datelib(self, soup) -> Tuple[str, str, str, str]:
        h1 = soup.find("h1")
        date_txt = ""
        if h1:
            t = h1.get_text()
            dm = re.search(r'du\s+(\S+\s+\d+\s+\S+)', t)
            if dm:
                date_txt = dm.group(1)
        course = ""
        hippo = ""
        heure = ""
        for h3 in soup.find_all("h3"):
            t = h3.get_text()
            cm = re.search(r'R\d+\s+Course\s+N[°]\d+\s*:\s*(.+)', t)
            if cm:
                course = cm.group(1).strip()
            hm = re.search(r'R\d+\s*[-–]\s*([^<]+?)\s*[-–]\s*(\d+(?:h|:)\d+)', t)
            if hm:
                hippo = hm.group(1).strip()
                heure = hm.group(2).strip().replace("h", ":")
        if not hippo:
            m = re.search(r'R\d+\s*[-–]\s*([^<]+?)\s*[-–]\s*(\d+(?:h|:)\d+)', soup.get_text())
            if m:
                hippo = m.group(1).strip()
                heure = m.group(2).strip().replace("h", ":")
        return date_txt, course, hippo, heure

    def zone_turf_resultat(self) -> Dict:
        soup = self._soup_get("https://www.zone-turf.fr/quinte/rapport/")
        if not soup:
            return self._fallback_resultat()
        arrivee = ""
        arrivee_el = soup.find(string=re.compile(r"Arriv[eé]e\s+officielle", re.I))
        if arrivee_el:
            parent = arrivee_el.find_parent(["div", "p", "td"])
            if parent:
                txt = self._clean_text(parent.get_text())
                m = re.search(r'Arriv[eé]e\s+officielle\s*:\s*([\d\s\-–]+)', txt)
                if m:
                    arrivee = m.group(1).strip()
        if not arrivee:
            m2 = re.search(r'Arriv[eé]e\s+Quint[eé][+]\s+du\s+[\d/]+?\s*:\s*\*{1,2}\s*([\d\s\-–]+)\s*\*{1,2}',
                          soup.get_text())
            if m2:
                arrivee = m2.group(1).strip()
        date_txt, course, hippo, heure = self._extract_zt_datelib(soup)
        if not arrivee:
            return self._fallback_resultat()
        horses = []
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                num = self._clean_text(cells[0].get_text())
                if not re.match(r'^\d{1,3}$', num):
                    continue
                b = row.find("b")
                nom = self._clean_text(b.get_text()) if b else ""
                if nom:
                    horses.append({"num": num, "nom": nom})
        now = dt.now()
        year = now.year
        parts = [f"RÉSULTAT QUINTÉ+"]
        if date_txt:
            parts.append(date_txt + f" {year}")
        if heure:
            parts.append(heure)
        if hippo:
            parts.append(hippo)
        if course:
            c = re.sub(r'^[CR]\d+\s*[-:]\s*', '', course).strip()
            if c:
                parts.append(c)
        parts = [p for p in parts if p]
        if len(parts) == 1:
            parts.append(now.strftime("%A %d %B %Y %H:%M"))
        header = " — ".join(parts)
        lines = [header, f"{'='*50}"]
        arrivee_clean = re.sub(r'[^0-9\s]', '', arrivee).strip()
        lines.append(f"Arrivée: {arrivee_clean}")
        if horses:
            lines.append("")
            nums = arrivee_clean.split()
            for pos, num in enumerate(nums[:5], 1):
                for h in horses:
                    if h["num"] == num:
                        lines.append(f"  {pos}e: {h['num']} - {h['nom']}")
                        break
                else:
                    lines.append(f"  {pos}e: {num}")
        return {"success": True, "message": "\n".join(lines)}

    def _format_heure(self, horaire) -> str:
        if not horaire:
            return ""
        if isinstance(horaire, (int, float)):
            return dt.fromtimestamp(horaire / 1000).strftime("%H:%M")
        h = str(horaire).strip().replace("h", ":")
        if ":" in h:
            return h
        return horaire

    def _fallback_resultat(self) -> Dict:
        for i in range(0, 8):
            jour = (date.today() - timedelta(days=i)).isoformat()
            data = self._get_programme(jour)
            if not data:
                continue
            quintes = self._trouver_quinte(data)
            for q in quintes:
                if q["statut"] in ("FIN_COURSE", "ARRIVEE_DEFINITIVE_COMPLETE") and q.get("arrivee"):
                    names = {}
                    for p in q.get("partants", []):
                        num = str(p.get("num") or p.get("numCheval") or p.get("numero", ""))
                        nom = p.get("nom") or p.get("libelle") or ""
                        if num and nom:
                            names[num] = nom
                    top5 = [str(a[0]) for a in q["arrivee"][:5]]
                    date_obj = dt.fromisoformat(jour)
                    date_fr = date_obj.strftime("%A %d %B %Y")
                    lines = [f"RÉSULTAT QUINTÉ+ — {date_fr}"]
                    heure = self._format_heure(q.get("horaire"))
                    if heure:
                        lines[0] += f" — {heure}"
                    hippo = q.get("hippodrome", "")
                    if hippo:
                        lines[0] += f" — {hippo}"
                    if q.get("libelle"):
                        lines[0] += f" — {q['libelle']}"
                    lines.append(f"{'='*50}")
                    lines.append(f"Arrivée: {' '.join(top5)}")
                    lines.append("")
                    for pos, num in enumerate(top5, 1):
                        nom = names.get(num, "")
                        if nom:
                            lines.append(f"  {pos}e: {num} - {nom}")
                        else:
                            lines.append(f"  {pos}e: {num}")
                    return {"success": True, "message": "\n".join(lines)}
        return {"success": False, "message": "Aucun résultat trouvé."}

    # ============================================================
    # PMU API methods (legacy)
    # ============================================================
    def _get_programme(self, jour: str = None):
        if not jour:
            jour = date.today().isoformat()
        try:
            r = requests.get(f"{self._api_base}/{jour}", timeout=15, headers=self._headers)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def _trouver_quinte(self, data: dict) -> list:
        quintes = []
        prog = data.get("programme", {})
        for rep in prog.get("reunions", []):
            hippo_lib = rep.get("hippodrome", {}).get("libelleCourt",
                      rep.get("hippodrome", {}).get("libelleLong", "?"))
            for c in rep.get("courses", []):
                if any(p.get("typePari") == "QUINTE_PLUS" for p in c.get("paris", [])):
                    quintes.append({
                        "hippodrome": hippo_lib,
                        "num_reunion": rep.get("numOfficiel"),
                        "num_course": c.get("numOrdre"),
                        "libelle": c.get("libelle", ""),
                        "distance": c.get("distance", ""),
                        "horaire": c.get("heureDepart") or c.get("horaire", ""),
                        "statut": c.get("statut", ""),
                        "arrivee": c.get("ordreArrivee", []),
                        "arrivee_definitive": c.get("arriveeDefinitive", False),
                        "partants": c.get("partants", []) or c.get("participants", []),
                    })
        return quintes

    def dernier_quinte(self) -> Dict:
        for i in range(0, 8):
            jour = (date.today() - timedelta(days=i)).isoformat()
            data = self._get_programme(jour)
            if not data:
                continue
            for q in self._trouver_quinte(data):
                if q["statut"] in ("FIN_COURSE", "ARRIVEE_DEFINITIVE_COMPLETE") and q.get("arrivee"):
                    names = {}
                    for p in q.get("partants", []):
                        num = str(p.get("num") or p.get("numCheval") or p.get("numero", ""))
                        nom = p.get("nom") or p.get("libelle") or ""
                        if num and nom:
                            names[num] = nom
                    top5 = [str(a[0]) for a in q["arrivee"][:5]]
                    date_obj = dt.fromisoformat(jour)
                    date_fr = date_obj.strftime("%A %d %B %Y")
                    lines = [f"RÉSULTAT QUINTÉ+ — {date_fr}"]
                    heure = self._format_heure(q.get("horaire"))
                    if heure:
                        lines[0] += f" — {heure}"
                    if q.get("hippodrome"):
                        lines[0] += f" — {q['hippodrome']}"
                    if q.get("libelle"):
                        lines[0] += f" — {q['libelle']}"
                    lines.append(f"{'='*50}")
                    lines.append(f"Arrivée: {' '.join(top5)}")
                    lines.append("")
                    for pos, num in enumerate(top5, 1):
                        nom = names.get(num, "")
                        if nom:
                            lines.append(f"  {pos}e: {num} - {nom}")
                        else:
                            lines.append(f"  {pos}e: {num}")
                    return {"success": True, "date": jour,
                            "message": "\n".join(lines),
                            "detail": q}
        return {"success": False, "message": "Aucun résultat quinté trouvé ces 7 jours."}

    def prochain_quinte(self) -> Dict:
        for i in range(7):
            jour = (date.today() + timedelta(days=i)).isoformat()
            data = self._get_programme(jour)
            if not data:
                continue
            for q in self._trouver_quinte(data):
                if q["statut"] not in ("FIN_COURSE", "ARRIVEE_DEFINITIVE_COMPLETE"):
                    noms = []
                    for p in q.get("partants", [])[:16]:
                        num = p.get("num") or p.get("numCheval") or p.get("numero", "")
                        nom = p.get("nom") or p.get("libelle") or p.get("cheval", {}).get("nom", "")
                        if num and nom:
                            noms.append(f"{num}:{nom}")
                    ptxt = f" Chevaux: {', '.join(noms)}" if noms else ""
                    return {"success": True, "message": f"Prochain quinté le {jour} à {q['hippodrome']}, {q['libelle']}, {q['distance']}m.{ptxt}",
                            "detail": q, "date": jour}
        return {"success": False, "message": "Aucun prochain quinté trouvé dans les 7 jours."}

    def get_commands(self) -> list:
        return ["pronostic_pmu", "resultat_pmu"]
