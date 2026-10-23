"""
Sběr nových inzerátů bytů a domů v Praze z Bazoš.cz a Sbazar.cz.
Výstup: docs/data.json (čte ho dashboard docs/index.html).
Volitelně posílá nové inzeráty do Telegramu (secrets TELEGRAM_TOKEN, TELEGRAM_CHAT_ID).
"""
import json, os, re, sys, time, random
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------------ NASTAVENÍ
DATA_FILE = Path("docs/data.json")
KEEP_DAYS = 30            # jak dlouho držet inzeráty v datech
MAX_PAGES = 8             # max. stránek na jednu kategorii a běh (20 inzerátů/str. na Bazoši)

# Bazoš: akce x typ -> URL se generují automaticky
BAZOS_AKCE = {"prodej": "prodam", "pronajem": "pronajmu"}
BAZOS_TYP = {"byt": "byt", "dum": "dum"}
BAZOS_PARAMS = {"hlokalita": "11000", "humkreis": "15"}   # Praha + okolí 15 km, pak filtr na PSČ 1xx xx

# Sbazar: vlož URL vyhledávání zkopírované z prohlížeče (Praha, byty/domy, prodej/pronájem).
# Klíč = (akce, typ). Prázdné URL se přeskočí.
SBAZAR_URLS = {
    ("prodej", "byt"): "",
    ("pronajem", "byt"): "",
    ("prodej", "dum"): "",
    ("pronajem", "dum"): "",
}

# Telegram: posílat jen inzeráty, které splní tyto podmínky (None = nefiltrovat)
NOTIFY = {
    "akce": None,          # "prodej" / "pronajem" / None
    "typ": None,           # "byt" / "dum" / None
    "max_cena": None,      # např. 8_000_000
    "min_m2": None,        # např. 50
    "dispozice": None,     # např. ["2+kk", "3+kk"]
}
MAX_SINGLE = 15         # kolik inzerátů poslat samostatně, zbytek přijde jako souhrn

# Filtr realitek: "rk_ven" = posílat soukromníky i nejisté (vyřadí jen jasné RK),
#                 "jen_soukromi" = posílat jen jasné soukromníky, None = posílat vše
SELLER_FILTER = "rk_ven"
DIGEST_HOUR_UTC = 16    # denní souhrn vyřazených (16 UTC = 18:00 v létě / 17:00 v zimě)
MAX_DETAILS = 100       # max. detailů inzerátů načtených za jeden běh (šetrnost k Bazoši)
RK_MIN_LISTINGS = 3     # prodávající s tolika a více inzeráty v našich datech = realitka

RK_WORDS = [
    r"realitn\w* kancel", r"makl[eé]ř", r"provize", r"zprostředk", r"exkluzivně", r"exkluzivn\w* (nabíd|nabíz|prodej|zastoupen|smlouv)",
    r"naše společnost", r"naše kancelář",     r"id nabídky", r"číslo nabídky", r"kód nabídky", r"\bev\. ?č", r"\bev\. ?číslo",
    r"poplatek za (podnájem|zprostředkování|služby)", r"\w*realit\w*\.(cz|com|eu)",
    r"číslo zakázky", r"id zakázky", r"evidenční číslo", r"kontaktujte (makléře|naši)",
    r"rezervační (poplatek|smlouv)", r"právní servis", r"financování zajistíme", r"hypoteční poradenství",
    r"re/?max", r"century ?21", r"m ?& ?m reality", r"m ?& ?m\b", r"maxima reality", r"svoboda ?& ?williams",
    r"engel ?& ?v[oö]lkers", r"lexxus", r"bidli", r"realitymix", r"sting", r"mm reality",
    r"reality\.cz", r"realit[ay]\b.*s\.r\.o", r"s\.r\.o\.", r"\bs\.? ?r\.? ?o\b", r"\bspol\.", r"a\.s\.", r"properties", r"real estate",
]
# Konkrétní realitky / makléři, které chceš vždy vyřadit (stačí část jména, malá písmena)
RK_SELLERS = [
    "ladislav burian", "realbrána", "realbrana",
    "ideální nájemce", "dumrealit", "jan paschke", "paschke", "hvb real estate", "finpos", "aleš doubek", "makers reality", "gepard",
    "vlasta marklová", "žalmánek", "váš konzultant realit", "realityspolu", "reality spolu", "petráčková",
    "next reality", "karel zajac", "zoom", "bohemian estates", "broker consulting",
]

