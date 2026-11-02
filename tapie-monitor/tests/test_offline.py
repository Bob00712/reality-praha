# -*- coding: utf-8 -*-
"""Offline test celé logiky s falešnými odpověďmi zdrojů.
Spuštění:  python -m pytest -q tests   (nebo  python tests/test_offline.py)
"""
import json
import os
import sys
from datetime import timedelta
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common  # noqa: E402
from common import now_utc  # noqa: E402

NOW = now_utc()
D = NOW.strftime("%Y-%m-%dT%H:%M:%S")


def note(inner):
    return escape(f'<?xml version="1.0" encoding="UTF-8"?><ns2:udalost xmlns:ns2="http://x">{inner}</ns2:udalost>')


def ev(i, sz, desc, inner, doc=""):
    return (f"<data><id>{i}</id><datumZalozeniUdalosti>{D}</datumZalozeniUdalosti>"
            f"<datumZverejneniUdalosti>{D}</datumZverejneniUdalosti><dokumentUrl>{doc}</dokumentUrl>"
            f"<spisovaZnacka>{sz}</spisovaZnacka><typUdalosti>1</typUdalosti>"
            f"<popisUdalosti>{desc}</popisUdalosti><oddil>A</oddil><cisloVOddilu>1</cisloVOddilu>"
            f"<poznamka>{note(inner)}</poznamka></data>")


OSOBA = ("<osoba><idOsoby>X</idOsoby><druhRoleVRizeni>{role}</druhRoleVRizeni>"
         "<nazevOsoby>{name}</nazevOsoby><druhOsoby>{kind}</druhOsoby><ic>{ic}</ic>"
         "<adresa><mesto>Brno</mesto></adresa></osoba>")

EVENTS = [
    ev(101, "INS 100/2026", "Změna osoby", OSOBA.format(role="DLUŽNÍK", name="CNC Kovo s.r.o.", kind="P", ic="12345678")),
    ev(102, "INS 100/2026", "Změna osoby", OSOBA.format(role="SPRÁVCE", name="Mgr. Jan Správný", kind="SPRÁV_INS", ic="")),
    ev(103, "INS 100/2026", "Usnesení o prohlášení konkursu", "<vec><druhStavRizeni>KONKURS</druhStavRizeni></vec>"),
    ev(104, "INS 100/2026", "Oznámení o zpeněžení – výběrové řízení", "<vec><druhStavRizeni>KONKURS</druhStavRizeni></vec>", doc="https://isir.justice.cz/doc/1"),
    ev(105, "INS 200/2026", "Změna osoby", OSOBA.format(role="DLUŽNÍK", name="Pizzerie Roma s.r.o.", kind="P", ic="87654321")),
    ev(106, "INS 200/2026", "Rozhodnutí o úpadku", "<vec><druhStavRizeni>ÚPADEK</druhStavRizeni></vec>"),
    ev(107, "INS 300/2026", "Změna osoby", OSOBA.format(role="DLUŽNÍK", name="Jan Novák", kind="F", ic="")),
    ev(108, "INS 300/2026", "Prohlášení konkursu", "<vec><druhStavRizeni>KONKURS</druhStavRizeni></vec>"),
]


def soap(events):
    return ("<S:Envelope xmlns:S='http://schemas.xmlsoap.org/soap/envelope/'><S:Body>"
            "<ns2:getIsirWsPublicDataResponse xmlns:ns2='http://isirpublicws.cca.cz/types/'>"
            + "".join(events) + "<status><stav>OK</stav></status>"
            "</ns2:getIsirWsPublicDataResponse></S:Body></S:Envelope>").encode()


ARES = {
    "12345678": ({"obchodniJmeno": "CNC Kovo s.r.o.", "pravniForma": "112",
                  "sidlo": {"textovaAdresa": "Brno"}, "czNace": ["25620", "28410"]},
                 {"zaznamy": [{"czNacePrevazujici": "25620", "statistickeUdaje": {"kategoriePoctuPracovniku": "240"}}]}),
    "87654321": ({"obchodniJmeno": "Pizzerie Roma s.r.o.", "pravniForma": "112",
                  "czNace": ["56100"]}, {"zaznamy": [{"czNacePrevazujici": "56100"}]}),
}

