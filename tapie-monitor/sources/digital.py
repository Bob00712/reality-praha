# -*- coding: utf-8 -*-
"""Modul DIGITAL – upadající digitální byznys v Evropě k převzetí
(model Bending Spoons v menším: zavedený digitální produkt s uživateli,
který vlastník neutáhne – insolvence, hledá kupce/investora, odprodej).

Zdroj: Google News RSS v jazycích EU trhů (DE, AT, FR, NL, IT, ES, CZ, EN).
Případ vznikne jen ze zprávy, která obsahuje ZÁROVEŇ:
  1. silný signál (insolvence / redressement / faillissement / concurso /
     hledá se kupec či investor / prodej / ukončení),
  2. digitální produkt (app, platforma, SaaS, online, e-shop, software),
  3. konkrétní velikost v textu (počet uživatelů/zákazníků nebo zaměstnanců).
Bez čísla o velikosti zpráva AAA nedostane (a nepošle se).
"""
import hashlib
import re

import config
from common import http, log
from sources import news

# klíčová slova (malými písmeny, stačí část slova)
STRONG = [
    "insolvenz", "insolvency", "insolvence", "insolvent", "redressement judiciaire",
    "liquidation judiciaire", "procédure de sauvegarde", "faillissement", "failliet",
    "doorstart", "concordato", "fallimento", "liquidazione", "concurso de acreedores",
    "preconcurso", "into administration", "administrators", "repreneur",
    "investor gesucht", "investorensuche", "käufer gesucht", "kupec", "buyer sought",
    "looking for a buyer", "for sale", "zu verkaufen", "à vendre", "te koop",
    "acquirente", "comprador", "shut down", "schließt", "stellt den betrieb ein",
    "cessation", "chiude", "cierra", "ukončuje", "konec služby",
]
MEDIUM = ["layoff", "lays off", "laid off", "job cuts", "cuts staff", "cuts jobs", "slashes",
          "entlass", "stellenabbau", "licenciement", "ontslag", "licenziament", "despido",
          "propouštění", "restructur", "restrukturier"]
# „nedaří se“ – stejně silné jako insolvence (prostor převzít a nakopnout)
STRUGGLE = [
    "struggl", "in trouble", "losing users", "lost users", "user decline", "declining users",
    "revenue fell", "revenue dropped", "revenue decline", "sales slump", "burn rate",
    "runway", "running out of cash", "out of money", "fails to raise", "failed to raise",
    "down round", "fire sale", "distressed", "wind down", "winds down", "winding down",
    "sunset", "sunsetting", "shutting down", "to shut", "closes its doors", "pulls the plug",
    "strategic review", "strategic options", "strategic alternatives", "seeking a buyer",
    "explores sale", "exploring a sale", "up for sale", "pivot", "founder steps down",
    "ceo steps down", "rettungs", "schieflage", "kriselt", "krise", "geht das geld aus",
    "en difficulté", "difficultés", "en crise", "in difficoltà", "en apuros", "v potížích",
]
DIGITAL = [
    "app", "plattform", "platform", "plateforme", "piattaforma", "plataforma",
    "platforma", "saas", "software", "online", "e-commerce", "onlineshop", "e-shop",
    "webshop", "marketplace", "marktplatz", "start-up", "startup", "aplikac",
    "applicazione", "aplicación", "digital", "subscription", "abonnement",
]
EXCLUDED = config.APP_EXCLUDED_KEYWORDS + [
    "crowdinvest", "crowdfunding", "kryptob", "krypto", "immobilien", "real estate",
    "baufirma", "bauunternehm", "restaurant", "hotel", "gastronomie", "lieferdienst",
    "quick commerce",
]

USERS_RE = re.compile(
    r"(\d+(?:[.,\s]\d{3})*(?:[.,]\d+)?)\s*(k|tis\.?|tisíc|mio\.?|millionen|million|millions|"
    r"milioni|millones|milionů|mil\.)?\s*(?:registrierte[n]?\s+|aktive[n]?\s+|monthly\s+|active\s+)?"
    r"(users|nutzer\w*|kunden|customers|subscribers|abonnent\w*|utilisateurs|clients|abonnés|"
    r"gebruikers|klanten|utenti|clienti|usuarios|clientes|uživatel\w*|zákazník\w*|downloads)",
    re.I)
