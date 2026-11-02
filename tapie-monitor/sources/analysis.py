# -*- coding: utf-8 -*-
"""Rychlé analytické hodnocení případu (business potenciál, rizika, doporučení).

Pravidlová šablona podle typu řízení, země, oboru a velikosti – strukturovaná
jako první screening transakčního poradce (deal screening memo). Nenahrazuje
due diligence; údaje vycházejí jen z veřejných zdrojů uvedených u případu.
"""

ROUTE = {
    "konkurs": ("Asset deal od insolvenčního správce (prodej závodu nebo jeho části "
                "mimo dražbu, §§ 283–295 IZ). Kupující nepřebírá dluhy dlužníka.", 3),
    "reorganizace": ("Vstup jako investor do reorganizačního plánu (úpis kapitálu / "
                     "úvěr / koupě závodu v rámci plánu) – nutný souhlas věřitelů.", 2),
    "sanierungsverfahren": ("Investor do Sanierungsplanu (kvóta min. 20 %, s Eigenverwaltung "
                            "30 %) nebo koupě podniku od Masseverwalter.", 2),
    "konkurs_at": ("Koupě podniku/majetku od Masseverwalter (Unternehmensverkauf), "
                   "bez převzetí dluhů.", 3),
    "eigenverwaltung": ("Vstup investora přes Insolvenzplan nebo M&A proces řízený "
                        "Sachwalterem (übertragende Sanierung = asset deal bez dluhů).", 2),
    "schutzschirm": ("Investor do Insolvenzplanu v ochranném řízení – rychlé, ale "
                     "konkurence strategických kupců.", 2),
    "regelinsolvenz": ("Übertragende Sanierung – koupě aktiv od Insolvenzverwalter, "
                       "bez dluhů; rychlý proces (typicky 2–4 měsíce).", 3),
}

SECTOR = {
    "A": ("Vlastní produkt a značka – hodnota v receptuře/designu, distribučních "
          "kontraktech a zákaznické bázi; marže lze obnovit opravou nákladů a pracovního kapitálu.",
          "Ověř, zda značka/ochranné známky a e-shop/doménu vlastní dlužník (často na spřízněné osobě)."),
    "B": ("Strojní park, know-how a certifikace (ISO 9001, EN 1090, příp. AS/EN 9100) – "
          "aktiva typicky prodávaná pod reprodukční hodnotou; potenciál jako subdodavatel "
          "pro výrobce plynových turbín a energetiku.",
          "Ověř stáří a zástavy strojů (leasing = nevlastní je), vlastnictví hal "
          "a odchod klíčových techniků/programátorů CNC."),
    "C": ("Software/IP a tým – nízká kapitálová náročnost, rychlá integrace; hodnota "
          "v opakovaných příjmech (SaaS/servisní smlouvy) a zdrojovém kódu.",
          "Ověř vlastnictví zdrojového kódu a licencí (často u dodavatelů/freelancerů) "
          "a riziko odchodu vývojářů – bez týmu hodnota rychle mizí."),
}


def _route_key(c):
    p = (c.get("procedure") or "").lower()
    if c.get("country") == "AT":
        if "sanierung" in p:
            return "sanierungsverfahren"
        return "konkurs_at"
    if c.get("country") == "DE":
        for k in ("schutzschirm", "eigenverwaltung"):
            if k in p:
                return k
        return "regelinsolvenz"
    return "reorganizace" if "reorgan" in p else "konkurs"


def analyze_firma(c):
    route, speed = ROUTE[_route_key(c)]
    cat = c.get("cat", "?")
    pot_sector, risk_sector = SECTOR.get(cat, ("", ""))
    potential = [route]
    if pot_sector:
        potential.append(pot_sector)
    emp = c.get("employees")
    if emp:
        size = f"{emp[0]}" if emp[0] == emp[1] else f"{emp[0]}–{emp[1]}"
        potential.append(f"Velikost {size} zaměstnanců: zvládnutelná integrace, "
                         "cena typicky v řádu jednotek až nižších desítek mil. Kč za aktiva.")
    if c.get("update", "").startswith("PRODEJ"):
        potential.insert(0, "Správce právě vyhlásil zpeněžení – okno pro nabídku je OTEVŘENÉ.")
    risks = []
    if c.get("country") == "CZ":
        risks.append("Při koupi celého závodu přecházejí zaměstnanci (§ 338 ZP) včetně "
                     "nároků z pracovněprávních vztahů vzniklých po převodu – spočítej mzdy.")
    risks.append("Odchod klíčových zákazníků a dodavatelů během řízení – ověř backlog "
                 "zakázek a smlouvy s change-of-control klauzulemi.")
    if risk_sector:
        risks.append(risk_sector)
    risks.append("Ekologické zátěže a vady areálu se kupujícímu nepromíjí – ověř "
                 "vlastnictví pozemků, nájemní smlouvy a povolení.")
    if c.get("liabilities", "?").startswith("?"):
        risks.append("Výše závazků neznámá – rozsah přihlášek pohledávek napoví, "
                     "jak tvrdě bude správce vyjednávat o ceně.")
    verdict = ("PRIORITA: kontaktovat správce do 48 h, vyžádat soupis majetkové podstaty "
               "a podmínky prodeje; NDA + data room." if speed == 3 else
               "SLEDOVAT: kontaktovat dlužníka/správce, zjistit stav plánu a hlasování "
               "věřitelů; připravit indikativní nabídku investice.")
    return potential, risks, verdict


