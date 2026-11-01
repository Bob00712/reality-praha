# -*- coding: utf-8 -*-
"""Zařazení firmy do kategorií A/B/C podle CZ-NACE nebo klíčových slov."""
import config
from common import keyword_category, has_excluded_keyword

CAT_LABEL = {
    "A": "A – výrobce s vlastním produktem",
    "B": "B – strojírenství / kovovýroba / tepelná technika",
    "C": "C – software / aplikace",
    "E-SHOP": "e-shop / značka (výjimečně)",
    "?": "?",
    "jiný obor": "jiný obor",
}


def _match(code, prefixes):
    return any(code.startswith(p) for p in prefixes)


def classify_nace(nace_codes, name="", main_known=True):
    """Vrací (kategorie, vyloučeno_důvod|None). Hlavní obor = první kód."""
    codes = [c for c in (nace_codes or []) if c]
    low = (name or "").lower()
    bad = next((w for w in config.NAME_EXCLUDED_WORDS if w in low), None) or has_excluded_keyword(name)
    if bad:
        return "jiný obor", f"vyloučeno slovem „{bad.strip()}“ v názvu"
    if not main_known:
        # bez převažující činnosti nevíme hlavní obor – seznam živností nic neříká
        return keyword_category(name) or "?", None
    main = codes[0] if codes else None
    if main and _match(main, config.NACE_EXCLUDED):
        return "jiný obor", f"vyloučený obor NACE {main}"
    for cat, lst in (("B", config.NACE_CATEGORY_B), ("C", config.NACE_CATEGORY_C),
                     ("A", config.NACE_CATEGORY_A), ("E-SHOP", config.NACE_ESHOP)):
        if main and _match(main, lst):
            return cat, None
    kw = keyword_category(name)
    if kw:
        return kw, None
    if main and main_known:
        if config.DROP_OTHER_FIELDS:
            return "jiný obor", f"hlavní obor NACE {main} není v kategoriích A/B/C"
        return "jiný obor", None
    return "?", None  # hlavní obor neznámý (vedlejší obory firmy v ČR nic neznamenají)


def classify_text(text):
    """Pro zprávy (AT/DE): kategorie z klíčových slov, vyloučení."""
    bad = has_excluded_keyword(text)
    if bad:
        return "jiný obor", f"vyloučeno slovem „{bad.strip()}“"
    return keyword_category(text) or "?", None