# Inzeráty, kde majitel výslovně nechce RK – vyřadit (nemá smysl volat)
NO_RK_WORDS = [
    r"(rk|realitk\w*|realitní\w* kancelář\w*|makléř\w*)[^.\n]{0,25}(nevolat|nevolejte|nekontaktovat|nekontaktujte|neozývat|neozývejte|neodpovídám|nepište|ne,? děkuji|děkuji,? ne)",
    r"(nevolat|nevolejte|nekontaktovat|nekontaktujte)[^.\n]{0,15}(rk|realitk\w*|realitní\w* kancelář\w*|makléř\w*)",
    r"(nemám|nemáme) zájem o (rk|realitk\w*|služby (rk|realitk\w*|makléř\w*))",
    r"bez zájmu o (rk|realitk\w*)", r"spolupráci s (rk|realitk\w*) (nechci|nepožaduji|odmítám)",
]

# Slabé znaky RK: samy o sobě inzerát nevyřadí, jen ho označí jako ❔ nejistý
RK_WEAK = [r"exkluziv", r"\brk\b", r"nabízíme (vám )?(k )?(prodeji|pronájmu|podnájmu)", r"nabízíme vám"]

PRIVATE_WORDS = [r"bez rk", r"nejsem rk", r"ne ?rk", r"přímo od majitele", r"bez provize", r"provize se neplatí", r"bez poplatku rk", r"od majitele", r"jsem majitel", r"soukrom[áý] osoba", r"bez realitky"]
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "cs-CZ,cs;q=0.9",
}
S = requests.Session()
S.headers.update(HEADERS)
NOW = datetime.now(timezone.utc)


def log(*a):
    print(*a, flush=True)


START = time.time()
MAX_RUNTIME = 6 * 60      # po 6 minutách přestat stahovat a uložit, co máme


class OutOfTime(Exception):
    pass


def get(url, params=None):
    if time.time() - START > MAX_RUNTIME:
        raise OutOfTime("vyčerpán časový limit běhu")
    time.sleep(random.uniform(1.5, 3.0))   # šetrně k serverům
    r = S.get(url, params=params, timeout=(10, 20))
    r.raise_for_status()
    return r.text


def parse_price(text):
    if not text:
        return None
    t = text.replace("\xa0", " ")
    num = r"(\d{1,3}(?:[ .]\d{3})+|\d{4,})"
    m = re.search(num + r"\s*(?:Kč|,-|CZK)", t, re.I) or re.search(num, t)
    if not m:
        return None
    try:
        v = int(re.sub(r"\D", "", m.group(1)))
        return v if v >= 1000 else None
    except ValueError:
        return None


def parse_layout(text):
    m = re.search(r"\b(\d)\s?\+\s?(kk|1)\b", text, re.I)
    return f"{m.group(1)}+{m.group(2).lower()}" if m else None


def parse_area(text):
    for m in re.finditer(r"(\d{2,4}(?:[.,]\d{1,2})?)\s?(?:m2|m²|m\^2|metr|㎡)", text, re.I):
        v = float(m.group(1).replace(",", "."))
        if 12 <= v <= 1500:
            return round(v)
    return None


def parse_district(text):
    m = re.search(r"Praha[\s-]*(\d{1,2})\b", text, re.I)
    return f"Praha {int(m.group(1))}" if m else ("Praha" if re.search(r"praha", text, re.I) else None)


def enrich(item):
    blob = f"{item.get('title','')} {item.get('desc','')}"
    item.setdefault("layout", parse_layout(blob))
    item.setdefault("area", parse_area(blob))
    if not item.get("district"):
        item["district"] = parse_district(f"{item.get('locality','')} {blob}")
    if item.get("price") and item.get("area"):
        item["ppm2"] = round(item["price"] / item["area"])
    return item


