import subprocess
import time
import re
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List


class AudiobookPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.currently_playing = None
        self.player_process = None
        self.yt_proc = None
        self._waiter = None

    def _search_litteratureaudio(self, query: str) -> List[dict]:
        try:
            import requests
            from urllib.parse import quote
            seen = set()
            results = []
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"}
            for search_url in [
                f"https://www.litteratureaudio.com/?s={quote(query)}&post_type=station",
                f"https://www.litteratureaudio.com/page/1/?s={quote(query)}",
            ]:
                try:
                    r = requests.get(search_url, timeout=8, headers=headers)
                except Exception:
                    continue
                if r.status_code != 200:
                    continue
                for sid in re.findall(r'data-play-id="(\d+)"', r.text):
                    if sid not in seen:
                        seen.add(sid)
                        results.append({"title": f"station {sid}", "url": f"https://www.litteratureaudio.com/livre-audio/{sid}"})
                for href, title in re.findall(r'<a href="(https?://[^"]+)"[^>]*>([^<]+)', r.text):
                    clean = href.split("&")[0]
                    if clean not in seen and "litteratureaudio.com" in clean:
                        seen.add(clean)
                        results.append({"title": title.strip()[:80], "url": clean})
            return results[:10]
        except Exception as e:
            print(f"litteratureaudio search error: {e}")
        return []

    def _search_youtube_direct(self, query: str, max_results: int = 5) -> list:
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True, 'no_warnings': True,
                'default_search': f'ytsearch{max_results}',
                'format': 'bestaudio/best',
                'noplaylist': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(query, download=False)
                if results and 'entries' in results:
                    return [{'url': e['webpage_url'], 'title': e.get('title', '?')[:80],
                             'thumbnail': f'https://i.ytimg.com/vi/{e["id"]}/default.jpg'}
                            for e in results['entries'] if e]
        except Exception as e:
            print(f"YouTube search error: {e}")
        return []

    def _extract_archive_org(self, page_url: str, timeout: int = 15) -> str:
        """Extract direct audio URL from archive.org via Metadata API"""
        import requests
        try:
            m = re.search(r'/details/([^/?&#]+)', page_url)
            if not m:
                return None
            item_id = m.group(1)
            r = requests.get(f"https://archive.org/metadata/{item_id}", timeout=timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            files = data.get("files", [])
            audio_exts = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus"}
            for f in files:
                name = f.get("name", "")
                ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext in audio_exts:
                    return f"https://archive.org/download/{item_id}/{name}"
            return None
        except Exception as e:
            print(f"archive.org error: {e}")
        return None

    def _extract_litteratureaudio(self, page_url: str, timeout: int = 15) -> str:
        """Extract audio URL from litteratureaudio.com via WP REST API (v2/station)"""
        import requests
        try:
            html = requests.get(page_url, timeout=timeout).text
            station_ids = re.findall(r'data-play-id="(\d+)"', html)
            if not station_ids:
                station_ids = re.findall(r'post-(\d+).*station', html)
            if not station_ids:
                return None
            for sid in station_ids[:5]:
                api = f"https://www.litteratureaudio.com/wp-json/wp/v2/station/{sid}"
                r = requests.get(api, timeout=timeout)
                if r.status_code != 200:
                    continue
                data = r.json()
                meta = data.get("meta", {})
                stream = meta.get("stream") or meta.get("download_url") or meta.get("url")
                if stream:
                    return stream
            return None
        except Exception as e:
            print(f"litteratureaudio error: {e}")
        return None

    def _extract_audio(self, page_url: str) -> str:
        """Extract audio URL from various sources"""
        domain = page_url.lower()

        if "archive.org" in domain:
            result = self._extract_archive_org(page_url)
            if result:
                return result

        if "litteratureaudio.com" in domain:
            result = self._extract_litteratureaudio(page_url)
            if result:
                return result

        yt_cmd = ["yt-dlp", "-g", "--format", "bestaudio", "--no-warnings", page_url]
        try:
            r = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip().split("\n")[0]
        except subprocess.TimeoutExpired:
            pass
        return None

    def play(self, query: str = None, url: str = None) -> Dict:
        player = self._get_player_cmd()
        if not player:
            return {"error": "Aucun player audio (mpv requis)"}
        self.stop()

        play_url = None
        title = ""

        if url:
            page_url = url
            direct = self._extract_audio(url) or url
            if not direct:
                return {"error": "Impossible d'extraire le flux audio"}
            if any(x in page_url for x in ['youtube.com','youtu.be','soundcloud.com']):
                play_url = page_url
            else:
                play_url = direct
            title = url.split("/")[-1][:50]
        elif query:
            play_url = None

            yt_results = self._search_youtube_direct(query, max_results=6)
            if len(yt_results) == 1:
                sel = yt_results[0]
                play_url = sel["url"]
                title = sel["title"]
                print(f"Audiobook: YouTube '{title}'")
            elif len(yt_results) > 1:
                from thumbnail_display import pick_from_results
                idx = pick_from_results(yt_results, manager=self.manager)
                if idx == '__STOP__':
                    self.stop()
                    music = self.manager.plugins.get("music")
                    if music: music.stop()
                    return {"error": "Stop"}
                if idx is None:
                    return {"error": "Sélection annulée"}
                sel = yt_results[idx]
                play_url = sel["url"]
                title = sel["title"]
                print(f"Audiobook: YouTube '{title}'")

            if not play_url:
                lit_results = self._search_litteratureaudio(query)
                for r in lit_results:
                    direct = self._extract_litteratureaudio(r["url"]) if "/livre-audio/" in r["url"] else self._extract_audio(r["url"])
                    if direct:
                        play_url = direct
                        title = r["title"]
                        print(f"Audiobook: LitteratureAudio '{title}'")
                        break

            if not play_url:
                return {"error": "Aucun flux audio trouvé pour ce livre"}

        try:
            print(f"Audiobook: playing {play_url[:100]}")
            yt_cmd = ["yt-dlp", "-q", "--no-warnings", "--no-playlist", "-o", "-"]
            if any(x in play_url for x in ['youtube.com','youtu.be','soundcloud.com']):
                yt_cmd += ["-f", "bestaudio"]
            yt_cmd.append(play_url)
            self.yt_proc = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.player_process = subprocess.Popen(
                [player, "--no-video", "--cache=no", "--no-keep-open", "--loop=no", "-"],
                stdin=self.yt_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.yt_proc.stdout.close()
            time.sleep(0.5)
            if self.player_process.poll() is not None:
                self.player_process = None
                self.yt_proc.terminate()
                self.yt_proc = None
                return {"error": f"Lecture impossible: {play_url[:80]}"}
            self._waiter = threading.Thread(target=self._wait_mpv, daemon=True)
            self._waiter.start()
            self.currently_playing = {"title": title, "url": play_url, "status": "playing"}
            return {"success": True, "playing": title}
        except Exception as e:
            self.player_process = None
            return {"error": str(e)}

    def stop(self) -> Dict:
        if self.yt_proc:
            self.yt_proc.terminate()
            try:
                self.yt_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.yt_proc.kill()
                self.yt_proc.wait()
            self.yt_proc = None
        if self.player_process:
            self.player_process.terminate()
            try:
                self.player_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.player_process.kill()
                self.player_process.wait()
            self.player_process = None
        subprocess.run(["pkill", "-f", "mpv.*--no-video"], capture_output=True)
        self.currently_playing = None
        return {"success": True, "status": "stopped"}

    def _wait_mpv(self):
        proc = self.player_process
        if not proc:
            return
        try:
            proc.wait()
        except Exception:
            pass
        if self.player_process is not proc:
            return
        self.player_process = None
        if self.yt_proc:
            try:
                self.yt_proc.wait(timeout=5)
            except Exception:
                self.yt_proc.kill()
                self.yt_proc.wait()
            self.yt_proc = None
        self.currently_playing = None

    def get_status(self) -> Dict:
        if self.currently_playing:
            return {"playing": self.currently_playing["title"], "status": "playing"}
        return {"status": "stopped"}

    def _get_player_cmd(self) -> str:
        for player in ["mpv", "mplayer", "ffplay"]:
            if subprocess.run(["which", player], capture_output=True).returncode == 0:
                return player
        return None
