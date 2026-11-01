# -*- coding: utf-8 -*-
"""Společné funkce: stahování, stav, hodnocení, Telegram."""
import html
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "data" / "state.json"
CASES_FILE = ROOT / "data" / "cases.json"

UA = "tapie-monitor/1.0 (osobni monitoring; kontakt pres GitHub)"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA


def log(*a):
    print(*a, flush=True)


def now_utc():
    return datetime.now(timezone.utc)


def today():
    return now_utc().strftime("%Y-%m-%d")


def strip_accents(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s):
    return strip_accents(s).upper()


def http(method, url, retries=3, timeout=60, **kw):
    """HTTP s opakováním. Vrací Response nebo vyhodí výjimku."""
    last = None
    for i in range(retries):
        try:
            r = SESSION.request(method, url, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


# ------------------------------------------------------------------ stav
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:  # noqa: BLE001
        log(f"[stav] nejde načíst {path}: {e} – začínám znovu")
        return default


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------ hodnocení
def rate(points):
    if points >= config.RATING_A_MIN:
        return "A"
    if points >= config.RATING_B_MIN:
        return "B"
    return "C"


def size_points(employees):
    """employees = (min, max) nebo None. Vrací (body, je_mimo_rozsah)."""
    if not employees:
        return 1, False
    lo, hi = employees
    if hi < config.EMPLOYEES_MIN or lo > config.EMPLOYEES_MAX:
        return 0, True
    if lo >= config.EMPLOYEES_MIN and hi <= config.EMPLOYEES_MAX:
        return 3, False
    return 2, False  # rozsah se částečně překrývá


def liab_points(eur):
    if eur is None:
        return 1
    return 2 if eur <= config.LIABILITIES_MAX_EUR else 0


def fmt_employees(emp):
    if not emp:
        return "?"
    lo, hi = emp
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


def fmt_eur(eur):
    if eur is None:
        return "?"
    if eur >= 1_000_000:
        return f"{eur / 1_000_000:.1f}".replace(".", ",") + " mil. EUR"
    return f"{eur:,.0f} EUR".replace(",", " ")


def keyword_category(text):
    t = (text or "").lower()
    for cat in ("B", "C", "A", "E-SHOP"):
        if any(k in t for k in config.KEYWORDS_CATEGORY[cat]):
            return cat
    return None


def has_excluded_keyword(text):
    t = (text or "").lower()
    return next((k for k in config.KEYWORDS_EXCLUDED if k in t), None)


EMP_RE = re.compile(
    r"(\d{1,3}(?:[.\s]\d{3})?|\d+)\s*(?:mitarbeiter|beschäftigte|dienstnehmer|"
    r"arbeitnehmer|angestellte|employees|staff|zaměstnanc)", re.I)
LIAB_RE = re.compile(
    r"(?:passiva|verbindlichkeiten|schulden|liabilities)[^0-9]{0,40}"
    r"(\d+(?:[.,]\d+)?)\s*(millionen|mio|million|tausend|mrd|milliarden)?", re.I)


def extract_employees(text):
    m = EMP_RE.search(text or "")
    if not m:
        return None
    n = int(re.sub(r"[.\s]", "", m.group(1)))
    return (n, n) if n < 100000 else None


def extract_liabilities(text):
    m = LIAB_RE.search(text or "")
    if not m:
        return None
    val = float(m.group(1).replace(".", "").replace(",", ".")) if "," in m.group(1) \
        else float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit.startswith(("mio", "million")):
        val *= 1_000_000
    elif unit.startswith(("mrd", "milliard")):
        val *= 1_000_000_000
    elif unit.startswith("tausend"):
        val *= 1000
    return val if val >= 1000 else None


# ------------------------------------------------------------- Telegram
def esc(s):
    return html.escape(str(s if s not in (None, "") else "?"), quote=False)


def format_case(c):
    flag = {"CZ": "🇨🇿", "AT": "🇦🇹", "DE": "🇩🇪", "US": "🇺🇸"}.get(c.get("country"), "🌍")
    head = f"<b>[{c['module']}] {esc(c['rating'])}</b> · <b>{esc(c['name'])}</b>"
    if c.get("update"):
        head = f"<b>[{c['module']}] {esc(c['rating'])} · {esc(c['update'])}</b>\n<b>{esc(c['name'])}</b>"
    lines = [head,
             f"{flag} Země: {esc(c.get('country'))}",
             f"⚖️ {'Signál' if c['module'] == 'APP' else 'Řízení'}: {esc(c.get('procedure'))}",
             f"🏭 Obor: {esc(c.get('field'))}",
             f"👥 Velikost: {esc(c.get('size'))}"]
    if c["module"] == "FIRMA":
        lines.append(f"💶 Závazky: {esc(c.get('liabilities'))}")
    lines.append(f"📇 {'Vlastník' if c['module'] == 'APP' else 'Správce'}: {esc(c.get('contact'))}")
    for n in c.get("notes", []):
        lines.append(f"ℹ️ {esc(n)}")
    if c.get("link"):
        lines.append(f'🔗 <a href="{html.escape(c["link"])}">otevřít zdroj</a>')
    for label, url in c.get("links", []):
        lines.append(f'🔗 <a href="{html.escape(url)}">{esc(label)}</a>')
    return "\n".join(lines)


def telegram_send(text):
    tok = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        log("[telegram] chybí TELEGRAM_TOKEN / TELEGRAM_CHAT_ID – vypisuji jen sem:\n" + text)
        return True
    ok = True
    for part in split_message(text):
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              data={"chat_id": chat, "text": part, "parse_mode": "HTML",
                                    "disable_web_page_preview": "true"}, timeout=30)
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
                r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                                  data={"chat_id": chat, "text": part, "parse_mode": "HTML",
                                        "disable_web_page_preview": "true"}, timeout=30)
            if r.status_code != 200:
                log(f"[telegram] chyba {r.status_code}: {r.text[:200]}")
                ok = False
        except Exception as e:  # noqa: BLE001
            log("[telegram] chyba", e)
            ok = False
        time.sleep(1.1)
    return ok


def split_message(text, limit=3900):
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > limit and cur:
            parts.append(cur)
            cur = ""
        while len(block) > limit:
            parts.append(block[:limit])
            block = block[limit:]
        cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts
