# -*- coding: utf-8 -*-
"""Modul APP – upadající aplikace.

Zdroje (vše zdarma, oficiální/veřejné, bez obcházení ochran):
* Apple App Store – veřejné RSS žebříčky (top free + top grossing podle
  kategorií) a iTunes Search/Lookup API (vlastník, web vývojáře, počet
  hodnocení, datum poslední aktualizace).
* Google News RSS – zprávy o propouštění, ukončení produktu, prodeji.
Nepoužíváme: Google Play (nemá veřejné API, scraping porušuje podmínky),
Acquire.com / Flippa / layoffs.fyi (zákaz automatického stahování nebo
nutné přihlášení) – viz README, jak na ně nastavit e-mailová upozornění.
"""
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone

import config
from common import grades_app, http, log, now_utc, rate, today
from sources import news

CHARTS = ("topfreeapplications", "topgrossingapplications")
CHART_PAUSE = 0.2    # s mezi žebříčky (šetrnost k Apple)
LOOKUP_PAUSE = 3.0   # s mezi dávkami Lookup API (limit ~20/min)


def _pause(sec):
    import time
    if sec:
        time.sleep(sec)


def _get_json(url):
    try:
        r = http("GET", url)
        if r.status_code == 200:
            return r.json()
        log(f"[app] HTTP {r.status_code} {url}")
    except Exception as e:  # noqa: BLE001
        log(f"[app] CHYBA {url}: {e}")
    return None