# ------------------------------------------------------------------ BAZOŠ
def bazos_page(akce, typ, offset):
    path = f"https://reality.bazos.cz/{BAZOS_AKCE[akce]}/{BAZOS_TYP[typ]}/"
    if offset:
        path += f"{offset}/"
    try:
        html = get(path, BAZOS_PARAMS)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return []          # za poslední stránkou výsledků
        raise
    soup = BeautifulSoup(html, "lxml")
    out = []
    for box in soup.select("div.inzeraty"):
        a = box.select_one("h2.nadpis a, .nadpis a")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/inzerat/(\d+)/", href)
        if not m:
            continue
        url = href if href.startswith("http") else "https://reality.bazos.cz" + href
        loc_el = box.select_one(".inzeratylok")
        loc = loc_el.get_text(" ", strip=True) if loc_el else ""
        psc = re.search(r"\b(\d{3})\s?(\d{2})\b", loc)
        psc = f"{psc.group(1)} {psc.group(2)}" if psc else None
        if psc and not psc.startswith("1"):      # mimo Prahu
            continue
        full = box.get_text(" ", strip=True)
        d = re.search(r"\[(\d{1,2})\.(\d{1,2})\.\s?(\d{4})\]", full)
        posted = f"{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}" if d else None
        img = box.select_one("img")
        desc_el = box.select_one(".popis")
        price_el = box.select_one(".inzeratycena")
        out.append(enrich({
            "key": f"bazos:{m.group(1)}",
            "source": "bazos",
            "url": url,
            "title": a.get_text(strip=True),
            "desc": (desc_el.get_text(" ", strip=True) if desc_el else "")[:400],
            "price": parse_price(price_el.get_text(" ", strip=True) if price_el else ""),
            "price_text": price_el.get_text(" ", strip=True) if price_el else "",
            "locality": loc.replace(psc or "", "").strip(),
            "psc": psc,
            "img": img.get("src") if img else None,
            "posted": posted,
            "akce": akce,
            "typ": typ,
        }))
    return out


def bazos_detail(item):
    """Načte detail inzerátu: celý popis a jméno / ID prodávajícího."""
    try:
        soup = BeautifulSoup(get(item["url"]), "lxml")
    except Exception as e:
        log(f"[bazos] detail {item['key']}: CHYBA {e}")
        return
    d = soup.select_one(".popisdetail")
    if d:
        item["desc_full"] = d.get_text(" ", strip=True)[:3000]
    for td in soup.find_all("td"):
        if td.get_text(strip=True).rstrip(":").lower() == "jméno":
            nxt = td.find_next("td")
            if nxt:
                item["seller"] = nxt.get_text(" ", strip=True)[:80]
            break
    for a in soup.select('a[href*="idphone"], a[href*="idmail"], a[href*="hodnoceni"]'):
        m = re.search(r"id(?:phone|mail)=(\w+)", a.get("href", ""))
        if m:
            item["seller_id"] = m.group(1)
            break


RK_KNOWN, RK_PHONES = set(), set()


def _norm_phone(ph):
    d = re.sub(r"\D", "", str(ph))
    return d[-9:] if len(d) >= 9 else d


def classify(item, seller_counts):
    """Vrací 'rk', 'soukromy' nebo 'nejiste' + důvod."""
    if item.get("source") == "ulovdomov":
        if item.get("ud_external"):
            return "rk", "převzato z realitního portálu"
        if item.get("ud_private") is False:
            return "rk", "UlovDomov: není soukromý majitel"
    text = " ".join(str(item.get(k) or "") for k in ("title", "desc", "desc_full")).lower()
    seller = (item.get("seller") or "").lower()
    for w in NO_RK_WORDS:
        if re.search(w, text):
            return "rk", "majitel nechce RK"
    for name in RK_SELLERS:
        pat = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
        if re.search(pat, seller) or re.search(pat, text):
            return "rk", f"na seznamu RK ({name})"
    if re.search(r"\s[-–|]\s*\S", item.get("seller") or ""):
        return "rk", f"jméno s firmou ({item.get('seller')})"
    if re.search(r"\w(real|reality|estate|invest)\b|,", seller) or \
            re.search(r"\bREAL|\bReal(?:it|\b|[A-ZÁ-Ž])", item.get("seller") or ""):
        return "rk", f"jméno firmy ({item.get('seller')})"
    for w in RK_WORDS:
        if re.search(w, seller):
            return "rk", f"jméno prodávajícího ({item.get('seller')})"
    if seller and len(seller.split()) >= 2 and seller in RK_KNOWN:
        return "rk", f"dříve vyřazen jako RK ({item.get('seller')})"
    if item.get("phone") and _norm_phone(item["phone"]) in RK_PHONES:
        return "rk", "telefon patří realitce"
    if item.get("phone") and seller_counts.get("tel:" + _norm_phone(item["phone"]), 0) >= RK_MIN_LISTINGS:
        return "rk", "stejný telefon u více inzerátů"
    sid = item.get("seller_id") or seller
    if sid and seller_counts.get(sid, 0) >= RK_MIN_LISTINGS:
        return "rk", f"{seller_counts[sid]} inzerátů od stejného prodávajícího"
    priv = [w for w in PRIVATE_WORDS if re.search(w, text)]
    clean = text
    for w in PRIVATE_WORDS:                      # "bez RK" nesmí spustit RK
        clean = re.sub(w, " ", clean)
    hits = [w for w in RK_WORDS if re.search(w, clean)]
    if hits and not priv:
        return "rk", "text inzerátu (" + re.sub(r"\\b|\\", "", hits[0]) + ")"
    weak = [w for w in RK_WEAK if re.search(w, clean)]
    if weak and not priv:
        return "nejiste", "slabý znak RK v textu"
    if priv and not hits:
        return "soukromy", "v textu uvádí soukromou nabídku"
    if item.get("seller") and not hits:
        return "soukromy", "jméno fyzické osoby, žádné znaky RK"
    return "nejiste", "nedostatek informací"


