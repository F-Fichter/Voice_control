#!/usr/bin/env python3
"""
Chat Agent - Agent conversationnel vocal avec LLM
"""

import subprocess
from typing import Dict, List, Optional


class ChatAgent:
    def __init__(self, manager):
        self.manager = manager
        self.tts = manager.tts
        self.conversation: List[Dict] = []
        self.model = None
        self.api_type = None  # "groq", "ollama", "openai", "lmstudio"
        self.max_tokens = 1024
        self.system_prompt = self._default_system_prompt()
        self._init_llm()

    def _default_system_prompt(self) -> str:
        """Prompt système par défaut"""
        loc = self._user_location()
        loc_ctx = f"\nTu te trouves à {loc}. Utilise cette localisation pour les recherches de commerces, horaires, météo, et services à proximité.\n" if loc else ""
        return f"""Tu es bob, un assistant vocal intelligent. Tu dois répondre de manière:
- Detaillee (n hesite pas a developper en plusieurs phrases)
- En français
- Avec une voix naturelle
- Conviviale mais utile{loc_ctx}
Tu es connecté à une maison intelligente. Tu peux contrôler:
- Les lumières et relais
- La musique
- Les appareils Home Assistant

Si l'utilisateur demande de contrôler quelque chose, dis simplement "OK" et exécute l'action.

IMPORTANT: Si des résultats de recherche te sont fournis, tu DOIS les utiliser pour répondre. Ne dis PAS que tu n'as pas accès aux données en temps réel si les résultats de recherche sont disponibles."""

    def _user_location(self) -> str:
        try:
            return self.manager.app.config.get("user_location", "").strip()
        except Exception:
            return ""

    def _init_llm(self):
        """Initialise le LLM (priorité : Groq > Ollama > OpenAI > LM Studio)"""
        if self._check_groq():
            self.api_type = "groq"
            self.model = "llama-3.3-70b-versatile"
            return

        if self._check_ollama():
            self.api_type = "ollama"
            self.model = "llama3.2"
            return

        if self._check_openai():
            self.api_type = "openai"
            self.model = "gpt-4o-mini"
            return

        if self._check_lmstudio():
            self.api_type = "lmstudio"
            self.model = "local"
            return

        print("Chat: Aucun LLM disponible - Mode limité")

    def _check_ollama(self) -> bool:
        """Vérifie Ollama"""
        import requests
        try:
            r = requests.get("http://localhost:11434/api/version", timeout=2)
            return r.status_code == 200
        except:
            return False

    def _check_lmstudio(self) -> bool:
        """Vérifie LM Studio"""
        import requests
        try:
            r = requests.get("http://localhost:1234/v1/models", timeout=2)
            return r.status_code == 200
        except:
            return False

    def _check_groq(self) -> bool:
        """Vérifie clé Groq (gratuit, prioritaire)"""
        key = self.manager.app.config.get("groq_api_key", "")
        return bool(key and key.startswith("gsk_"))

    def _check_openai(self) -> bool:
        """Vérifie clé OpenAI"""
        return "openai_api_key" in self.manager.app.config

    def chat(self, text: str, voice: bool = True) -> str:
        """Envoie un message et retourne la réponse"""
        if not text.strip():
            return ""

        self.conversation.append({"role": "user", "content": text})

        response = self._generate_response()

        if response:
            self.conversation.append({"role": "assistant", "content": response})
            if voice and self.tts:
                self.tts.speak_async(response)
            return response

        print("Chat: Groq a retourné une réponse vide")
        msg = "Désolé, je ne peux pas répondre pour le moment"
        if voice and self.tts:
            self.tts.speak(msg)
        return msg

    def _generate_response(self) -> str:
        """Génère une réponse via LLM"""
        if self.api_type == "groq":
            return self._chat_groq()
        elif self.api_type == "ollama":
            return self._chat_ollama()
        elif self.api_type == "lmstudio":
            return self._chat_lmstudio()
        elif self.api_type == "openai":
            return self._chat_openai()
        else:
            return self._fallback_response()

    def _chat_ollama(self) -> str:
        """Chat via Ollama"""
        import requests

        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation[-10:]

        try:
            r = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["message"]["content"]
        except Exception as e:
            print(f"Ollama error: {e}")
        return ""

    def _chat_lmstudio(self) -> str:
        """Chat via LM Studio"""
        import requests

        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation[-10:]

        try:
            r = requests.post(
                "http://localhost:1234/v1/chat/completions",
                json={
                    "model": "local",
                    "messages": messages,
                    "max_tokens": self.max_tokens
                },
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"LM Studio error: {e}")
        return ""

    def _is_smalltalk(self, text: str) -> bool:
        """Vrai si c'est une salutation/acquiescement (pas besoin de chercher sur le web)"""
        tl = text.lower().strip().rstrip("?!.")
        smalltalk = {
            "bonjour", "salut", "coucou", "hello", "bye", "au revoir",
            "merci", "merci beaucoup", "merci bien", "super", "génial",
            "oui", "non", "peut-être", "d'accord", "ok", "okay",
            "bravo", "parfait", "cool", "très bien", "dac", "d'acc",
            "bonne nuit", "bonsoir", "bonne journée", "à demain",
        }
        return tl in smalltalk or len(tl.split()) <= 2

    def _chat_groq(self) -> str:
        """Chat via Groq API avec recherche internet automatique"""
        import requests
        import time

        api_key = self.manager.app.config.get("groq_api_key", "")
        model = self.model or "llama-3.3-70b-versatile"

        last_user_msg = self.conversation[-1]["content"] if self.conversation else ""
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation[-10:]

        if last_user_msg and not self._is_smalltalk(last_user_msg):
            search_query = self._extract_search_query(last_user_msg)
            print(f"Chat: Recherche web ({search_query})...")
            results = self._search_web(search_query)
            if results:
                search_ctx = f"""Résultats de recherche web pour la question de l'utilisateur:
{results}

INSTRUCTION: Tu DOIS répondre en français en utilisant UNIQUEMENT ces résultats de recherche ci-dessus. Ne dis PAS que tu n'as pas accès aux données en temps réel, que tu es une IA, ou que tu ne peux pas répondre. Les informations sont dans les résultats."""
                messages.insert(1, {"role": "system", "content": search_ctx})

        response = self._groq_completion(api_key, model, messages)
        return response or ""

    def _groq_completion(self, api_key: str, model: str, messages: list) -> str:
        """Appelle l'API Groq avec retry 429 exponentiel + rate limiter client"""
        import requests
        import time

        # Rate limiter client : max 1 requête toutes les 2s
        now = time.time()
        if hasattr(self, '_last_request_time') and self._last_request_time:
            gap = now - self._last_request_time
            if gap < 2.0:
                wait = 2.0 - gap
                print(f"Groq rate limiter: attente {wait:.1f}s (gap {gap:.1f}s)")
                time.sleep(wait)
                now = time.time()
        self._last_request_time = now

        backoff = [5, 10, 20]
        for attempt in range(3):
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": self.max_tokens
                    },
                    timeout=60
                )
                if r.status_code == 200:
                    self._last_request_time = time.time()
                    return r.json()["choices"][0]["message"]["content"]
                if r.status_code == 429:
                    delay = backoff[attempt]
                    print(f"Groq rate limit (429), attente {delay}s... (tentative {attempt+1}/3)")
                    time.sleep(delay)
                    continue
                print(f"Groq chat error ({r.status_code}): {r.text[:200]}")
                break
            except Exception as e:
                print(f"Groq chat error: {e}")
                if attempt < 2:
                    time.sleep(3)
        return ""

    def _extract_search_query(self, text: str) -> str:
        """Extrait les termes de recherche d'une question utilisateur"""
        import re
        q = text.lower().strip()
        q = q.replace("-", " ")
        q = re.sub(r"^(dis[ ]*moi|donne[ ]*moi|je[ ]*veux|je[ ]*voudrais|je[ ]*suis|tu[ ]*peux|est[ ]*ce[ ]*que|qu[ ]*est[ ]*ce[ ]*que)\s+", "", q)
        q = re.sub(r"\s*(s[' ]il te pla[tî]t|stp|merci|s'il vous plaît)$", "", q)
        q = q.strip() or text.lower().strip()
        loc = self._user_location()
        if loc and not any(mot in q for mot in loc.lower().split()):
            mots_locaux = ["horaire", "magasin", "commerce", "pharmacie", "boulangerie", "boucher",
                           "coiffeur", "restaurant", "supermarché", "drive", "station", "coiffure",
                           "tabac", "presse", "docteur", "medecin", "hopital", "clinique",
                           "coiffure", "garage", "mecanicien", "plombier", "electricien",
                           "ouvert", "ferme", "livraison", "retrait", "à proximité", "pres de",
                           "proche", "pieux", "surtainville", "bricolage", "jardin"]
            if any(mot in q for mot in mots_locaux):
                q = f"{q} {loc}"
        return q

    def _search_web(self, query: str, max_results: int = 3) -> str:
        """Recherche internet via DuckDuckGo avec récupération du contenu des pages"""
        loc = self._user_location()
        mots_locaux = ["horaire", "magasin", "commerce", "pharmacie", "boulangerie", "boucher",
                       "coiffeur", "restaurant", "supermarché", "drive", "station", "coiffure",
                       "tabac", "presse", "docteur", "medecin", "hopital", "clinique",
                       "garage", "mecanicien", "plombier", "electricien",
                       "ouvert", "ferme", "livraison", "retrait", "proximite", "proche",
                       "pieux", "surtainville", "bricolage", "jardin", "coiffure"]
        if loc and loc.lower().split()[0] not in query.lower() and any(m in query.lower() for m in mots_locaux):
            query = f"{query} {loc}"
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5, region="fr-fr"))
                if not results:
                    return ""
                lines = []
                urls = []
                qwords = set(query.lower().split())
                seen_urls = set()
                for r in results:
                    url = r.get("href", r.get("link", r.get("url", "")))
                    title = r.get("title", "")
                    body = r.get("body", "")
                    if not title or not body:
                        continue
                    if len(qwords) <= 2 and title.lower().strip(" .,!?") == query.lower().strip():
                        continue
                    lines.append(f"- {title}: {body[:200]}")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        urls.append(url)
                    if len(lines) >= max_results:
                        break
                for url in urls[:2]:
                    try:
                        import requests as _req
                        pr = _req.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                        if pr.status_code == 200:
                            ct = pr.headers.get("content-type", "")
                            if "text/html" in ct or "text/plain" in ct:
                                from bs4 import BeautifulSoup as _BS
                                _s = _BS(pr.text, "lxml")
                                for _tag in _s(["script", "style", "nav", "footer", "header", "aside"]):
                                    _tag.decompose()
                                _txt = _s.get_text(separator=" ", strip=True)
                                _txt = " ".join(_txt.split())[:1500]
                                if _txt:
                                    lines.append(f"[Page] {url}:\n{_txt}")
                    except Exception:
                        pass
                return "\n\n".join(lines)
        except Exception as e:
            print(f"Search error: {e}")
            try:
                import requests
                params = {"action": "opensearch", "search": query, "limit": max_results, "format": "json"}
                r = requests.get("https://fr.wikipedia.org/w/api.php", params=params, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if len(data) >= 3 and data[2]:
                        lines = [f"{data[1][i]}: {data[2][i][:300]}" for i in range(min(len(data[1]), max_results)) if data[2][i]]
                        if lines:
                            return "\n".join(lines)
            except Exception:
                pass
        return ""

    def _chat_openai(self) -> str:
        """Chat via OpenAI API"""
        import requests

        api_key = self.manager.app.config.get("openai_api_key")
        model = self.model or "gpt-4o-mini"

        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation[-10:]

        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": self.max_tokens
                },
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"OpenAI error ({r.status_code}): {r.text[:200]}")
        except Exception as e:
            print(f"OpenAI error: {e}")
        return ""

    def _fallback_response(self) -> str:
        """Réponse simple sans LLM"""
        text = " ".join(self.conversation[-1]["content"].lower().split()[:10])

        # Réponses simples pré-définies
        fallbacks = {
            "bonjour": "Bonjour ! Comment puis-je t'aider ?",
            "salut": "Salut ! Que puis-je faire pour toi ?",
            "merci": "De rien !",
            "comment": "Je vais bien, et toi ?",
            "quoi": "Juste une conversation normale !",
            "qui es": "Je suis bob, ton assistant vocal.",
            "meteo": "Je n'ai pas accès à la météo pour le moment.",
            "heure": "Regarde l'heure sur ta montre !",
            "musique": "Je peux jouer de la musique, dis-moi quoi !",
            "lumière": "Je peux contrôler les lumières !",
        }

        for keyword, response in fallbacks.items():
            if keyword in text:
                return response

        return "Je t'écoute. Qu'est-ce que je peux faire pour toi ?"

    def reset(self):
        """Reset la conversation"""
        self.conversation = []

    def set_model(self, model: str):
        """Change le modèle"""
        self.model = model

    def set_system_prompt(self, prompt: str):
        """Change le prompt système"""
        self.system_prompt = prompt

    def is_available(self) -> bool:
        """Vérifie si le chat est disponible"""
        return self.api_type is not None

    def get_status(self) -> Dict:
        """Retourne le statut"""
        return {
            "available": self.is_available(),
            "api_type": self.api_type,
            "model": self.model,
            "history_length": len(self.conversation)
        }