RSS = """<rss><channel>
<item><title>Maschinenbau Huber GmbH: Sanierungsverfahren eröffnet, 85 Dienstnehmer betroffen - KSV1870</title>
<link>https://news.example/1</link><pubDate>{pub}</pubDate><source>KSV1870</source>
<description>Passiva von 4,2 Millionen Euro. Masseverwalter ist Rechtsanwalt Peter Maier.</description></item>
<item><title>Hotel Alpenblick: Konkurs eröffnet - ORF</title><link>https://news.example/2</link>
<pubDate>{pub}</pubDate><source>ORF</source><description></description></item>
<item><title>Metallbau Schmid GmbH aus Regensburg stellt Insolvenzantrag in Eigenverwaltung, 60 Mitarbeiter</title>
<link>https://news.example/3</link><pubDate>{pub}</pubDate><source>BR</source><description></description></item>
<item><title>LinguaPro language learning app owner exploring a sale after layoffs - TechCrunch</title>
<link>https://news.example/4</link><pubDate>{pub}</pubDate><source>TechCrunch</source><description></description></item>
<item><title>Pearson will shut down Mondly app next year - The Verge</title>
<link>https://news.example/6</link><pubDate>{pub}</pubDate><source>The Verge</source><description></description></item>
<item><title>Crypto game studio lays off staff</title><link>https://news.example/5</link>
<pubDate>{pub}</pubDate><source>X</source><description></description></item>
</channel></rss>"""


class Resp:
    def __init__(self, status=200, content=b"", js=None):
        self.status_code, self.content, self._js = status, content, js
        self.text = content.decode("utf-8", "ignore") if content else json.dumps(js)

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def fake_http(method, url, **kw):
    if "isir_public_ws" in url:
        after = int(kw["data"].decode().split("<idPodnetu>")[1].split("<")[0])
        evs = [e for e in EVENTS if int(e.split("<id>")[1].split("<")[0]) > after]
        return Resp(content=soap(evs))
    if "ares.gov.cz" in url:
        ico = url.rstrip("/").rsplit("/", 1)[-1]
        if ico not in ARES:
            return Resp(404, js={})
        return Resp(js=ARES[ico][1 if "-res/" in url else 0])
    if "news.google.com" in url:
        pub = NOW.strftime("%a, %d %b %Y %H:%M:%S GMT")
        return Resp(content=RSS.format(pub=pub).encode())
    if "itunes.apple.com" in url and "/rss/" in url:
        if "us/rss/topfreeapplications" in url and "6017" in url:
            entries = [{"id": {"attributes": {"im:id": "900"}}, "im:name": {"label": "Other"},
                        "im:artist": {"label": "x"}, "category": {"attributes": {"label": "Education"}}}]
            return Resp(js={"feed": {"entry": entries}})
        return Resp(js={"feed": {}})
    if "itunes.apple.com/search" in url:
        mondly = {"trackId": 777, "trackName": "Mondly", "sellerName": "Pearson", "artistName": "ATi Studios",
                  "userRatingCount": 150000, "primaryGenreName": "Education",
                  "trackViewUrl": "https://apps.apple.com/app/id777"}
        return Resp(js={"results": [mondly]} if "Mondly" in url else {"results": []})
    if "itunes.apple.com/lookup" in url:
        old = (NOW - timedelta(days=500)).strftime("%Y-%m-%dT00:00:00Z")
        return Resp(js={"results": [
            {"trackId": 777, "trackName": "Mondly", "sellerName": "Pearson", "artistName": "ATi Studios",
             "sellerUrl": "https://mondly.com", "userRatingCount": 150000, "primaryGenreName": "Education",
             "currentVersionReleaseDate": old, "trackViewUrl": "https://apps.apple.com/app/id777",
             "averageUserRating": 4.6, "description": "Learn languages"},
            {"trackId": 900, "trackName": "Other", "sellerName": "x", "userRatingCount": 10,
             "primaryGenreName": "Education", "currentVersionReleaseDate": NOW.isoformat()},
        ]})
    if any(d in url for d in ("techcrunch.com/feed", "sifted.eu", "tech.eu", "eu-startups", "siliconcanals",
                              "trendingtopics", "deutsche-startups", "t3n.de", "maddyness", "startupitalia",
                              "czechcrunch")):
        if "techcrunch" in url:
            pub = NOW.strftime("%a, %d %b %Y %H:%M:%S GMT")
            return Resp(content=f"""<rss><channel><item><title>Berlin-based FitPlan struggles, cuts 30 of its 80 employees</title>
<link>https://techcrunch.com/x</link><pubDate>{pub}</pubDate>
<description>The fitness app with 400,000 users is exploring a sale.</description></item>
<item><title>US startup Foo lays off staff</title><link>https://techcrunch.com/y</link><pubDate>{pub}</pubDate>
<description>San Francisco based app with 50,000 users.</description></item></channel></rss>""".encode())
        return Resp(404, content=b"")
    if "rss.applemarketingtools.com" in url:
        return Resp(js={"feed": {"results": []}})
    raise AssertionError("neočekávaná URL " + url)


