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
from common import http, log, now_utc, rate, today
from sources import news

CHARTS = ("topfreeapplications", "topgrossingapplications")


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


def lookup(ids, cc="us"):
    out = {}
    ids = list(dict.fromkeys(str(i) for i in ids))
    for i in range(0, len(ids), 150):
        chunk = ids[i:i + 150]
        data = _get_json(f"https://itunes.apple.com/lookup?id={','.join(chunk)}&country={cc}")
        for r in (data or {}).get("results", []):
            if r.get("trackId"):
                out[str(r["trackId"])] = r
    return out


def search_app(term):
    q = urllib.parse.urlencode({"term": term, "entity": "software", "limit": 1, "country": "us"})
    data = _get_json(f"https://itunes.apple.com/search?{q}")
    res = (data or {}).get("results") or []
    return str(res[0]["trackId"]) if res else None


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
    size_pts = 3 if ratings >= 100_000 else 2 if ratings >= config.APP_MIN_RATINGS else 1 if ratings else 1
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
        "country": "?" if not chart_label else chart_label.split(" ")[0].upper(),
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
    }


def run_charts(state, seen):
    st = state.setdefault("apps", {})
    ranks = st.setdefault("ranks", {})
    t = today()
    fetched_ids, labels = set(), {}
    fallback_used = False
    for cc in config.APP_COUNTRIES:
        for genre, gname in config.APP_GENRES.items():
            for chart in CHARTS:
                rows = fetch_chart(cc, genre, chart)
                key = f"{cc}:{genre}:{chart}"
                if not rows:
                    continue
                h = ranks.setdefault(key, {})
                for pos, (aid, name, artist, cat) in enumerate(rows, 1):
                    if _excluded(f"{name} {artist}", cat):
                        continue
                    h.setdefault(aid, {})[t] = pos
                    fetched_ids.add(aid)
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
    for aid, app in meta.items():
        genre = app.get("primaryGenreName", "")
        if _excluded(f"{app.get('trackName', '')} {app.get('sellerName', '')}", genre):
            continue
        ratings = int(app.get("userRatingCount") or 0)
        upd = (app.get("currentVersionReleaseDate") or "")[:10]
        stale = bool(upd) and upd < stale_cut and ratings >= config.APP_MIN_RATINGS
        drop = drops.get(aid)
        if drop and stale:
            sig, pts = f"{drop[0]} + bez aktualizace od {upd}", 4
        elif drop:
            sig, pts = drop[0], 3
        elif stale:
            sig, pts = f"velká aplikace bez aktualizace od {upd}", 2
        else:
            continue
        key = f"APP:{aid}:{'drop' if drop else 'stale'}"
        if key in seen or (not drop and f"APP:{aid}:drop" in seen):
            continue
        case = _app_case(app, sig, pts, labels.get(aid, ""))
        case["key"] = key
        if aid in watch_ids:
            case["notes"].insert(0, "Na tvém seznamu sledovaných (APP_WATCHLIST)")
            case["points"] += 1
            case["rating"] = rate(case["points"], "APP")
        out.append(case)
    return out


def run_news(seen, fps):
    items = []
    for q in config.APP_NEWS_QUERIES:
        items += news.search(q, "EN")
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
        })
    log(f"[app] zpráv {len(items)}, případů {len(out)}")
    return out
