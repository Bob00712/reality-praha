# -*- coding: utf-8 -*-
"""Rakousko a Bavorsko – insolvence firem ze zpráv (Google News RSS).

Proč ne přímo úřední portály:
* AT Ediktsdatei: automatické (strojové) převzetí dat je povoleno jen
  s licencí podle IWG od Ministerstva spravedlnosti (žádost na
  IWG-Antrag@bmj.gv.at, poplatek) – web nelze legálně "scrapovat".
* DE insolvenzbekanntmachungen.de: podle InsBekV §2 je portál chráněn
  proti hromadnému kopírování, nemá API a vyhledávání je omezené.
Zprávy KSV1870 / AKV / Creditreform a regionálních médií jsou proto
nejlepší legální náhrada zdarma.
"""
import hashlib

import config
from common import (log, rate, size_points, liab_points, fmt_employees, fmt_eur,
                    extract_employees, extract_liabilities)
from sources import news
from sources.firma_rules import classify_text, CAT_LABEL


def _procedure(text, table):
    t = text.lower()
    for kw, (label, pts) in table.items():
        if kw in t:
            return label, pts
    return None, 0


def _process(items, country, table, seen, fps, require_places=None):
    out = []
    for it in items:
        text = f"{it['title']} {it['summary']}"
        low = text.lower()
        if require_places and not any(p in low for p in require_places):
            continue
        proc, ppts = _procedure(text, table)
        if not proc:
            continue
        cat, excluded = classify_text(text)
        if excluded:
            continue
        key = f"{country}:news:" + hashlib.sha1(it["title"].lower().encode()).hexdigest()[:16]
        if key in seen or news.is_duplicate(it["title"], fps):
            continue
        emp = extract_employees(text)
        sp, out_of_range = size_points(emp)
        if out_of_range and config.DROP_IF_SIZE_KNOWN_OUT_OF_RANGE:
            continue
        liab = extract_liabilities(text)
        if liab is not None and liab > config.LIABILITIES_MAX_EUR * 3:
            continue  # výrazně větší než chceme
        points = ppts + config.CATEGORY_POINTS.get(cat, 0) + sp + liab_points(liab)
        if cat == "E-SHOP":
            points = min(points, config.RATING_A_MIN - 1)
        admin = news.extract_admin(text)
        fps.append(sorted(news.fingerprint(it["title"])))
        out.append({
            "key": key,
            "fp": sorted(news.fingerprint(it["title"])),
            "module": "FIRMA",
            "source": f"zprávy {country}",
            "name": news.guess_company(it["title"]),
            "country": country,
            "procedure": proc,
            "field": CAT_LABEL.get(cat, cat),
            "size": f"{fmt_employees(emp)} zaměstnanců",
            "liabilities": fmt_eur(liab),
            "contact": (admin + " (správce dle zprávy)") if admin else
                       "? – jméno správce najdeš v článku / v Ediktsdatei" if country == "AT"
                       else "? – jméno správce najdeš v článku / insolvenzbekanntmachungen.de",
            "link": it["link"],
            "links": [],
            "notes": [f"Titulek: {it['title']}", f"Zdroj: {it['source'] or '?'} ({it['date'] or '?'})",
                      "Údaje ze zprávy – ověř v úředním rejstříku."],
            "points": points,
            "rating": rate(points),
        })
    return out


def run(seen, fps):
    out = []
    if config.AT_ENABLED:
        items = []
        for q in config.AT_NEWS_QUERIES:
            items += news.search(q, "AT")
        found = _process(items, "AT", config.AT_PROCEDURES, seen, fps,
                         require_places=config.AT_MARKERS)
        log(f"[AT] zpráv {len(items)}, případů {len(found)}")
        out += found
    if config.BAVARIA_ENABLED:
        items = []
        for q in config.BAVARIA_NEWS_QUERIES:
            items += news.search(q, "DE")
        found = _process(items, "DE", config.DE_PROCEDURES, seen, fps,
                         require_places=config.BAVARIA_PLACES)
        log(f"[DE-Bayern] zpráv {len(items)}, případů {len(found)}")
        out += found
    return out
