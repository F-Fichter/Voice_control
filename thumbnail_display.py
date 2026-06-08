import os
import sys
import base64
import webbrowser
import tempfile
import subprocess
import time
import requests
from io import BytesIO
from PIL import Image


def _fetch_img(url):
    try:
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.thumbnail((240, 180), Image.LANCZOS)
        return img
    except Exception:
        return None


def _img_to_b64(img):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def _build_html(items):
    rows_html = ""
    for i, item in enumerate(items):
        num = i + 1
        title = item.get("title", "")[:60]
        thumb = item.get("thumbnail") or item.get("thumbnail_url", "")
        img_tag = ""
        if thumb:
            pil_img = _fetch_img(thumb)
            if pil_img:
                b64 = _img_to_b64(pil_img)
                img_tag = f'<img src="data:image/jpeg;base64,{b64}" alt="{title}">'
            else:
                img_tag = '<div class="no-img">Pas d\'image</div>'
        else:
            img_tag = '<div class="no-img">Pas d\'image</div>'

        rows_html += f"""
        <div class="card">
            <div class="num">[{num}]</div>
            {img_tag}
            <div class="title">{title}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #1a1a2e; color: #eee; display: flex; flex-direction: column;
    align-items: center; min-height: 100vh; padding: 20px;
}}
h1 {{ margin: 20px 0; font-size: 1.4em; color: #e94560; }}
.grid {{
    display: flex; flex-wrap: wrap; justify-content: center; gap: 16px;
    max-width: 900px; width: 100%;
}}
.card {{
    background: #16213e; border-radius: 10px; padding: 12px;
    width: 240px; text-align: center;
    border: 2px solid #0f3460;
}}
.card img {{ width: 100%; border-radius: 6px; display: block; }}
.num {{ font-size: 1.5em; font-weight: bold; color: #e94560; margin-bottom: 8px; }}
.title {{ margin-top: 8px; font-size: 0.85em; color: #ccc; line-height: 1.3; }}
.no-img {{ width: 100%; height: 135px; background: #0f3460; border-radius: 6px;
           display: flex; align-items: center; justify-content: center; color: #555; }}
.footer {{ margin-top: 24px; font-size: 0.8em; color: #555; }}
</style>
</head>
<body>
<h1>&#x1F3B5; S&#xE9;lectionnez une piste</h1>
<div class="grid">{rows_html}</div>
<div class="footer">Dites le num&#xE9;ro &#xE0; voix haute (1-{len(items)})</div>
</body>
</html>"""


def _show_text_list(items):
    print(f"\n  {'='*55}")
    for i, item in enumerate(items[:6], 1):
        t = item.get("title", "?")[:55]
        print(f"  [{i}] {t}")
    print(f"  {'='*55}")


