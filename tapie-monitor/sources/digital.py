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
from common import log
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
MEDIUM = ["layoff", "lays off", "entlass", "stellenabbau", "licenciement", "ontslag",
          "licenziament", "despido", "propouštění", "restructur", "restrukturier"]
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


def extract_staff(text):
    m = STAFF_RE.search(text or "")
    return int(m.group(1)) if m else None


def grades(strong, digital, users, staff):
    g1 = "A" if strong else "B"
    g2 = "A" if digital else "C"
    size_ok = (users is not None and users >= config.DIGITAL_MIN_USERS) or \
              (staff is not None and config.EMPLOYEES_MIN <= staff <= config.DIGITAL_MAX_STAFF)
    too_big = (users or 0) > config.DIGITAL_MAX_USERS or (staff or 0) > config.DIGITAL_MAX_STAFF
    g3 = "C" if too_big else "A" if size_ok else "C"
    return g1 + g2 + g3


def run(seen, fps):
    out = []
    n_items = 0
    for loc, queries in QUERIES.items():
        for q in queries:
            for it in news.search(q, loc, days=config.DIGITAL_NEWS_DAYS):
                n_items += 1
                text = f"{it['title']} {it['summary']}"
                low = text.lower()
                if any(k in low for k in EXCLUDED) or any(k in low for k in EXCLUDED_COUNTRY_WORDS):
                    continue
                strong = next((k for k in STRONG if k in low), None)
                medium = next((k for k in MEDIUM if k in low), None)
                if not (strong or medium):
                    continue
                digital = next((k for k in DIGITAL
                                if re.search(r"\b" + re.escape(k) + (r"s?\b" if len(k) <= 4 else ""), low)), None)
                users, staff = extract_users(text), extract_staff(text)
                g = grades(strong, digital, users, staff)
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
                out.append({
                    "key": key, "fp": fp, "module": "DIGITAL", "source": f"zprávy {loc}",
                    "name": news.guess_company(it["title"]),
                    "country": COUNTRY_HINT.get(loc, "?"),
                    "procedure": strong or medium,
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