REV_RE = re.compile(
    r"(?:€|eur|\$|usd|£)\s*(\d+(?:[.,]\d+)?)\s*(m|mn|million|millionen|mio\.?|millions|bn|billion)?\s*"
    r"(?:in\s+)?(?:arr|revenue|revenues|turnover|umsatz|sales|chiffre d'affaires|fatturato)"
    r"|(\d+(?:[.,]\d+)?)\s*(m|mn|million|millionen|mio\.?|millions)\s*(?:€|eur|euro|\$|usd|dollars|£)?\s*"
    r"(?:in\s+)?(?:arr|revenue|umsatz|turnover|chiffre d'affaires|fatturato)", re.I)
STAFF_RE = re.compile(
    r"(\d{1,4})\s*(mitarbeiter\w*|beschäftigte\w*|angestellte\w*|employees|staff|salariés|"
    r"collaborateurs|medewerkers|werknemers|dipendenti|empleados|trabajadores|zaměstnanc\w*)",
    re.I)

QUERIES = {
    "DE": ["Start-up Insolvenz App Nutzer", "Insolvenz Plattform Investor gesucht",
           "Insolvenzantrag Online-Plattform Mitarbeiter", "Software Start-up Insolvenz Kunden"],
    "AT": ["Start-up Insolvenz App Nutzer", "Sanierungsverfahren Plattform Software"],
    "FR": ["redressement judiciaire plateforme repreneur", "redressement judiciaire application utilisateurs",
           "liquidation judiciaire start-up application", "start-up cherche repreneur plateforme"],
    "NL": ["faillissement platform app gebruikers", "failliet startup app doorstart"],
    "IT": ["startup app concordato utenti", "piattaforma digitale fallimento acquirente"],
    "ES": ["startup app concurso de acreedores usuarios", "plataforma digital concurso comprador"],
    "CZ": ["startup aplikace insolvence uživatelé", "platforma insolvence kupec"],
    "EN": ["European startup insolvency app users", "European app startup administration buyer",
           "EU startup shuts down app users"],
}
COUNTRY_HINT = {"DE": "DE", "AT": "AT", "FR": "FR", "NL": "NL", "IT": "IT", "ES": "ES", "CZ": "CZ",
                "EN": "EU?"}
EXCLUDED_COUNTRY_WORDS = ["bulgaria", "bulgarien", "romania", "rumänien", "roumanie", "poland",
                          "polen", "pologne", "polsk", "polska", "bulharsk", "rumunsk",
                          "usa", "u.s.", "silicon valley", "san francisco", "new york", "india"]


def _num(s, unit):
    s = s.replace(" ", "")
    if re.match(r"^\d{1,3}([.,]\d{3})+$", s):
        val = float(re.sub(r"[.,]", "", s))
    else:
        val = float(s.replace(",", "."))
    u = (unit or "").lower()
    if u.startswith(("k", "tis")):
        val *= 1000
    elif u.startswith(("mio", "million", "milion", "millon", "mil")):
        val *= 1_000_000
    return int(val)


def extract_users(text):
    best = None
    for m in USERS_RE.finditer(text or ""):
        try:
            n = _num(m.group(1), m.group(2))
        except ValueError:
            continue
        best = max(best or 0, n)
    return best


def extract_revenue(text):
    """Tržby/ARR v EUR (přibližně, měna se nepřepočítává)."""
    m = REV_RE.search(text or "")
    if not m:
        return None
    num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    try:
        val = float(num.replace(",", "."))
    except (TypeError, ValueError):
        return None
    u = (unit or "").lower()
    val *= 1_000_000_000 if u.startswith(("bn", "billion")) else 1_000_000 if u else 1
    return int(val)


def extract_staff(text):
    m = STAFF_RE.search(text or "")
    return int(m.group(1)) if m else None


