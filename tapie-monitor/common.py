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
def grades_firma(proc_pts, cat, size_pts, liab_eur=None):
    """Tři známky: typ řízení, obor, velikost. AAA = všechny sedí."""
    g1 = "A" if proc_pts >= 3 else "B" if proc_pts == 2 else "C"
    g2 = "A" if cat in ("A", "B", "C") else "B" if cat in ("E-SHOP", "?") else "C"
    g3 = "A" if size_pts >= 3 else "B" if size_pts == 2 else "C"
    if liab_eur is not None and liab_eur > config.LIABILITIES_MAX_EUR:
        g3 = "C"
    return g1 + g2 + g3


def grades_app(sig_pts, focus_pts, ratings):
    g1 = "A" if sig_pts >= 3 else "B" if sig_pts == 2 else "C"
    # zaměření je jedno (uživatel 2.11.) – druhá známka = není hra/krypto (ty se vyřazují dřív)
    g2 = "A" if not config.APP_REQUIRE_FOCUS or focus_pts >= 2 else "C"
    if ratings > config.APP_MAX_RATINGS:
        g3 = "C"  # globální gigant – nekoupíš
    else:
        g3 = "A" if ratings >= config.APP_AAA_MIN_RATINGS else "B" if ratings >= config.APP_MIN_RATINGS else "C"
    return g1 + g2 + g3


def rate(points, module="FIRMA"):
    a, b = ((config.APP_RATING_A_MIN, config.APP_RATING_B_MIN) if module == "APP"
            else (config.RATING_A_MIN, config.RATING_B_MIN))
    if points >= a:
        return "A"
    if points >= b:
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
    flag = {"CZ": "🇨🇿", "AT": "🇦🇹", "DE": "🇩🇪", "US": "🇺🇸", "FR": "🇫🇷", "NL": "🇳🇱",
            "IT": "🇮🇹", "ES": "🇪🇸"}.get(c.get("country"), "🌍")
    label = c.get("grades") or c["rating"]
    head = f"<b>[{c['module']}] {esc(label)}</b> · <b>{esc(c['name'])}</b>"
    if c.get("update"):
        head = f"<b>[{c['module']}] {esc(label)} · {esc(c['update'])}</b>\n<b>{esc(c['name'])}</b>"
    lines = [head,
             f"{flag} Země: {esc(c.get('country'))}",
             f"⚖️ {'Řízení' if c['module'] == 'FIRMA' else 'Signál'}: {esc(c.get('procedure'))}",
             f"🏭 Obor: {esc(c.get('field'))}",
             f"👥 Velikost: {esc(c.get('size'))}"]
    if c["module"] == "FIRMA":
        lines.append(f"💶 Závazky: {esc(c.get('liabilities'))}")
    lines.append(f"📇 {'Správce' if c['module'] == 'FIRMA' else 'Vlastník / správce'}: {esc(c.get('contact'))}")
    for n in c.get("notes", []):
        lines.append(f"ℹ️ {esc(n)}")
    if c.get("link"):
        lines.append(f'🔗 <a href="{html.escape(c["link"])}">otevřít zdroj</a>')
    for label, url in c.get("links", []):
        lines.append(f'🔗 <a href="{html.escape(url)}">{esc(label)}</a>')
    if config.ANALYSIS_ENABLED:
        from sources.analysis import format_analysis
        lines.append(format_analysis(c))
    return "\n".join(lines)


def telegram_send(text):
    # Vlastní kanál pro tapie-monitor (nemíchá se s realitami).
    # Token: vlastní bot TAPIE_TELEGRAM_TOKEN, jinak stejný bot jako reality.
    tok = (os.environ.get("TAPIE_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = os.environ.get("TAPIE_TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        log("[telegram] chybí TAPIE_TELEGRAM_CHAT_ID (nebo token) – do Telegramu NEPOSÍLÁM, "
            "vypisuji jen sem:\n" + text)
        return False
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


def split_message(text, limit=3800):
    """Rozdělí dlouhou zprávu po celých řádcích (nikdy uprostřed HTML značky)."""
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(line) > limit:  # extrémně dlouhý řádek – zbav se HTML
            line = re.sub(r"<[^>]+>", "", line)[:limit]
        if cur and len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur.strip():
        parts.append(cur)
    return parts


def telegram_find_chats():
    """Vypíše chaty/kanály, kde bot něco viděl (pro zjištění chat ID)."""
    tok = (os.environ.get("TAPIE_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or "").strip()
    if not tok:
        log("[telegram] chybí token")
        return
    r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=30).json()
    found = {}
    for u in r.get("result", []):
        for k in ("message", "channel_post", "my_chat_member", "edited_channel_post"):
            ch = (u.get(k) or {}).get("chat")
            if ch:
                found[ch["id"]] = (ch.get("type"), ch.get("title") or ch.get("username") or ch.get("first_name"))
    if not found:
        log("[telegram] bot zatím nic neviděl – přidej ho do kanálu jako správce a napiš tam zprávu")
    for cid, (typ, title) in found.items():
        log(f"[telegram] CHAT {cid} | {typ} | {title}")