def test_full_run(tmp_path, monkeypatch=None):
    import monitor
    from sources import isir, ares, news, apps, digital
    for mod in (isir, ares, news, apps, digital):
        setattr(mod, "http", fake_http)
    isir.find_start_id = lambda days: 100
    apps.CHART_PAUSE = apps.LOOKUP_PAUSE = 0
    common.STATE_FILE = tmp_path / "state.json"
    common.CASES_FILE = tmp_path / "cases.json"
    monitor.STATE_FILE, monitor.CASES_FILE = common.STATE_FILE, common.CASES_FILE
    sent = []
    monitor.telegram_send = lambda text: sent.append(text) or True
    os.environ.pop("TELEGRAM_TOKEN", None)
    import config
    config.WEEKLY_DIGEST = False   # 1. část: denní režim
    sys.argv = ["monitor.py"]
    monitor.main()
    allt = "\n".join(sent)
    print(allt)
    assert "CNC Kovo" in allt and "Jan Správný" in allt
    assert "PRODEJ Z MAJETKOVÉ PODSTATY" in allt
    assert "Pizzerie" not in allt and "Novák" not in allt
    assert "Maschinenbau Huber" in allt and "Peter Maier" in allt
    assert "Hotel Alpenblick" not in allt
    assert "Metallbau Schmid" in allt
    # jen AAA: aplikace bez známé velikosti / jen bez aktualizace neprojdou
    assert "LinguaPro" not in allt and "Crypto" not in allt
    assert "FitPlan" in allt and "[DIGITAL] AAA" in allt and "Foo lays off" not in allt
    assert "[APP]" not in allt  # zprávy samy případ nevytvoří, propad v žebříčku zatím není
    from sources.apps import big_owner
    assert big_owner({"sellerName": "Samsung Electronics Co., Ltd."})
    assert big_owner({"sellerName": "OpenAI OpCo, LLC"})
    assert not big_owner({"sellerName": "Pineapple Studio s.r.o."})
    # 2.11.2026: mrtvé aplikace a klienti cizích platforem (Apollo for Reddit) ven
    from sources.apps import platform_dependent, dead_product
    assert platform_dependent({"trackName": "Apollo for Reddit"})
    assert platform_dependent({"trackName": "Narwhal 2", "description": "The best client for Reddit."})
    assert not platform_dependent({"trackName": "Mondly", "description": "Learn languages"})
    assert not platform_dependent({"trackName": "Canva", "description": "Make posts for Instagram"})
    assert dead_product({"currentVersionReleaseDate": "2023-11-28T00:00:00Z"})
    assert not dead_product({"currentVersionReleaseDate": NOW.isoformat()})
    assert "[FIRMA] AAA" in allt and "Business potenciál" in allt and "Rizika" in allt
    from common import split_message
    long = "\n".join(f'[X] A · <a href="https://x/{i}">odkaz</a>' for i in range(400))
    for part in split_message(long):
        assert part.count("<a ") == part.count("</a>") and len(part) <= 3800
    assert all("[FIRMA]" in s or "[APP]" in s or "[DIGITAL]" in s for s in sent[1:] if "Souhrn" not in s)

    # druhý běh: žádné duplicity
    sent.clear()
    monitor.main()
    assert not [s for s in sent if "Souhrn týdne" not in s], sent  # nic nového = žádná zpráva

    # 2. část: týdenní režim + případ typu Smala (správce hledá kupce, blízký termín)
    config.WEEKLY_DIGEST = True
    from datetime import timedelta as _td
    soon = NOW + _td(days=4)
    later = NOW + _td(days=30)
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"]
    def d(x):
        return f"{x.day} {months[x.month - 1]} {x.year}"
    smala_rss = f"""<rss><channel>
<item><title>Kidzy en redressement judiciaire : la plateforme de seconde main cherche un repreneur</title>
<link>https://news.example/s1</link><pubDate>{NOW.strftime("%a, %d %b %Y %H:%M:%S GMT")}</pubDate>
<description>Offres de reprise jusqu'au {d(soon)} : marque, site internet, clients.</description></item>
<item><title>ModaBox en redressement judiciaire, la marque e-commerce cherche un repreneur</title>
<link>https://news.example/s2</link><pubDate>{NOW.strftime("%a, %d %b %Y %H:%M:%S GMT")}</pubDate>
<description>Dépôt des offres jusqu'au {d(later)}.</description></item>
</channel></rss>"""
    orig = news.http
    def fake2(method, url, **kw):
        if "news.google.com" in url and "hl=fr" in url:
            return Resp(content=smala_rss.encode())
        return orig(method, url, **kw)
    news.http = fake2
    sent.clear()
    monitor.main()
    allt = "\n".join(sent)
    assert "Kidzy" in allt and "ModaBox" not in allt, allt   # urgentní hned, druhý čeká
    st = json.load(open(common.STATE_FILE))
    assert any("ModaBox" in c["name"] for c in st["pending"])
    sent.clear()
    monitor.weekly_digest(st, [])
    allt = "\n".join(sent)
    assert "týdenní přehled" in allt and "ModaBox" in allt and st["pending"] == []


if __name__ == "__main__":
    import tempfile
    test_full_run(Path(tempfile.mkdtemp()))
    print("\nOK")
