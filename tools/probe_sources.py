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
        raw = url.startswith("raw:")
        url = url[4:] if raw else url
        st, fin, html = get(url)
        if raw and st == 200:
            (OUT / "html").mkdir(exist_ok=True)
            name = re.sub(r"[^\w.-]+", "_", url.split("//", 1)[1])[:120] + ".html"
            (OUT / "html" / name).write_text(html, "utf-8")
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
            lines.append("--- text ---"); lines.append(txtall[:30000] if 'podmin' in url or 'terms' in url or 'legal' in url else txtall[:7000])
        time.sleep(2)
    (OUT / f"{host}.txt").write_text("\n".join(lines), "utf-8")
    print(host, "hotovo")

SOURCES = {
    "https://www.expats.cz/": ["https://www.expats.cz/czech-news/article/expats-terms"],
    "https://www.realcity.cz/": [],
    "https://www.ireality.cz/": [],
    "https://www.realitni-inzerce.cz/": [],
    "https://www.sousede.cz/": [],
}
if __name__ == "__main__":
    only = sys.argv[1:]
    for b, ex in SOURCES.items():
        if not only or any(o in b for o in only):
            probe(b, ex)