def analyze_app(c):
    sig = (c.get("procedure") or "").lower()
    potential = []
    if any(k in sig for k in ("prodej", "prodává", "odprodej", "revize")):
        potential.append("Vlastník aktivně zvažuje exit – carve-out bývá levnější než "
                         "akvizice celé firmy a prodávající ocení rychlost a jistotu.")
    if "pokles" in sig or "vypadla" in sig:
        potential.append("Propad v žebříčku při zachované uživatelské bázi = typicky problém "
                         "produktu/marketingu, ne poptávky; obrat lze řešit re-launchem.")
    if "aktualizace" in sig:
        potential.append("Aplikace bez vývoje, ale s velkou bází – vlastník ji nejspíš "
                         "neprioritizuje; vhodné pro nabídku na odkup aktiv (kód, značka, uživatelé).")
    potential.append(f"Uživatelská základna: {c.get('size')}. Monetizace přes předplatné "
                     "lze obnovit (paywall, cenové testy, ASO).")
    risks = [
        "Hodnota je v týmu a kódu – ověř technický dluh, licence třetích stran a "
        "závislost na platformě vlastníka (účty, SSO, backend).",
        "Převod uživatelských dat podléhá GDPR – nutný právní titul pro předání.",
        "Klesající aktivní uživatelé (DAU/MAU) mohou být horší než počet hodnocení – "
        "vyžádej metriky z App Store Connect / Google Play Console.",
    ]
    verdict = ("PRIORITA: oslovit Corporate Development vlastníka s neformálním dotazem "
               "na odkup aktiv; vyžádat MAU, MRR, churn." if "prodej" in sig or "exit" in sig
               else "SLEDOVAT: první neformální kontakt s vlastníkem, zjistit ochotu prodat.")
    return potential, risks, verdict


def analyze_symbolic(c):
    potential = [
        "Převzetí za symbolickou cenu (Tapie style): kupec neplatí za firmu, ale převezme provoz, "
        "zaměstnance a závazek ji stabilizovat – hodnota je v obratu, zákaznících, značce a týmu.",
        "Páky obratu: okamžitě zastavit ztrátové činnosti, vyjednat se správcem/věřiteli odpis "
        "nebo splátkový kalendář, prodat nepotřebná aktiva, sjednotit nákup a ceny.",
    ]
    risks = [
        "Symbolická cena ≠ levný obchod: převezmeš ztrátový provoz – spočítej hotovost na 6–12 měsíců "
        "(mzdy, nájmy, dodavatelé) a podmínky převodu zaměstnanců.",
        "Ověř, co přesně přechází: share deal (i se skrytými dluhy!) vs. asset deal (bez dluhů) – "
        "Tapie trval na tom, že dluhy nepřebírá; trvej na asset dealu nebo zárukách prodávajícího.",
        "Prodávající (koncern/správce) často chce závazky: zachování míst, investice – smluvní pokuty.",
        "Data ze zprávy nejsou ověřená – vyžádej výsledovku, cash-flow a seznam závazků.",
    ]
    verdict = ("PRIORITA: kontaktovat prodávajícího/správce, vyžádat informační memorandum a podmínky "
               "(co přesně přechází, závazky kupce, termín); připravit 100denní plán obratu.")
    return potential, risks, verdict


def analyze_digital(c):
    sig = (c.get("procedure") or "").lower()
    insolv = any(k in sig for k in ("insolv", "redressement", "liquidation", "faillis", "failliet",
                                    "concorso", "concordato", "fallimento", "concurso", "administrat"))
    potential = []
    if insolv:
        potential.append("Prodej z insolvence (asset deal: značka, doména, kód, uživatelská báze) "
                         "bez převzetí dluhů – správce typicky preferuje rychlost a jistotu plnění.")
    else:
        potential.append("Vlastník hledá kupce/ukončuje produkt – prostor pro levný carve-out aktiv.")
    potential.append(f"Velikost: {c.get('size')}. Model Bending Spoons: zeštíhlit náklady (cloud, tým), "
                     "zavést/zdražit předplatné, centralizovat vývoj – marže lze zvednout rychle.")
    risks = [
        "Převod osobních údajů uživatelů (GDPR) – nutný právní titul a informování uživatelů.",
        "Hodnota je v týmu/kódu – ověř, kdo vlastní IP, technický dluh a závislosti na dodavatelích.",
        "Uživatelé po oznámení insolvence rychle odcházejí – čas hraje proti hodnotě.",
        "Data ze zprávy nejsou ověřená – vyžádej metriky (MAU, MRR, churn) a účetní závěrky.",
    ]
    verdict = ("PRIORITA: kontaktovat správce/administrateur do 48 h, vyžádat teaser, data room "
               "a termín pro nabídky." if insolv else
               "SLEDOVAT: neformální kontakt s vlastníkem, zjistit ochotu prodat a metriky.")
    return potential, risks, verdict


def analyze(c):
    if "symbolickou cenu" in (c.get("procedure") or ""):
        return analyze_symbolic(c)
    if c.get("module") == "DIGITAL":
        return analyze_digital(c)
    return analyze_app(c) if c.get("module") == "APP" else analyze_firma(c)


def format_analysis(c):
    from html import escape
    potential, risks, verdict = analyze(c)
    potential = [escape(p, quote=False) for p in potential]
    risks = [escape(r, quote=False) for r in risks]
    verdict = escape(verdict, quote=False)
    lines = ["", "📈 <b>Business potenciál</b>"] + [f"• {p}" for p in potential]
    lines += ["⚠️ <b>Rizika</b>"] + [f"• {r}" for r in risks]
    lines += [f"🎯 <b>Doporučení:</b> {verdict}"]
    return "\n".join(lines)
