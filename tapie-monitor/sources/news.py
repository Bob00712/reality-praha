# -*- coding: utf-8 -*-
"""Google News RSS – veřejné RSS výsledků vyhledávání zpráv (zdarma,
bez klíče). Používá se pro AT/DE insolvence (náhrada za úřední portály,
které nejdou legálně automatizovat) a pro signály upadajících aplikací.
"""
import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timedelta

import config
from common import http, log, now_utc, strip_accents

LOCALES = {
    "AT": dict(hl="de", gl="AT", ceid="AT:de"),
    "DE": dict(hl="de", gl="DE", ceid="DE:de"),
    "EN": dict(hl="en-US", gl="US", ceid="US:en"),
    "FR": dict(hl="fr", gl="FR", ceid="FR:fr"),
    "NL": dict(hl="nl", gl="NL", ceid="NL:nl"),
    "IT": dict(hl="it", gl="IT", ceid="IT:it"),
    "ES": dict(hl="es", gl="ES", ceid="ES:es"),
    "CZ": dict(hl="cs", gl="CZ", ceid="CZ:cs"),
}


def search(query, locale="EN", days=None):
    days = days or config.NEWS_MAX_AGE_DAYS
    loc = LOCALES[locale]
    q = f"{query} when:{days}d"
    url = ("https://news.google.com/rss/search?" +
           urllib.parse.urlencode({"q": q, **loc}))
    try:
        r = http("GET", url)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"[news] CHYBA {query!r}: {e}")
        return []
    return parse_rss(r.content, days)


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_rss(content, days=3):
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    cutoff = now_utc() - timedelta(days=days)
    out = []
    for it in root.iter("item"):
        title = _clean(it.findtext("title"))
        src = _clean(it.findtext("source"))
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        pub = it.findtext("pubDate")
        try:
            dt = email.utils.parsedate_to_datetime(pub) if pub else None
        except Exception:  # noqa: BLE001
            dt = None
        if dt and dt < cutoff:
            continue
        out.append({
            "title": title,
            "summary": _clean(it.findtext("description")),
            "link": (it.findtext("link") or "").strip(),
            "source": src,
            "date": dt.strftime("%Y-%m-%d") if dt else "",
        })
    return out


STOP = set("der die das und mit von für fur ein eine im in zu den des auf ist the a an of "
           "to for and on at is as by with".split())


def fingerprint(title):
    words = re.findall(r"\w+", strip_accents(title.lower()))
    return {w for w in words if len(w) > 2 and w not in STOP}


def is_duplicate(title, fingerprints, threshold=0.55):
    fp = fingerprint(title)
    if not fp:
        return False
    for other in fingerprints:
        o = set(other)
        if o and len(fp & o) / len(fp | o) >= threshold:
            return True
    return False


def guess_company(title):
    """Hrubý odhad názvu firmy z titulku (text před ':' nebo s právní formou)."""
    m = re.search(r"([A-ZÄÖÜ][\w&.\-ÄÖÜäöüß]+(?:\s+[A-ZÄÖÜ&][\w&.\-ÄÖÜäöüß]+){0,4}\s+"
                  r"(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|AG|KG|OG|SE|e\.U\.|Inc\.?|Ltd\.?|LLC))", title)
    if m:
        return m.group(1).strip()
    if ":" in title:
        head = title.split(":", 1)[0].strip()
        if 2 <= len(head) <= 60:
            return head
    return title[:80]


ADMIN_RE = re.compile(
    r"(?:Masseverwalter(?:in)?|Insolvenzverwalter(?:in)?|Sanierungsverwalter(?:in)?|"
    r"Sachwalter(?:in)?)\s*(?:ist|wurde|:)?\s*(?:der|die)?\s*(?:Rechtsanwalt|Rechtsanwältin|"
    r"RA|Dr\.|Mag\.)?\s*([A-ZÄÖÜ][\w.\-]+(?:\s+[A-ZÄÖÜ][\w.\-]+){0,3})")


def extract_admin(text):
    m = ADMIN_RE.search(text or "")
    return m.group(1).strip().rstrip(".,;") if m else None