def scrape_bazos(known):
    found = []
    for akce in BAZOS_AKCE:
        for typ in BAZOS_TYP:
            for p in range(MAX_PAGES):
                try:
                    items = bazos_page(akce, typ, p * 20)
                except Exception as e:
                    log(f"[bazos] {akce}/{typ} str.{p}: CHYBA {e}")
                    break
                found += items
                fresh = [i for i in items if i["key"] not in known]
                log(f"[bazos] {akce}/{typ} str.{p}: {len(items)} inzerátů, nových {len(fresh)}")
                if not items or (p > 0 and not fresh):   # dál už jen staré
                    break
    return found


# ------------------------------------------------------------------ SBAZAR
def _walk_json(obj):
    """Najde v libovolném JSONu objekty, které vypadají jako inzerát."""
    if isinstance(obj, dict):
        keys = set(obj)
        if "id" in keys and ("name" in keys or "title" in keys) and ("price" in keys or "seo_name" in keys):
            yield obj
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def sbazar_parse(html, akce, typ):
    soup = BeautifulSoup(html, "lxml")
    out = {}

    # 1) vložená JSON data stránky (Next.js / state / ld+json)
    for sc in soup.find_all("script"):
        txt = sc.string or ""
        if not txt or ("price" not in txt and "Offer" not in txt):
            continue
        txt = txt.strip()
        cand = None
        try:
            cand = json.loads(txt)
        except Exception:
            m = re.search(r"=\s*(\{.*\})\s*;?\s*$", txt, re.S)
            if m:
                try:
                    cand = json.loads(m.group(1))
                except Exception:
                    pass
        if cand is None:
            continue
        for o in _walk_json(cand):
            iid = str(o.get("id"))
            title = o.get("name") or o.get("title") or ""
            price = o.get("price")
            if isinstance(price, dict):
                price = price.get("value") or price.get("amount")
            loc = o.get("locality") or {}
            loc_txt = " ".join(str(v) for v in loc.values()) if isinstance(loc, dict) else str(loc)
            seo = o.get("seo_name") or ""
            user = (o.get("user") or {}).get("user_service", {}).get("shop_url") if isinstance(o.get("user"), dict) else None
            url = o.get("url") or (f"https://www.sbazar.cz/{user}/detail/{iid}-{seo}" if user and seo else None)
            img = None
            imgs = o.get("images") or []
            if imgs and isinstance(imgs, list) and isinstance(imgs[0], dict):
                img = imgs[0].get("url")
                if img and img.startswith("//"):
                    img = "https:" + img
            if not url:
                continue
            out[iid] = {"key": f"sbazar:{iid}", "url": url, "title": title,
                        "desc": (o.get("description") or "")[:400],
                        "price": int(price) if isinstance(price, (int, float)) and price > 999 else None,
                        "locality": loc_txt, "img": img,
                        "posted": (o.get("create_date") or o.get("created") or "")[:10] or None}

    # 2) záloha: odkazy na detail inzerátu přímo z HTML
    if not out:
        for a in soup.select('a[href*="/detail/"]'):
            href = a.get("href", "")
            m = re.search(r"/detail/(\d+)", href)
            if not m or m.group(1) in out:
                continue
            card = a
            for _ in range(4):           # vyšplhat na kartu inzerátu
                if card.parent and len(card.parent.get_text(" ", strip=True)) < 600:
                    card = card.parent
            text = card.get_text(" ", strip=True)
            img = card.select_one("img")
            out[m.group(1)] = {
                "key": f"sbazar:{m.group(1)}",
                "url": href if href.startswith("http") else "https://www.sbazar.cz" + href,
                "title": a.get_text(" ", strip=True) or text[:120],
                "desc": text[:400], "price": parse_price(text), "locality": text,
                "img": (img.get("src") or img.get("data-src")) if img else None, "posted": None,
            }

    items = []
    for v in out.values():
        v.update({"source": "sbazar", "akce": akce, "typ": typ, "psc": None})
        if v.get("img") and v["img"].startswith("//"):
            v["img"] = "https:" + v["img"]
        items.append(enrich(v))
    return items