def fetch_chart(cc, genre, chart):
    """Vrací list (app_id, název, vývojář, kategorie) v pořadí žebříčku."""
    url = f"https://itunes.apple.com/{cc}/rss/{chart}/limit={config.APP_CHART_LIMIT}/genre={genre}/json"
    data = _get_json(url)
    entries = ((data or {}).get("feed") or {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        try:
            out.append((e["id"]["attributes"]["im:id"], e["im:name"]["label"],
                        e.get("im:artist", {}).get("label", "?"),
                        e.get("category", {}).get("attributes", {}).get("label", "")))
        except (KeyError, TypeError):
            continue
    return out


def fetch_chart_fallback(cc):
    """Novější Apple RSS (bez kategorií) – záloha, když staré RSS nefunguje."""
    data = _get_json(f"https://rss.applemarketingtools.com/api/v2/{cc}/apps/top-free/100/apps.json")
    res = ((data or {}).get("feed") or {}).get("results") or []
    return [(r.get("id"), r.get("name"), r.get("artistName", "?"),
             ", ".join(g.get("name", "") for g in r.get("genres", []) if isinstance(g, dict)))
            for r in res if r.get("id")]


def lookup(ids, cc="de"):
    """iTunes Lookup (limit Apple ~20 dotazů/min → pauza mezi dávkami)."""
    out = {}
    ids = list(dict.fromkeys(str(i) for i in ids))
    for i in range(0, len(ids), 150):
        chunk = ids[i:i + 150]
        if i:
            _pause(LOOKUP_PAUSE)
        data = _get_json(f"https://itunes.apple.com/lookup?id={','.join(chunk)}&country={cc}")
        for r in (data or {}).get("results", []):
            if r.get("trackId"):
                out[str(r["trackId"])] = r
    return out


STOPWORDS = {"The", "A", "An", "App", "Apps", "How", "Why", "What", "After", "Its", "Inc",
             "New", "CEO", "Report", "Exclusive", "Update", "This", "Startup", "Company"}


def find_app_for_news(title):
    """Zkusí ke zprávě najít aplikaci v App Store (kvůli velikosti a vlastníkovi)."""
    import re as _re
    cands = _re.findall(r"\b([A-Z][\w'&.-]+(?:\s+[A-Z][\w'&.-]+){0,2})", title)
    seen_c = []
    for c in cands:
        c = " ".join(w for w in c.split() if w not in STOPWORDS).strip(" .'")
        if len(c) >= 3 and c not in seen_c:
            seen_c.append(c)
    for term in seen_c[:3]:
        q = urllib.parse.urlencode({"term": term, "entity": "software", "limit": 3, "country": "us"})
        data = _get_json(f"https://itunes.apple.com/search?{q}")
        for r in (data or {}).get("results") or []:
            names = f"{r.get('trackName', '')} {r.get('sellerName', '')} {r.get('artistName', '')}".lower()
            if term.lower().split()[0] in names:
                return r
    return None


def big_owner(app):
    import re as _re
    owner = f"{app.get('sellerName', '')} {app.get('artistName', '')}".lower()
    return any(_re.search(r"\b" + _re.escape(b) + r"\b", owner) for b in config.APP_OWNER_BLACKLIST)


def corroborate(case, app):
    """K aplikaci, která padá v žebříčku, dohledá zprávy (přesný název v uvozovkách)."""
    name = (app.get("trackName") or "").split(":")[0].split(" - ")[0].strip()
    if len(name) < 4:
        return
    items = news.search(f'"{name}" app', "EN", days=30)
    hits = []
    for it in items:
        t = f"{it['title']} {it['summary']}".lower()
        if name.lower() not in t:
            continue
        sig = next((lab for kw, (lab, _) in config.APP_NEWS_SIGNALS.items() if kw in t), None)
        if sig:
            hits.append((sig, it))
    for sig, it in hits[:2]:
        case["notes"].insert(0, f"Zpráva ({sig}): {it['title']}")
        case["links"].append((f"zpráva: {it['source'] or 'článek'}", it["link"]))


def search_app(term):
    q = urllib.parse.urlencode({"term": term, "entity": "software", "limit": 1, "country": "us"})
    data = _get_json(f"https://itunes.apple.com/search?{q}")
    res = (data or {}).get("results") or []
    return str(res[0]["trackId"]) if res else None


def platform_dependent(app):
    """Aplikace stojí na API cizí platformy (Reddit, X, Instagram…) – vlastník
    platformy jí může kdykoli vypnout přístup, takže ji nemá smysl kupovat."""
    import re as _re
    name = (app.get("trackName") or "").lower()
    if any(_re.search(r"\b" + _re.escape(w) + r"\b", name) for w in config.APP_PLATFORM_NAME_WORDS):
        return True
    desc = (app.get("description") or "").lower()
    return any(p in desc for p in config.APP_PLATFORM_DESC_PHRASES)


def dead_product(app):
    """Bez aktualizace déle než APP_MAX_MONTHS_SINCE_UPDATE = mrtvý produkt."""
    upd = (app.get("currentVersionReleaseDate") or "")[:10]
    cut = (now_utc() - timedelta(days=30 * config.APP_MAX_MONTHS_SINCE_UPDATE)).strftime("%Y-%m-%d")
    return bool(upd) and upd < cut


def _excluded(text, genre):
    t = (text or "").lower()
    if genre in config.APP_EXCLUDED_GENRES:
        return True
    return any(k in t for k in config.APP_EXCLUDED_KEYWORDS)


def _days_ago(n):
    return (now_utc() - timedelta(days=n)).strftime("%Y-%m-%d")


def detect_drop(hist, today_s):
    """hist = {datum: pořadí}. Vrací popis signálu nebo None."""
    window = [d for d in hist if _days_ago(30) <= d < today_s]
    in_top = [d for d in window if hist[d] <= config.APP_TOP_RANK]
    if len(in_top) < config.APP_MIN_DAYS_IN_TOP:
        return None
    best = min(hist[d] for d in in_top)
    cur = hist.get(today_s)
    if cur is None:
        last_seen = max(hist)
        absent = (datetime.strptime(today_s, "%Y-%m-%d") - datetime.strptime(last_seen, "%Y-%m-%d")).days
        if absent >= config.APP_ABSENT_DAYS:
            return f"vypadla ze žebříčku (dříve až #{best}, nevidět {absent} dní)"
        return None
    if cur - best >= config.APP_DROP_POSITIONS:
        return f"pokles v žebříčku z #{best} na #{cur}"
    return None


def _app_case(app, signal, sig_pts, chart_label=""):
    ratings = int(app.get("userRatingCount") or 0)
    genre = app.get("primaryGenreName", "?")
    text = f"{app.get('trackName', '')} {genre} {app.get('description', '')[:400]}"
    size_pts = 3 if ratings >= config.APP_AAA_MIN_RATINGS else 2 if ratings >= config.APP_MIN_RATINGS else 1
    focus = 2 if genre == "Education" or any(k in text.lower() for k in ("language", "learn")) else 1
    points = sig_pts + size_pts + focus
    upd = (app.get("currentVersionReleaseDate") or "")[:10] or "?"
    seller = app.get("sellerName") or app.get("artistName") or "?"
    contact = seller + (f" – {app['sellerUrl']}" if app.get("sellerUrl") else "")
    li = ("https://www.linkedin.com/search/results/people/?" +
          urllib.parse.urlencode({"keywords": f"{seller} corporate development"}))
    return {
        "module": "APP",
        "source": "App Store",
        "name": app.get("trackName", "?"),
        # země žebříčku ≠ země vlastníka (Apollo: kanadský vývojář v CZ žebříčku) – proto "?"
        "country": "?",
        "procedure": signal,
        "field": genre,
        "size": f"{ratings:,} hodnocení v App Store".replace(",", " ") if ratings else "?",
        "contact": contact + " (oslov Corporate Development / M&A vlastníka)",
        "link": app.get("trackViewUrl"),
        "links": [("kdo tam dělá M&A (LinkedIn)", li)],
        "notes": [f"Vývojář: {app.get('artistName', '?')}", f"Poslední aktualizace: {upd}",
                  f"Hodnocení: {app.get('averageUserRating', '?')}"] +
                 ([f"Žebříček: {chart_label}"] if chart_label else []),
        "points": points,
        "rating": rate(points, "APP"),
        "grades": grades_app(sig_pts, focus, ratings),
    }


def run_charts(state, seen):
    st = state.setdefault("apps", {})
    ranks = st.setdefault("ranks", {})
    t = today()
    fetched_ids, labels, app_ccs = set(), {}, {}
    fallback_used = False
    for cc in config.APP_COUNTRIES:
        for genre, gname in config.APP_GENRES.items():
            for chart in CHARTS:
                rows = fetch_chart(cc, genre, chart)
                _pause(CHART_PAUSE)
                key = f"{cc}:{genre}:{chart}"
                if not rows:
                    continue
                h = ranks.setdefault(key, {})
                for pos, (aid, name, artist, cat) in enumerate(rows, 1):
                    if _excluded(f"{name} {artist}", cat):
                        continue
                    h.setdefault(aid, {})[t] = pos
                    fetched_ids.add(aid)
                    app_ccs.setdefault(aid, set()).add(cc)
                    labels.setdefault(aid, f"{cc} {gname} {'free' if 'free' in chart else 'grossing'}")
        if not any(k.startswith(cc + ":") and ranks[k] for k in ranks):
            rows = fetch_chart_fallback(cc)
            if rows:
                fallback_used = True
                h = ranks.setdefault(f"{cc}:all:topfree", {})
                for pos, (aid, name, artist, cat) in enumerate(rows, 1):
                    if not _excluded(f"{name} {artist} {cat}", ""):
                        h.setdefault(aid, {})[t] = pos
                        fetched_ids.add(aid)
                        labels.setdefault(aid, f"{cc} top free")
    if fallback_used:
        log("[app] staré RSS s kategoriemi nefunguje – použit nový Apple RSS (bez kategorií)")

    # úklid historie (45 dní) a výpočet poklesů
    cutoff = _days_ago(45)
    drops = {}
    for key, h in ranks.items():
        fetched_today = any(t in v for v in h.values())
        for aid in list(h):
            h[aid] = {d: r for d, r in h[aid].items() if d >= cutoff}
            if not h[aid]:
                del h[aid]
                continue
            if fetched_today:
                sig = detect_drop(h[aid], t)
                if sig and aid not in drops:
                    drops[aid] = (sig, key)

    # watchlist
    wl = st.setdefault("watch_ids", {})
    for name in config.APP_WATCHLIST:
        if name not in wl:
            wl[name] = search_app(name)
    watch_ids = {i for i in wl.values() if i}

    meta = lookup(fetched_ids | watch_ids | set(drops))
    log(f"[app] žebříčky: {len(fetched_ids)} aplikací, poklesů {len(drops)}, detail {len(meta)}")

    out = []
    stale_cut = (now_utc() - timedelta(days=30 * config.APP_STALE_MONTHS)).strftime("%Y-%m-%d")
    # kandidáti (padá v žebříčku nebo dlouho bez aktualizace) – datum aktualizace je globální
    cands = {aid: app for aid, app in meta.items()
             if aid in drops or (app.get("currentVersionReleaseDate") or "9")[:10] < stale_cut}
    cands = {aid: app for aid, app in cands.items()
             if not big_owner(app)
             and not _excluded(f"{app.get('trackName', '')} {app.get('sellerName', '')}",
                               app.get("primaryGenreName", ""))}
    # počet hodnocení v EU obchodech, kde je aplikace v žebříčku (bere se nejvyšší)
    by_cc = {}
    for aid in cands:
        for cc in sorted(app_ccs.get(aid, {"de"}))[:6]:
            by_cc.setdefault(cc, []).append(aid)
    local = {}
    for cc, ids in by_cc.items():
        for aid, r in lookup(ids, cc).items():
            n = int(r.get("userRatingCount") or 0)
            if n > local.get(aid, (0, None, None))[0]:
                local[aid] = (n, cc, r.get("averageUserRating"))
    log(f"[app] kandidátů {len(cands)}, ověřeno v EU obchodech {len(local)}")
    for aid, app in cands.items():
        n, cc, avg = local.get(aid, (0, None, None))
        app = dict(app, userRatingCount=n, averageUserRating=avg if avg is not None else app.get("averageUserRating"))
        ratings = n
        if ratings > config.APP_MAX_RATINGS:
            continue
        if avg is not None and float(avg) < config.APP_MIN_AVG_RATING:
            continue  # uživatelé ji hodnotí špatně – nejspíš nefunguje
        if dead_product(app) or platform_dependent(app):
            continue
        upd = (app.get("currentVersionReleaseDate") or "")[:10]
        stale = (config.APP_STALE_SIGNAL and bool(upd) and upd < stale_cut
                 and ratings >= config.APP_MIN_RATINGS)
        drop = drops.get(aid)
        if drop and stale:
            sig, pts = f"{drop[0]} + bez aktualizace od {upd}", 4
        elif drop:
            sig, pts = drop[0], 3
        elif stale:
            sig, pts = f"populární aplikace (v žebříčku), vlastník ji neaktualizuje od {upd}", 3
        else:
            continue
        key = f"APP:{aid}:{'drop' if drop else 'stale'}"
        if key in seen or (not drop and f"APP:{aid}:drop" in seen):
            continue
        case = _app_case(app, sig, pts, labels.get(aid, ""))
        case["key"] = key
        if cc:
            case["size"] += f" (obchod {cc.upper()})"
        if drop:
            corroborate(case, app)
        if aid in watch_ids:
            case["notes"].insert(0, "Na tvém seznamu sledovaných (APP_WATCHLIST)")
            case["points"] += 1
            case["rating"] = rate(case["points"], "APP")
        out.append(case)
    return out


def run_news(seen, fps):
    if not config.APP_NEWS_CREATE_CASES:
        return []
    items = []
    for q in config.APP_NEWS_QUERIES:
        items += news.search(q, "EN", days=config.APP_NEWS_MAX_AGE_DAYS)
    out = []
    for it in items:
        text = f"{it['title']} {it['summary']}".lower()
        if any(k in text for k in config.APP_EXCLUDED_KEYWORDS):
            continue
        if not any(k in text for k in config.APP_FOCUS_KEYWORDS):
            continue
        sig = next(((lab, p) for kw, (lab, p) in config.APP_NEWS_SIGNALS.items() if kw in text), None)
        if not sig:
            continue
        key = "APP:news:" + hashlib.sha1(it["title"].lower().encode()).hexdigest()[:16]
        if key in seen or news.is_duplicate(it["title"], fps):
            continue
        fp = sorted(news.fingerprint(it["title"]))
        fps.append(fp)
        focus = 2 if any(k in text for k in ("language", "learning", "edtech", "education")) else 1
        app = find_app_for_news(it["title"]) if sig[1] >= 3 else None
        ratings = int((app or {}).get("userRatingCount") or 0)
        if app and _excluded(app.get("trackName", ""), app.get("primaryGenreName", "")):
            continue
        if app and (dead_product(app) or platform_dependent(app)):
            continue
        if app:
            case = _app_case(app, sig[0], sig[1])
            case.update({"key": key, "fp": fp, "source": "zprávy + App Store", "link": it["link"]})
            case["links"].insert(0, ("aplikace v App Store", app.get("trackViewUrl", "")))
            case["notes"] = [f"Titulek: {it['title']}",
                             f"Zdroj: {it['source'] or '?'} ({it['date'] or '?'})",
                             "Aplikace dohledána podle názvu ve zprávě – ověř, že jde o tu správnou."] + case["notes"]
            out.append(case)
            continue
        points = sig[1] + focus + 1  # +1 = velikost "?"
        out.append({
            "key": key, "fp": fp, "module": "APP", "source": "zprávy",
            "name": news.guess_company(it["title"]),
            "country": "?",
            "procedure": sig[0],
            "field": "vzdělávání / jazyky" if focus == 2 else "spotřebitelská / e-commerce appka",
            "size": "?",
            "contact": "? – vlastník je uveden ve zprávě; oslov Corporate Development / M&A",
            "link": it["link"], "links": [],
            "notes": [f"Titulek: {it['title']}", f"Zdroj: {it['source'] or '?'} ({it['date'] or '?'})"],
            "points": points, "rating": rate(points, "APP"),
            "grades": grades_app(sig[1], focus, ratings),
        })
    log(f"[app] zpráv {len(items)}, případů {len(out)}")
    return out
