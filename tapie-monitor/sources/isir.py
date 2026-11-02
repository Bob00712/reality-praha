# -*- coding: utf-8 -*-
"""ČR – insolvenční rejstřík ISIR, veřejná webová služba Ministerstva
spravedlnosti (IsirWsPublicService). Zdarma, bez registrace, určená
právě pro automatické stahování událostí.
Popis: https://isir.justice.cz/isir/help/Popis_WS.pdf
"""
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import config
from common import (http, log, norm, now_utc, rate, size_points, liab_points, grades_firma,
                    fmt_employees)
from sources import ares
from sources.firma_rules import classify_nace, CAT_LABEL

WS_URL = "https://isir.justice.cz:8443/isir_public_ws/IsirWsPublicService"
SOAP = ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:typ="http://isirpublicws.cca.cz/types/"><soapenv:Header/><soapenv:Body>'
        '<typ:getIsirWsPublicIdDataRequest><idPodnetu>{id}</idPodnetu>'
        '</typ:getIsirWsPublicIdDataRequest></soapenv:Body></soapenv:Envelope>')

DEBTOR_ROLES = ("DLUZNIK",)
ADMIN_ROLES = ("SPRAVCE",)


# ------------------------------------------------------------ XML pomůcky
def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _find_all(el, name):
    return [e for e in el.iter() if _local(e.tag) == name]


def _text(el, name):
    if el is None:
        return ""
    for e in el.iter():
        if _local(e.tag) == name:
            return (e.text or "").strip()
    return ""


def parse_response(xml_bytes):
    root = ET.fromstring(xml_bytes)
    status = _text(root, "stav")
    if status and status != "OK":
        raise RuntimeError(f"ISIR chyba {_text(root, 'kodChyby')}: {_text(root, 'popisChyby')}")
    events = []
    for d in _find_all(root, "data"):
        try:
            events.append({
                "id": int(_text(d, "id")),
                "date": _text(d, "datumZalozeniUdalosti"),
                "sz": _text(d, "spisovaZnacka"),
                "type": _text(d, "typUdalosti"),
                "desc": _text(d, "popisUdalosti"),
                "doc": _text(d, "dokumentUrl"),
                "note": _text(d, "poznamka"),
            })
        except ValueError:
            continue
    return events


def fetch(after_id):
    r = http("POST", WS_URL, data=SOAP.format(id=int(after_id)).encode(),
             headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
             timeout=120)
    r.raise_for_status()
    return parse_response(r.content)


def parse_note(note):
    """Z XML v poli 'poznamka' vytáhne osoby a stav řízení."""
    out = {"persons": [], "state": ""}
    if not note or "<" not in note:
        return out
    try:
        root = ET.fromstring(note.encode("utf-8") if isinstance(note, str) else note)
    except ET.ParseError:
        return out
    out["state"] = _text(root, "druhStavRizeni")
    for o in _find_all(root, "osoba"):
        name = " ".join(x for x in (_text(o, "jmeno"), _text(o, "nazevOsoby")) if x)
        out["persons"].append({
            "role": norm(_text(o, "druhRoleVRizeni")).replace(" ", ""),
            "kind": norm(_text(o, "druhOsoby")),
            "ico": re.sub(r"\D", "", _text(o, "ic")),
            "name": name,
            "city": _text(o, "mesto"),
        })
    return out


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")[:25])
    except Exception:  # noqa: BLE001
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            return None


def _first_date(after_id):
    ev = fetch(after_id)
    if not ev:
        return None
    d = _parse_dt(ev[0]["date"])
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def find_start_id(days_back):
    """Binárním hledáním najde ID události zhruba před `days_back` dny."""
    target = now_utc() - timedelta(days=days_back)
    hi = 1_000_000
    while fetch(hi):
        hi *= 2
        if hi > 2**40:
            break
    lo = 0
    while hi - lo > 1000:
        mid = (lo + hi) // 2
        d = _first_date(mid)
        if d is None or d >= target:
            hi = mid
        else:
            lo = mid
        time.sleep(0.3)
    log(f"[isir] start od ID {lo} (≈ {days_back} dní zpět)")
    return lo


