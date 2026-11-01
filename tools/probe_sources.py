"""Jednorázový průzkum možných zdrojů inzerátů (robots.txt, úvodní stránka, odkazy na reality).
Výstup: docs/probe/sources/<doména>.txt. Nic neposílá do Telegramu."""
import re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"})
OUT = Path("docs/probe/sources"); OUT.mkdir(parents=True, exist_ok=True)
HINT = re.compile(r"byt|dum|dom|realit|nemovit|pronaj|prodej|rent|sale|flat|apartment|bydl", re.I)

def get(url):
    try:
        r = S.get(url, timeout=(10, 25), allow_redirects=True)
        return r.status_code, r.url, r.text
    except Exception as e:
        return 0, url, f"ERR {e}"

def probe(base, extra):
    host = urlparse(base).netloc
    lines = [f"# {base}  {time.strftime('%Y-%m-%d %H:%M')}"]
    st, fin, txt = get(urljoin(base, "/robots.txt"))
    lines += [f"## robots.txt {st} {fin}", txt[:4000] if st == 200 else txt[:300]]
    for url in [base] + extra:
        st, fin, html = get(url)
        lines.append(f"\n## GET {url} -> {st} {fin} ({len(html)} B)")
        if st != 200:
            lines.append(html[:300]); continue
        soup = BeautifulSoup(html, "lxml")
        lines.append("title: " + (soup.title.get_text(strip=True) if soup.title else "-"))
        links = []
        for a in soup.find_all("a", href=True):
            h = urljoin(fin, a["href"])
            t = a.get_text(" ", strip=True)[:60]
            if urlparse(h).netloc.endswith(host.replace("www.", "")) and (HINT.search(h) or HINT.search(t)):
                links.append(f"{t} | {h}")
        seen = list(dict.fromkeys(links))
        lines.append(f"odkazy ({len(seen)}):"); lines += seen[:80]
        txtall = soup.get_text(" ", strip=True)
        for w in ("soukrom", "majitel", "bez realitk", "RK", "makléř", "provize"):
            lines.append(f"výskyt '{w}': {txtall.count(w)}")
        if url != base:
            lines.append("--- text ---"); lines.append(txtall[:7000])
        time.sleep(2)
    (OUT / f"{host}.txt").write_text("\n".join(lines), "utf-8")
    print(host, "hotovo")

SOURCES = {
    "https://www.byty.cz/": ["https://www.byty.cz/byty-2-1-prodej/", "https://www.byty.cz/byty-2-1-pronajem/",
                             "https://www.byty.cz/podminky.aspx", "https://www.byty.cz/pro-realitky.aspx"],
    "https://www.reality.cz/": ["https://www.reality.cz/prodej/byty/Praha/", "https://www.reality.cz/pronajem/byty/Praha/",
                                "https://www.reality.cz/L00-007001/", "https://www.reality.cz/napoveda/"],
    "https://realitymix.cz/": ["https://realitymix.cz/reality/byty/prodej", "https://realitymix.cz/chci-prodat-pronajmout",
                               "https://realitymix.cz/detail/praha/pronajem-bytu-1-1-v-praze-ul-nuselska-8556969.html"],
    "https://www.expats.cz/": ["https://www.expats.cz/praguerealestate", "https://www.expats.cz/praguerealestate/apartments/for-rent"],
    "https://www.digireality.cz/": ["https://www.digireality.cz/byty", "https://www.digireality.cz/inzerat/698bda80641f2580ebee7271"],
}
if __name__ == "__main__":
    only = sys.argv[1:]
    for b, ex in SOURCES.items():
        if not only or any(o in b for o in only):
            probe(b, ex)
