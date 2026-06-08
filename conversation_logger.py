import datetime
import os
from pathlib import Path


LOG_DIR = Path(__file__).parent / "logs" / "conversations"


def _ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _today_path() -> Path:
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"{date_str}.md"


def log_user(text: str, source: str = "voice"):
    _ensure_dir()
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    tag = "VOIX" if source == "voice" else "TEXTE"
    path = _today_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] **{tag}** ➤ {text}\n")


def log_system(text: str, source: str = "assistant"):
    _ensure_dir()
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    tag = "BOB" if source == "assistant" else source.upper()
    path = _today_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] *{tag}* ➤ {text}\n\n")


def log_action(action: str, detail: str = ""):
    _ensure_dir()
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    path = _today_path()
    with open(path, "a", encoding="utf-8") as f:
        line = f"[{ts}] `{action}`"
        if detail:
            line += f" — {detail}"
        f.write(line + "\n")