def wanted_stage(state, desc):
    s = norm(state) + " " + norm(desc)
    for key, label in config.CZ_WANTED_STATES.items():
        if key in norm(state):
            return label
    # záložně podle popisu události
    if "PROHLASENI KONKURSU" in s or "PROHLASUJE KONKURS" in s:
        return config.CZ_WANTED_STATES["KONKURS"]
    if "POVOLENI REORGANIZACE" in s or "POVOLUJE REORGANIZACI" in s:
        return config.CZ_WANTED_STATES["REORGAN"]
    if "ROZHODNUTI O UPADKU" in s:
        return config.CZ_WANTED_STATES["UPADEK"]
    return None


def is_sale(desc):
    d = (desc or "").lower()
    return any(k in d for k in config.CZ_SALE_KEYWORDS)


def isir_link(ico=None, sz=None):
    if ico:
        return ("https://isir.justice.cz/isir/ueu/vysledek_lustrace.do?"
                f"ic={ico}&aktualnost=AKTUALNI_I_UKONCENA")
    m = re.search(r"(\d+)\s*/\s*(\d{4})", sz or "")
    if m:
        return ("https://isir.justice.cz/isir/ueu/vysledek_lustrace.do?"
                f"bc_vec={m.group(1)}&rocnik={m.group(2)}&druh_vec=INS"
                "&aktualnost=AKTUALNI_I_UKONCENA")
    return "https://isir.justice.cz/isir/common/index.do"


# ---------------------------------------------------------------- běh
def run(state, seen):
    """Projde nové události ISIR. Vrací seznam případů (dict)."""
    st = state.setdefault("isir", {})
    cases_cache = st.setdefault("cases", {})   # sz -> dlužník/správce
    started = time.time()
    first_run = "last_id" not in st
    if first_run:
        st["last_id"] = find_start_id(config.CZ_CACHE_BACKFILL_DAYS)
    report_from = now_utc() - timedelta(days=config.CZ_BACKFILL_DAYS)

    hits = {}      # sz -> (stage, event)
    sales = {}     # sz -> event
    n_events = 0
    last_id = st["last_id"]
    while True:
        if time.time() - started > config.CZ_MAX_RUNTIME_MIN * 60:
            log("[isir] časový limit – pokračuji příště")
            break
        try:
            events = fetch(last_id)
        except Exception as e:  # noqa: BLE001
            log(f"[isir] CHYBA stahování: {e}")
            break
        events = [e for e in events if e["id"] > last_id]
        if not events:
            break
        for ev in events:
            n_events += 1
            last_id = ev["id"]
            sz = ev["sz"]
            info = parse_note(ev["note"])
            c = cases_cache.get(sz)
            for p in info["persons"]:
                if p["role"].startswith(DEBTOR_ROLES) and p["ico"] and p["kind"] != "F":
                    c = cases_cache.setdefault(sz, {})
                    c.update({"ico": p["ico"], "name": p["name"], "kind": p["kind"],
                              "seen": ev["date"][:10]})
                elif p["role"].startswith(ADMIN_ROLES) and c is not None:
                    c["admin"] = (p["name"] + (f", {p['city']}" if p["city"] else "")).strip()
            if c is None:
                continue
            evd = _parse_dt(ev["date"])
            if evd and evd.tzinfo is None:
                evd = evd.replace(tzinfo=timezone.utc)
            recent = evd is None or evd >= report_from
            stage = wanted_stage(info["state"], ev["desc"])
            if stage:
                c["stage"] = stage
                if recent:
                    hits[sz] = (stage, ev)
            if recent and is_sale(ev["desc"]):
                sales[sz] = ev
        time.sleep(0.2)
    st["last_id"] = last_id
    log(f"[isir] zpracováno {n_events} událostí, poslední ID {last_id}, "
        f"kandidátů {len(hits)}, prodejů {len(sales)}")

    # úklid: zapomeň dlužníky starší než ~2 roky
    cutoff = (now_utc() - timedelta(days=730)).strftime("%Y-%m-%d")
    for sz in [k for k, v in cases_cache.items() if v.get("seen", "9") < cutoff]:
        del cases_cache[sz]

    out = []
    reported_icos = set()
    for sz, (stage, ev) in hits.items():
        c = cases_cache[sz]
        key = f"CZ:{sz}"
        prev = seen.get(key) or seen.get(f"CZICO:{c.get('ico')}")
        if not prev and c.get("ico") in reported_icos:
            continue
        if prev:
            # už posláno – pošli jen změnu z úpadku/moratoria na konkurs/reorganizaci
            if prev.get("stage") == stage or stage not in ("konkurs", "reorganizace"):
                continue
            case = build_case(sz, c, stage, ev)
            if case:
                case["update"] = f"ZMĚNA: {prev.get('stage')} → {stage}"
                case["key"] = key
                out.append(case)
            continue
        case = build_case(sz, c, stage, ev)
        if case:
            reported_icos.add(c.get("ico"))
            out.append(case)

    for sz, ev in sales.items():
        key = f"CZ:{sz}:sale:{ev['date'][:7]}"
        if key in seen or f"CZ:{sz}" not in seen and not any(o["key"] == f"CZ:{sz}" for o in out):
            continue
        case = build_case(sz, cases_cache[sz], cases_cache[sz].get("stage") or "?", ev)
        if case:
            case["key"] = key
            case["update"] = "PRODEJ Z MAJETKOVÉ PODSTATY"
            case["notes"].insert(0, f"Událost: {ev['desc']}")
            if ev.get("doc"):
                case["links"].append(("dokument k prodeji", ev["doc"]))
            out.append(case)
    s = ares.STATS
    log(f"[ares] dotazů {s['lookups']}, hlavní obor znám u {s['main_known']}, "
        f"zaměstnanci znám u {s['emp_known']}")
    return out