def scrape_sbazar(known):
    found = []
    for (akce, typ), url in SBAZAR_URLS.items():
        if not url:
            continue
        try:
            items = sbazar_parse(get(url), akce, typ)
            log(f"[sbazar] {akce}/{typ}: {len(items)} inzerátů, nových {sum(i['key'] not in known for i in items)}")
            if not items:
                log("[sbazar] 0 inzerátů – nejspíš se změnila struktura stránky, pošli log Claudovi")
            found += items
        except Exception as e:
            log(f"[sbazar] {akce}/{typ}: CHYBA {e}")
    return found


# ------------------------------------------------------------------ ULOVDOMOV
UD_FIND = "https://ud.api.ulovdomov.cz/v1/offer/find"
UD_CONTACT = "https://www.ulovdomov.cz/fe-api/offer/contact-info/{}"
UD_PRAHA = {"northEast": {"lat": 50.178, "lng": 14.707}, "southWest": {"lat": 49.942, "lng": 14.224}}
UD_TYPES = {("pronajem", "byt"): ("rent", "flat"), ("prodej", "byt"): ("sale", "flat"),
            ("pronajem", "dum"): ("rent", "house"), ("prodej", "dum"): ("sale", "house")}
UD_PAGES = 3
UD_LAYOUT = {"onePlusKk": "1+kk", "onePlusOne": "1+1", "twoPlusKk": "2+kk", "twoPlusOne": "2+1",
             "threePlusKk": "3+kk", "threePlusOne": "3+1", "fourPlusKk": "4+kk", "fourPlusOne": "4+1",
             "fivePlusKk": "5+kk", "fivePlusOne": "5+1"}