def grades(strong, digital, users, staff, revenue=None):
    g1 = "A" if strong else "B"
    g2 = "A" if digital else "C"
    size_ok = (users is not None and users >= config.DIGITAL_MIN_USERS) or \
              (staff is not None and config.EMPLOYEES_MIN <= staff <= config.DIGITAL_MAX_STAFF) or \
              (revenue is not None and config.DIGITAL_MIN_REVENUE <= revenue <= config.DIGITAL_MAX_REVENUE)
    too_big = (users or 0) > config.DIGITAL_MAX_USERS or (staff or 0) > config.DIGITAL_MAX_STAFF or \
              (revenue or 0) > config.DIGITAL_MAX_REVENUE
    g3 = "C" if too_big else "A" if size_ok else "C"
    return g1 + g2 + g3


# Tech weby: (RSS feed, locale pro záložní Google News, jen-EU web?)
TECH_SITES = {
    "techcrunch.com": ("https://techcrunch.com/feed/", "EN", False),
    "sifted.eu": ("https://sifted.eu/feed", "EN", True),
    "tech.eu": ("https://tech.eu/feed/", "EN", True),
    "eu-startups.com": ("https://www.eu-startups.com/feed/", "EN", True),
    "siliconcanals.com": ("https://siliconcanals.com/feed/", "EN", True),
    "trendingtopics.eu": ("https://www.trendingtopics.eu/feed/", "EN", True),
    "deutsche-startups.de": ("https://www.deutsche-startups.de/feed/", "DE", True),
    "t3n.de": ("https://t3n.de/rss.xml", "DE", True),
    "maddyness.com": ("https://www.maddyness.com/feed/", "FR", True),
    "startupitalia.eu": ("https://startupitalia.eu/feed", "IT", True),
    "czechcrunch.cz": ("https://czechcrunch.cz/feed/", "CZ", True),
}
EU_MARKERS = [
    "europe", "european", " eu ", "germany", "german", "berlin", "munich", "hamburg", "france",
    "french", "paris", "netherlands", "dutch", "amsterdam", "spain", "spanish", "madrid",
    "barcelona", "italy", "italian", "milan", "sweden", "swedish", "stockholm", "denmark",
    "danish", "copenhagen", "finland", "finnish", "helsinki", "austria", "vienna", "belgium",
    "brussels", "ireland", "irish", "dublin", "portugal", "lisbon", "czech", "prague",
    "estonia", "tallinn", "lithuania", "vilnius", "latvia", "riga", "greece", "athens",
    "hungary", "budapest", "slovakia", "bratislava", "slovenia", "croatia", "luxembourg",
]


def _strip(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s.replace("&nbsp;", " ")).strip()


def fetch_feed(url):
    """Obecné RSS/Atom; vrací položky s title, summary (vč. content:encoded), link, date."""
    import email.utils
    import xml.etree.ElementTree as ET
    from datetime import timedelta
    from common import now_utc
    try:
        r = http("GET", url, retries=2, timeout=40)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.content)
    except Exception:  # noqa: BLE001
        return None
    cutoff = now_utc() - timedelta(days=config.DIGITAL_NEWS_DAYS)
    items = []
    for it in list(root.iter("item")) + [e for e in root.iter() if e.tag.endswith("}entry")]:
        def txt(name):
            for e in it:
                if e.tag == name or e.tag.endswith("}" + name):
                    return e.text or e.get("href") or ""
            return ""
        pub = txt("pubDate") or txt("published") or txt("updated")
        try:
            dt = email.utils.parsedate_to_datetime(pub) if "," in pub else None
        except Exception:  # noqa: BLE001
            dt = None
        if dt and dt < cutoff:
            continue
        items.append({"title": _strip(txt("title")),
                      "summary": _strip(txt("encoded") or txt("description") or txt("summary") or txt("content"))[:6000],
                      "link": txt("link").strip(), "source": "", "date": dt.strftime("%Y-%m-%d") if dt else ""})
    return items