def build_case(sz, c, stage, ev):
    a = ares.lookup(c.get("ico")) or {}
    if not a:
        return None  # bez záznamu v ARES (typicky fyzická osoba) – nechceme
    if ares.is_natural_person(a.get("legal_form")):
        return None  # fyzická osoba (podnikatel) – nechceme
    name = a.get("name") or c.get("name") or "?"
    cat, excluded = classify_nace(a.get("nace"), name, a.get("nace_main_known", False))
    if excluded:
        log(f"[isir] vyřazeno {name}: {excluded}")
        return None
    emp = a.get("employees")
    sp, out_of_range = size_points(emp)
    if out_of_range and config.DROP_IF_SIZE_KNOWN_OUT_OF_RANGE:
        log(f"[isir] vyřazeno {name}: zaměstnanci {fmt_employees(emp)}")
        return None
    points = (config.CZ_STATE_POINTS.get(stage, 1) + config.CATEGORY_POINTS.get(cat, 0)
              + sp + liab_points(None))
    if cat == "E-SHOP":
        points = min(points, config.RATING_A_MIN - 1)  # e-shop max B
    nace_txt = ", ".join(a.get("nace", [])[:3]) or "?"
    notes = [f"Sp. zn.: {sz}", f"IČO: {c.get('ico') or '?'}"]
    if a.get("address"):
        notes.append(f"Sídlo: {a['address']}")
    notes.append(f"Poslední událost: {ev.get('desc')} ({ev.get('date', '')[:10]})")
    links = [("ARES", f"https://ares.gov.cz/ekonomicke-subjekty?ico={c.get('ico')}")]
    if ev.get("doc"):
        links.append(("dokument z ISIR", ev["doc"]))
    return {
        "key": f"CZ:{sz}",
        "module": "FIRMA",
        "source": "ISIR",
        "name": name,
        "country": "CZ",
        "procedure": stage,
        "stage": stage,
        "field": f"{CAT_LABEL.get(cat, cat)} (NACE {nace_txt})",
        "size": f"{fmt_employees(emp)} zaměstnanců",
        "liabilities": "? (ISIR je neuvádí – viz přihlášky pohledávek)",
        "contact": (c.get("admin") or "?") + " – insolvenční správce (kontakt v ISIR u spisu)",
        "link": isir_link(c.get("ico"), sz),
        "alias": f"CZICO:{c.get('ico')}" if c.get("ico") else None,
        "links": links,
        "notes": notes,
        "points": points,
        "rating": rate(points),
        "grades": grades_firma(config.CZ_STATE_POINTS.get(stage, 1), cat, sp),
        "cat": cat,
        "employees": emp,
    }