def _ud_offers(obj):
    """Najde v odpovědi seznam inzerátů (slovníky s id a absoluteUrl/seo)."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "id" in obj[0] \
            and ("absoluteUrl" in obj[0] or "seo" in obj[0]):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = _ud_offers(v)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _ud_offers(v)
            if r:
                return r
    return []


def _ud_item(o, akce, typ):
    village = ((o.get("village") or {}).get("title") or "")
    part = ((o.get("villagePart") or {}).get("title") or "")
    street = ((o.get("street") or {}).get("title") or "")
    price = (o.get("rentalPrice") or o.get("price") or {})
    price = price.get("value") if isinstance(price, dict) else price
    url = o.get("absoluteUrl") or f"https://www.ulovdomov.cz/inzerat/{o.get('seo', '')}/{o['id']}"
    photo = (o.get("photos") or [{}])[0].get("path") if o.get("photos") else None
    item = {
        "key": f"ulovdomov:{o['id']}", "source": "ulovdomov", "ud_id": o["id"], "url": url,
        "title": o.get("title") or "", "desc": (o.get("description") or "")[:400],
        "price": int(price) if isinstance(price, (int, float)) and price > 999 else None,
        "price_text": o.get("priceNote") or "", "locality": ", ".join(x for x in (street, part, village) if x),
        "img": photo, "posted": (o.get("published") or "")[:10] or None, "akce": akce, "typ": typ,
        "no_commission": o.get("isNoCommission"), "psc": None,
        "layout": UD_LAYOUT.get(o.get("disposition")), "area": o.get("area"),
    }
    m = re.search(r"Praha[\s-]*(\d{1,2})", f"{part} {village}")
    if m:
        item["district"] = f"Praha {int(m.group(1))}"
    return enrich(item)


def scrape_ulovdomov(known):
    found = []
    for (akce, typ), (ot, pt) in UD_TYPES.items():
        for page in range(1, UD_PAGES + 1):
            try:
                if time.time() - START > MAX_RUNTIME:
                    raise OutOfTime("vyčerpán časový limit běhu")
                time.sleep(random.uniform(1.5, 3.0))
                r = S.post(UD_FIND, params={"page": page, "perPage": 20, "sorting": "latest"},
                           json={"bounds": UD_PRAHA, "offerType": ot, "propertyType": pt}, timeout=(10, 20))
                if page == 1 and akce == "pronajem" and typ == "byt":
                    Path("docs/probe").mkdir(parents=True, exist_ok=True)
                    Path("docs/probe/ud_find.json").write_text(r.text[:200000], "utf-8")
                r.raise_for_status()
                offers = _ud_offers(r.json())
            except Exception as e:
                log(f"[ulovdomov] {akce}/{typ} str.{page}: CHYBA {e}")
                break
            items = [_ud_item(o, akce, typ) for o in offers]
            items = [i for i in items if "praha" in i["locality"].lower()]
            found += items
            fresh = [i for i in items if i["key"] not in known]
            log(f"[ulovdomov] {akce}/{typ} str.{page}: {len(offers)} inzerátů, v Praze {len(items)}, nových {len(fresh)}")
            if not offers or not fresh:
                break
    return found


def ulovdomov_contact(item):
    """Kontakt u inzerátu: soukromý majitel / firma / převzatý inzerát z jiného webu."""
    try:
        time.sleep(random.uniform(1.0, 2.0))
        r = S.get(UD_CONTACT.format(item["ud_id"]), timeout=(10, 20), headers={"Accept": "application/json"})
        if not Path("docs/probe/ud_contact.json").exists():
            Path("docs/probe").mkdir(parents=True, exist_ok=True)
            Path("docs/probe/ud_contact.json").write_text(r.text[:20000], "utf-8")
        d = r.json()
        d = d.get("data", d) if isinstance(d, dict) else {}
    except Exception as e:
        log(f"[ulovdomov] kontakt {item['key']}: CHYBA {e}")
        return
    name = " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x)
    item["seller"] = (f"{name} ({d['company_name']})" if name and d.get("company_name")
                      else d.get("company_name") or name or None)
    item["phone"] = d.get("phone") or None
    item["ud_private"] = d.get("is_private_landlord")
    item["ud_external"] = bool(d.get("external_url"))


# ------------------------------------------------------------------ TELEGRAM
def matches_notify(i):
    st = i.get("seller_type", "nejiste")
    if SELLER_FILTER == "rk_ven" and st == "rk": return False
    if SELLER_FILTER == "jen_soukromi" and st != "soukromy": return False
    f = NOTIFY
    if f["akce"] and i["akce"] != f["akce"]: return False
    if f["typ"] and i["typ"] != f["typ"]: return False
    if f["max_cena"] and (not i.get("price") or i["price"] > f["max_cena"]): return False
    if f["min_m2"] and (not i.get("area") or i["area"] < f["min_m2"]): return False
    if f["dispozice"] and i.get("layout") not in f["dispozice"]: return False
    return True


def _fmt(i):
    price = f"{i['price']:,} Kč".replace(",", " ") if i.get("price") else (i.get("price_text") or "cena neuvedena")
    if i.get("price") and i["akce"] == "pronajem":
        price += "/měs."
    meta = " | ".join(str(x) for x in [
        "Prodej" if i["akce"] == "prodej" else "Pronájem",
        i.get("layout"), f"{i['area']} m²" if i.get("area") else None,
        f"{i['ppm2']:,} Kč/m²".replace(",", " ") if i.get("ppm2") else None,
        i.get("district"), {"bazos": "Bazoš", "ulovdomov": "UlovDomov"}.get(i["source"], i["source"]),
        "bez provize" if i.get("no_commission") else None] if x)
    return price, meta


def _send(tok, chat, text, preview=True):
    # TELEGRAM_CHAT_ID může obsahovat víc ID oddělených čárkou -> pošle se všem
    for cid in [c.strip() for c in str(chat).split(",") if c.strip()]:
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              json={"chat_id": cid, "text": text, "disable_web_page_preview": not preview},
                              timeout=15)
            if not r.ok:
                log(f"[telegram] {cid}: {r.status_code} {r.text[:120]}")
        except Exception as e:
            log("[telegram]", e)
        time.sleep(1.1)            # limit Telegramu ~1 zpráva/s do jednoho chatu


def notify(new_items):
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    items = [x for x in new_items if matches_notify(x)]
    items.sort(key=lambda x: (x["akce"], x["typ"]))
    single, rest = items[:MAX_SINGLE], items[MAX_SINGLE:]
    for i in single:                       # každý inzerát zvlášť, s náhledem fotky
        price, meta = _fmt(i)
        who = {"soukromy": "👤 Soukromník", "nejiste": "❔ Nejisté (RK nepotvrzena)"}.get(i.get("seller_type"), "")
        if i.get("seller"):
            who += f" – {i['seller']}"
        q = " ".join(x for x in (f'"{i["seller"]}"' if i.get("seller") else "", i.get("phone") or "", "reality") if x)
        google = "https://www.google.com/search?q=" + requests.utils.quote(q) if i.get("seller") or i.get("phone") else ""
        tel = f"📞 {i['phone']}\n" if i.get("phone") else ""
        _send(tok, chat, f"🏠 {i['title']}\n{price}\n{meta}\n{who}\n{tel}{i['url']}"
                         + (f"\n🔎 Prověřit v Googlu: {google}" if google else ""), preview=True)
    if rest:                               # zbytek v souhrnných zprávách
        lines = [f"📋 Dalších {len(rest)} nových inzerátů:"]
        for i in rest:
            price, meta = _fmt(i)
            lines.append(f"\n• {i['title'][:80]}\n  {price} | {meta}\n  {i['url']}")
        chunk = ""
        for ln in lines:
            if len(chunk) + len(ln) > 3800:
                _send(tok, chat, chunk, preview=False)
                chunk = ""
            chunk += ln + "\n"
        if chunk:
            _send(tok, chat, chunk, preview=False)
    skipped = sum(1 for x in new_items if x.get("seller_type") == "rk")
    log(f"[telegram] odesláno {len(items)} inzerátů, vyřazeno realitek: {skipped}")


def daily_rk_digest(store):
    """Jednou denně pošle přehled vyřazených inzerátů, ať vidíš, jestli filtr nevyhodil soukromníka."""
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat) or NOW.hour != DIGEST_HOUR_UTC or NOW.minute >= 30:
        return
    since = (NOW - timedelta(hours=24)).isoformat()
    rk = [v for v in store.values() if v.get("seller_type") == "rk" and v["first_seen"] >= since]
    if not rk:
        return
    lines = [f"🚫 Vyřazeno filtrem za 24 h: {len(rk)}\nZkontroluj, jestli tu není soukromník:"]
    for v in rk:
        lines.append(f"\n• {v['title'][:70]}\n  {v.get('seller') or '?'} | důvod: {v.get('seller_reason','')}\n  {v['url']}")
    chunk = ""
    for ln in lines:
        if len(chunk) + len(ln) > 3800:
            _send(tok, chat, chunk, preview=False); chunk = ""
        chunk += ln + "\n"
    if chunk:
        _send(tok, chat, chunk, preview=False)


# ------------------------------------------------------------------ MAIN

# ------------------------------------------------------------------ PRŮZKUM NOVÝCH ZDROJŮ (dočasné)
PROBE_URLS = {}


def probe():
    """Stáhne JavaScript UlovDomova, ve kterém je adresa jejich datového rozhraní."""
    out = Path("docs/probe")
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*"):
        f.unlink()
    try:
        h = S.get("https://www.ulovdomov.cz/pronajem/bytu/praha", timeout=(10, 20)).text
        js = re.findall(r'/_next/static/chunks/[^"]+\.js', h)
        for i, path in enumerate(js):
            r = S.get("https://www.ulovdomov.cz" + path, timeout=(10, 20))
            (out / f"ud_js_{i}.txt").write_text(path + "\n" + r.text, "utf-8")
            time.sleep(1)
        log(f"[probe] ulovdomov js: {len(js)} souborů")
    except Exception as e:
        log(f"[probe] CHYBA {e}")


def find_duplicate(i, store):
    """Stejný byt z jiného webu: shoda typu, dispozice, plochy ±1 m², ceny ±2 % a čtvrti (nebo telefonu)."""
    for k, v in store.items():
        if k == i["key"] or v.get("source") == i["source"] or v.get("akce") != i["akce"] or v.get("typ") != i["typ"]:
            continue
        if i.get("phone") and v.get("phone") and _norm_phone(i["phone"]) == _norm_phone(v["phone"]) \
                and i.get("layout") == v.get("layout"):
            return k
        if not (i.get("price") and v.get("price")) or abs(i["price"] - v["price"]) > 0.02 * v["price"]:
            continue
        if not (i.get("area") and v.get("area")) or abs(i["area"] - v["area"]) > 1:
            continue
        if i.get("layout") and v.get("layout") and i["layout"] != v["layout"]:
            continue
        if i.get("district") and v.get("district") and i["district"] != v["district"]:
            continue
        return k
    return None


def main():
    data = {"listings": {}}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text("utf-8"))
    store = data["listings"]
    first_run = not store
    known = set(store)

    found = scrape_bazos(known) + scrape_sbazar(known)
    ud_first = not any(v["source"] == "ulovdomov" for v in store.values())
    try:
        found += scrape_ulovdomov(known)
    except Exception as e:
        log("[ulovdomov] CHYBA", e)

    # paměť realitek: jména (aspoň 2 slova) a telefony, které už byly jednou vyřazené jako RK
    for v in store.values():
        if v.get("seller_type") == "rk" and v.get("seller_reason") != "majitel nechce RK":
            if v.get("seller") and len(v["seller"].split()) >= 2:
                RK_KNOWN.add(v["seller"].lower())
            if v.get("phone"):
                RK_PHONES.add(_norm_phone(v["phone"]))

    # detail (jméno prodávajícího, celý popis) u nových inzerátů z Bazoše
    # + u starších, kde se detail minule nestihl načíst ("pending")
    pending = [dict(v) for v in store.values() if v.get("pending")]
    seen_keys = set()
    todo = []
    for i in pending + [i for i in found if i["key"] not in known and i["source"] in ("bazos", "ulovdomov")]:
        if i["key"] not in seen_keys:
            seen_keys.add(i["key"]); todo.append(i)
    if not first_run:
        for i in todo[:MAX_DETAILS]:
            if i["source"] == "bazos":
                bazos_detail(i)
            elif not (i["source"] == "ulovdomov" and ud_first and i["key"] not in store):
                ulovdomov_contact(i)
        log(f"[bazos] načteno detailů: {min(len(todo), MAX_DETAILS)}, čeká na příští běh: {max(0, len(todo) - MAX_DETAILS)}")
    seller_counts = {}
    for v in list(store.values()) + [i for i in found if i["key"] not in store]:
        sid = v.get("seller_id") or (v.get("seller") or "").lower()
        if sid:
            seller_counts[sid] = seller_counts.get(sid, 0) + 1
        if v.get("phone"):
            ph = "tel:" + _norm_phone(v["phone"])
            seller_counts[ph] = seller_counts.get(ph, 0) + 1

    pool = dict(store)                           # pro hledání duplicit i v rámci jednoho běhu

    def settle(i):
        """Zařadí inzerát; bez jména prodávajícího ho nechá čekat (max. 3 běhy)."""
        no_detail = (i["source"] == "bazos" and not i.get("seller")) or \
                    (i["source"] == "ulovdomov" and i.get("ud_private") is None and not i.get("ud_external"))
        if i["source"] == "ulovdomov" and ud_first and i["key"] not in store:
            i["seller_type"], i["seller_reason"], i["silent"], i["pending"] = "nejiste", "první načtení zdroje", True, False
            return
        if no_detail and not first_run:
            i["tries"] = i.get("tries", 0) + 1
            if i["tries"] < 3:
                i["pending"] = True
                return
            i["seller_type"], i["seller_reason"], i["silent"] = "nejiste", "nepodařilo se načíst prodávajícího", True
        else:
            i["seller_type"], i["seller_reason"] = classify(i, seller_counts)
        i["pending"] = False
        i.pop("desc_full", None)
        dup = find_duplicate(i, pool)
        if dup:
            i["dup_of"], i["silent"] = dup, True
        pool[i["key"]] = i

    ready = []                                   # dřívější "pending", které se teď dořešily
    by_key = {i["key"]: i for i in todo}
    for v in pending:
        i = by_key.get(v["key"], v)
        settle(i)
        store[i["key"]] = {**store[i["key"]], **i}
        if not i.get("pending"):
            ready.append(store[i["key"]])
    for i in found:
        if i["key"] not in known:
            i.update(by_key.get(i["key"], {}))
            settle(i)
    now_iso = NOW.isoformat(timespec="seconds")
    new = []
    for i in found:
        if i["key"] in store:
            old = store[i["key"]]
            if i.get("price") and old.get("price") and i["price"] != old["price"]:
                i["price_prev"] = old["price"]
            i["first_seen"] = old["first_seen"]
            i["last_seen"] = now_iso
            store[i["key"]] = {**old, **{k: v for k, v in i.items() if v is not None}}
        else:
            i["first_seen"] = i["last_seen"] = now_iso
            store[i["key"]] = i
            new.append(i)

    cutoff = (NOW - timedelta(days=KEEP_DAYS)).isoformat()
    for k in [k for k, v in store.items() if v["last_seen"] < cutoff]:
        del store[k]

    data["updated"] = now_iso
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    log(f"Hotovo: nových {len(new)}, celkem {len(store)}")

    if not first_run:          # při prvním běhu nespamovat
        notify([i for i in new + ready if not i.get("pending") and not i.get("silent")])
    if not found:
        sys.exit("Nenačten žádný inzerát – zkontroluj log (blokace nebo změna webu).")


if __name__ == "__main__":
    main()