def _open_html(html_path):
    import shutil
    proc = None
    cleanup = None
    if html_path and os.path.exists(html_path):
        try:
            ff_profile = tempfile.mkdtemp(prefix="ff_sel_")
            def _cleanup():
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                shutil.rmtree(ff_profile, ignore_errors=True)
            proc = subprocess.Popen(
                ["firefox", "--no-remote", "--new-instance", "--profile", ff_profile, html_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            proc._cleanup = _cleanup
        except Exception:
            shutil.rmtree(ff_profile, ignore_errors=True)
            try:
                proc = subprocess.Popen(["firefox", html_path],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    proc = subprocess.Popen(["xdg-open", html_path],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    try:
                        webbrowser.open(f"file://{html_path}")
                    except Exception:
                        pass
    return proc


def _close_html(proc):
    cleanup = getattr(proc, '_cleanup', None)
    if cleanup:
        cleanup()
    elif proc:
        try:
            proc.terminate()
        except Exception:
            pass


def _focus_console():
    sys.stdout.write("\a")
    sys.stdout.write("\033[?1049h")
    time.sleep(0.1)
    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()


_DIGIT_WORDS = {
    "premiere": 1, "premier": 1, "un": 1, "une": 1, "1": 1,
    "deuxieme": 2, "second": 2, "seconde": 2, "deux": 2, "2": 2,
    "troisieme": 3, "trois": 3, "3": 3,
    "quatrieme": 4, "quatre": 4, "4": 4,
    "cinquieme": 5, "cinq": 5, "5": 5,
    "sixieme": 6, "six": 6, "6": 6,
    "septieme": 7, "sept": 7, "7": 7,
    "huitieme": 8, "huit": 8, "8": 8,
    "neuvieme": 9, "neuf": 9, "9": 9,
    "dixieme": 10, "dix": 10, "10": 10,
}


def _parse_digit(text, max_items):
    text = text.lower().strip()
    import unicodedata
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('ascii')
    for keyword in ["annule", "annuler", "stop", "quitte", "retour", "rien"]:
        if keyword in text:
            return "__CANCEL__"
    for word, val in sorted(_DIGIT_WORDS.items(), key=lambda x: -len(x[0])):
        if word in text:
            if 1 <= val <= max_items:
                return val - 1
            if val == 0:
                return "__CANCEL__"
    import re
    digits = re.findall(r'\b(\d+)\b', text)
    if digits:
        val = int(digits[0])
        if 1 <= val <= max_items:
            return val - 1
    return None


def _listen_voice(max_items, manager):
    import numpy as np
    app = getattr(manager, "app", None) if manager else None
    recognizer = getattr(app, "recognizer", None)
    if not recognizer:
        print("  (reconnaissance vocale non disponible sur ce système)")
        return None

    print("  (écoutez... dites un chiffre entre 1 et {})".format(max_items))

    speech_attempts = 0
    while speech_attempts < 6:
        if speech_attempts > 0:
            print(f"  (essai {speech_attempts + 1}/6)")
        sys.stdout.write("  🎤 ")
        sys.stdout.flush()
        audio = recognizer.listen(duration=4)
        if audio is None:
            continue
        if np.abs(audio).max() < 0.01:
            continue
        text = recognizer.recognize(audio).lower().strip()
        if not text:
            speech_attempts += 1
            continue
        print(f"'{text}'")
        result = _parse_digit(text, max_items)
        if result is not None:
            return result
        speech_attempts += 1
    return None


def pick_from_results(results, manager=None):
    from key_helper import read_key

    items = results[:6]
    if not items:
        return None
    if len(items) == 1:
        return 0

    html = _build_html(items)
    html_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
        tmp.write(html)
        html_path = tmp.name
        tmp.close()
    except Exception:
        pass

    _show_text_list(items)

    browser = _open_html(html_path)

    tts = getattr(manager, "tts", None) if manager else None
    if tts and hasattr(tts, "speak"):
        tts.speak(f"Choisissez un numéro entre 1 et {len(items)}")
    else:
        print(f"\n  Choisissez un numéro (1-{len(items)}) : ", end="", flush=True)

    idx = _listen_voice(len(items), manager)
    if idx is not None:
        _close_html(browser)
        _focus_console()
        if idx == "__CANCEL__":
            return None
        return idx

    sys.stdout.write(f"\n  Votre choix (1-{len(items)}, Entrée=1, 0=annuler, ESC=annuler) : ")
    sys.stdout.flush()

    while True:
        k = read_key()
        if k['key'] == 'digit':
            val = k['value']
            if 0 <= val <= len(items):
                print(f"{val}")
                _close_html(browser)
                _focus_console()
                if val == 0:
                    return None
                return val - 1
        elif k['key'] == 'enter':
            print("1")
            _close_html(browser)
            _focus_console()
            return 0
        elif k['key'] == 'esc':
            print()
            _close_html(browser)
            _focus_console()
            return None
        elif k['key'] == 'ctrl_space':
            print()
            _close_html(browser)
            _focus_console()
            return '__STOP__'
        elif k['key'] == 'ctrl_c':
            raise KeyboardInterrupt
    return None
