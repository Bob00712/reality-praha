# -*- coding: utf-8 -*-
"""ARES – oficiální bezplatné REST API Ministerstva financí.
Dokumentace: https://ares.gov.cz/stranky/vyvojar-info
Doplňuje k IČO: název, sídlo, právní formu, CZ-NACE, počet zaměstnanců.
"""
import re

from common import http, log

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"

# Číselník ČSÚ "Kategorie počtu zaměstnanců" (CZ_579)
EMP_CATEGORIES = {
    "110": (0, 0), "120": (1, 5), "130": (6, 9), "210": (10, 19),
    "220": (20, 24), "230": (25, 49), "240": (50, 99), "310": (100, 199),
    "320": (200, 249), "330": (250, 499), "340": (500, 999),
    "410": (1000, 1499), "420": (1500, 1999), "430": (2000, 2499),
    "440": (2500, 2999), "450": (3000, 3999), "460": (4000, 4999),
    "470": (5000, 9999), "480": (10000, 10**6),
}

_cache = {}


def _walk(obj, keyfn):
    """Najde všechny hodnoty, jejichž klíč odpovídá keyfn (rekurzivně)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if keyfn(k.lower()):
                out.append(v)
            out.extend(_walk(v, keyfn))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk(v, keyfn))
    return out


def _get(path):
    try:
        r = http("GET", f"{BASE}/{path}", headers={"Accept": "application/json"})
        if r.status_code == 200:
            return r.json()
        if r.status_code != 404:
            log(f"[ares] {path}: HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        log(f"[ares] {path}: {e}")
    return None


def parse_employees(val):
    if val is None:
        return None
    s = str(val).strip()
    if s in EMP_CATEGORIES:
        return EMP_CATEGORIES[s]
    nums = [int(n) for n in re.findall(r"\d+", s)]
    if len(nums) >= 2 and nums[0] <= nums[1]:
        return (nums[0], nums[1])
    return None


def lookup(ico):
    """Vrací dict: name, address, legal_form, nace(list), employees((lo,hi)|None)."""
    ico = re.sub(r"\D", "", str(ico or "")).zfill(8)
    if not ico.strip("0"):
        return None
    if ico in _cache:
        return _cache[ico]
    basic = _get(f"ekonomicke-subjekty/{ico}") or {}
    res = _get(f"ekonomicke-subjekty-res/{ico}") or {}
    if not basic and not res:
        _cache[ico] = None
        return None

    nace = []
    for v in _walk(basic, lambda k: k == "cznace") + _walk(res, lambda k: k == "cznace"):
        for code in (v if isinstance(v, list) else [v]):
            code = re.sub(r"\D", "", str(code if not isinstance(code, dict) else
                                         code.get("kod", "")))
            if code and code not in nace:
                nace.append(code)

    emp = None
    for v in _walk(res, lambda k: ("poct" in k or "pocet" in k) and ("pracovn" in k or "zamest" in k)):
        emp = parse_employees(v.get("kod") if isinstance(v, dict) else v)
        if emp:
            break

    legal = basic.get("pravniForma") or next(iter(_walk(res, lambda k: k == "pravniforma")), None)
    addr = (basic.get("sidlo") or {}).get("textovaAdresa")
    out = {
        "ico": ico,
        "name": basic.get("obchodniJmeno") or next(iter(_walk(res, lambda k: k == "obchodnijmeno")), None),
        "address": addr,
        "legal_form": str(legal) if legal else None,
        "nace": nace,
        "employees": emp,
    }
    _cache[ico] = out
    return out


def is_natural_person(legal_form):
    """Právní formy 101–108 = fyzické osoby (podnikatelé); 111+ = firmy."""
    return bool(legal_form) and str(legal_form).strip().startswith("10")