def tech_items():
    """Články z tech webů. Vrací list (item, locale, eu_native)."""
    out = []
    sig_q = ('layoffs OR struggling OR "shut down" OR "shutting down" OR sunset OR "for sale" '
             'OR "strategic review" OR insolvency OR "winds down" OR "cuts jobs"')
    for site, (feed, loc, eu_native) in TECH_SITES.items():
        items = fetch_feed(feed)
        how = "RSS"
        if not items:
            items = news.search(f"site:{site} ({sig_q})", "EN" if loc not in news.LOCALES else loc,
                                days=config.DIGITAL_NEWS_DAYS)
            how = "Google News"
        for it in items:
            it["source"] = it.get("source") or site
        log(f"[digital] {site}: {len(items)} článků ({how})")
        out += [(it, loc, eu_native) for it in items]
    return out


def signal_label(kw):
    if kw in MEDIUM:
        return f"propouštění / úspory („{kw}“)"
    if kw in STRUGGLE:
        return f"nedaří se („{kw}“)"
    return f"insolvence / prodej / ukončení („{kw}“)"


def run(seen, fps):
    out = []
    n_items = 0
    pool = [(it, loc, True) for loc, queries in QUERIES.items() for q in queries
            for it in news.search(q, loc, days=config.DIGITAL_NEWS_DAYS)]
    if config.DIGITAL_TECH_SITES:
        pool += tech_items()
    for it, loc, eu_native in pool:
                n_items += 1
                text = f"{it['title']} {it['summary']}"
                low = f" {text.lower()} "
                if any(k in low for k in EXCLUDED) or any(k in low for k in EXCLUDED_COUNTRY_WORDS):
                    continue
                if not eu_native and not any(m in low for m in EU_MARKERS):
                    continue  # globální web (TechCrunch) – jen evropské firmy
                strong = next((k for k in STRONG + STRUGGLE if k in low), None)
                medium = next((k for k in MEDIUM if k in low), None)
                if not (strong or medium):
                    continue
                if medium and not strong and config.DIGITAL_LAYOFFS_ARE_STRONG:
                    strong = medium
                digital = next((k for k in DIGITAL
                                if re.search(r"\b" + re.escape(k) + (r"s?\b" if len(k) <= 4 else ""), low)), None)
                users, staff, revenue = extract_users(text), extract_staff(text), extract_revenue(text)
                g = grades(strong, digital, users, staff, revenue)
                key = "DIGI:" + hashlib.sha1(it["title"].lower().encode()).hexdigest()[:16]
                if key in seen or news.is_duplicate(it["title"], fps):
                    continue
                fp = sorted(news.fingerprint(it["title"]))
                fps.append(fp)
                size = []
                if users:
                    size.append(f"{users:,} uživatelů/zákazníků".replace(",", " "))
                if staff:
                    size.append(f"{staff} zaměstnanců")
                if revenue:
                    size.append(f"tržby/ARR ≈ {revenue / 1e6:.1f} mil.".replace(".", ","))
                out.append({
                    "key": key, "fp": fp, "module": "DIGITAL", "source": f"zprávy {loc}",
                    "name": news.guess_company(it["title"]),
                    "country": COUNTRY_HINT.get(loc, "?") if eu_native or loc != "EN" else "EU?",
                    "procedure": signal_label(strong or medium),
                    "field": f"digitální produkt ({digital})" if digital else "?",
                    "size": ", ".join(size) or "?",
                    "contact": news.extract_admin(text) or
                               "? – správce/vlastník je ve zprávě; u FR „administrateur judiciaire“",
                    "link": it["link"], "links": [],
                    "notes": [f"Titulek: {it['title']}", f"Zdroj: {it['source'] or '?'} ({it['date'] or '?'})",
                              "Údaje ze zprávy – ověř u správce / v rejstříku."],
                    "points": 0, "rating": "A" if g == "AAA" else "B",
                    "grades": g,
                })
    log(f"[digital] zpráv {n_items}, kandidátů {len(out)}, AAA {sum(c['grades'] == 'AAA' for c in out)}")
    return out
