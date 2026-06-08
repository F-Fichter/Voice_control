import subprocess
import os
import time
import shlex
import shutil
import tempfile
import threading
from typing import Dict, List


class MusicPlayerPlugin:
    def __init__(self, manager):
        self.manager = manager
        self.currently_playing = None
        self.player_process = None

    def search_youtube(self, query: str, max_results: int = 8) -> list:
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': f'ytsearch{max_results}',
                'format': 'bestaudio/best',
                'noplaylist': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(query, download=False)
                if results and 'entries' in results:
                    return [
                        {
                            'id': entry['id'],
                            'title': entry.get('title', 'Unknown'),
                            'duration': entry.get('duration', 0),
                            'url': entry.get('webpage_url', entry.get('id')),
                            'thumbnail': f'https://i.ytimg.com/vi/{entry["id"]}/default.jpg',
                        }
                        for entry in results['entries'] if entry
                    ]
                elif results:
                    return [{
                        'id': results['id'],
                        'title': results.get('title', 'Unknown'),
                        'duration': results.get('duration', 0),
                        'url': results.get('webpage_url', results.get('id')),
                        'thumbnail': f'https://i.ytimg.com/vi/{results["id"]}/default.jpg',
                    }]
        except Exception as e:
            print(f"Erreur recherche: {e}")
        return []

    def _build_script(self, urls: List[str]) -> str:
        lines = ['#!/bin/sh']
        for u in urls:
            uq = shlex.quote(u.strip())
            lines.append(
                f'yt-dlp -q --no-warnings --no-playlist -f '
                f"'best[height<=720]/best[height<=1080]/best' -o - {uq} | "
                f'mpv --fullscreen --cache=no --no-keep-open --loop=no -'
            )
            lines.append('if [ $? -ge 2 ]; then continue; fi')
        return '\n'.join(lines) + '\n'

    def play(self, query: str = None, url: str = None, mode: str = "single") -> Dict:
        self.stop()

        if not shutil.which('mpv'):
            return {"error": "mpv requis mais introuvable"}

        if url:
            results = [{'url': url, 'title': url.split('/')[-1][:50]}]
            title = url.split('/')[-1][:50]
        elif query:
            if mode == "genre":
                results = self.search_youtube(query + " music", max_results=10)
                if not results:
                    return {"error": "Aucun résultat trouvé"}
                title = f"{len(results)} morceaux de {query}"
            else:
                results = self.search_youtube(query, max_results=6)
                if not results:
                    return {"error": "Aucun résultat trouvé pour ce titre"}
                if len(results) > 1:
                    from thumbnail_display import pick_from_results
                    idx = pick_from_results(results, manager=self.manager)
                    if idx == '__STOP__':
                        self.stop()
                        book = self.plugin_manager.plugins.get("audiobook")
                        if book: book.stop()
                        return {"error": "Stop"}
                    if idx is None:
                        return {"error": "Sélection annulée"}
                    selected = results[idx]
                else:
                    selected = results[0]
                title = selected['title'][:80]
                url = selected['url']
                results = [selected]
        else:
            return {"error": "URL ou recherche requise"}

        script = self._build_script([r['url'] for r in results])
        fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='vc_music_')
        with os.fdopen(fd, 'w') as f:
            f.write(script)
        os.chmod(script_path, 0o755)

        try:
            env = os.environ.copy()
            env['DISPLAY'] = env.get('DISPLAY', ':0')
            self.player_process = subprocess.Popen(
                ['/bin/sh', script_path],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(0.5)
            if self.player_process.poll() is not None:
                self.player_process = None
                try:
                    os.remove(script_path)
                except Exception:
                    pass
                return {"error": "Le player s'est arrêté immédiatement (URL invalide ?)"}
            self.currently_playing = {
                'title': title,
                'url': results[0]['url'],
                'status': 'playing',
                'count': len(results),
                '_script': script_path,
            }
            threading.Thread(target=self._monitor_playback, daemon=True).start()
            return {"success": True, "playing": title}
        except Exception as e:
            self.player_process = None
            try:
                os.remove(script_path)
            except Exception:
                pass
            return {"error": str(e)}

    def _monitor_playback(self):
        proc = self.player_process
        if not proc:
            return
        try:
            proc.wait()
        except Exception:
            pass
        if self.player_process is not proc:
            return
        if not self.currently_playing:
            return
        sp = self.currently_playing.pop('_script', None)
        if sp and os.path.exists(sp):
            try:
                os.remove(sp)
            except Exception:
                pass
        self.currently_playing = None
        self.player_process = None

    def stop(self) -> Dict:
        if self.player_process:
            try:
                self.player_process.terminate()
                self.player_process.wait(timeout=2)
            except Exception:
                pass

        subprocess.run(['pkill', '-9', '-f', 'vc_music_'], capture_output=True)
        for _ in range(5):
            subprocess.run(['pkill', '-9', '-f', 'mpv.*--fullscreen'], capture_output=True)
            subprocess.run(['pkill', '-9', '-f', 'yt-dlp.*--no-warnings.*--no-playlist'], capture_output=True)
            time.sleep(0.2)
        if self.player_process:
            try:
                self.player_process.wait(timeout=1)
            except Exception:
                pass
            self.player_process = None
        if self.currently_playing:
            sp = self.currently_playing.pop('_script', None)
            if sp and os.path.exists(sp):
                try:
                    os.remove(sp)
                except Exception:
                    pass
        self.currently_playing = None
        return {"success": True, "status": "stopped"}

    def get_status(self) -> Dict:
        if self.currently_playing:
            return {"playing": self.currently_playing['title'], "status": "playing"}
        return {"status": "stopped"}

    def now_playing(self) -> str:
        if self.currently_playing:
            c = self.currently_playing
            if c.get('count', 1) > 1:
                return f"\u266a Playlist: {c['title']}"
            return f"\u266a {c['title']}"
        return "Aucune musique"

    def set_volume(self, level: int) -> Dict:
        level = max(0, min(100, level))
        try:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                           capture_output=True, timeout=5)
            return {"success": True, "level": level}
        except Exception as e:
            return {"success": False, "error": str(e)}
