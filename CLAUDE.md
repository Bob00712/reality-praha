# reality-praha – hlídač inzerátů od soukromníků (Bazoš → Telegram)

## Pro koho a jak komunikovat
- Majitel: Bob (Robert Harman), realitní makléř (Dominius reality). **Netechnický uživatel.**
- Odpovídej česky, stručně a prakticky. Změny dělej sám přímo v repu (commit do `main`), ne návodem „stáhni a nahraj".
- Po každé změně ověř, že běh v GitHub Actions doběhl ✅ (log kroku „Run python scraper.py").

## Co to dělá
Každých 15 minut stáhne nové inzeráty (byty, domy, pozemky bez polí a lesů, chaty, garáže; v Praze a Středočeském kraji vše od 5 mil.) z **Bazoš.cz**,
vyřadí realitky a poptávky a **soukromníky pošle do Telegramu**. Cílem je, aby Bob oslovil majitele dřív než ostatní RK.

## Jak to běží
- **GitHub Actions** (`.github/workflows/scrape.yml`): `python scraper.py`, pak uloží `docs/` zpět do repa.
  - `timeout-minutes: 10`, `concurrency: scrape`.
  - Ukládání má smyčku: při odmítnutém push udělá `fetch` + `reset --hard origin/main` + `python scraper.py --merge /tmp/ours.json`
    (sloučí `data.json`, aby se nic neztratilo ani neposlalo dvakrát) a zkusí to znovu (max. 5×).
  - V yml je i `schedule: cron "7,37 * * * *"`, ale GitHub plánované běhy u free účtu vynechává.
- **Hlavní spouštěč je cron-job.org** (účet Boba), každých 15 min:
  `POST https://api.github.com/repos/Bob00712/reality-praha/actions/workflows/scrape.yml/dispatches`, body `{"ref":"main"}`,
  hlavička `Authorization: Bearer <fine-grained PAT>` (jen tohle repo, Actions: read & write).
  **Token vyprší 5. 10. 2027** – pak vygenerovat nový a vyměnit v cron-job.org.
- **Secrets** v repu: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` (může obsahovat víc ID oddělených čárkou → pošle se všem).
  Tokeny nikdy nepiš do souborů ani logů.
- Neběží-li to: Actions → poslední běh → log. „Re-run" starých běhů nepoužívat (berou starou verzi yml) – spouštět přes *Run workflow*.

## Soubory
- `scraper.py` – vše (stahování, filtr RK, duplicity, Telegram, merge). Nastavení je nahoře v souboru.
- `docs/data.json` – stav: `{"updated", "listings": {key: {...}}}`, klíč např. `bazos:225446795`. Drží se 30 dní (`KEEP_DAYS`).
- `docs/probe/` – ladicí výstupy (vzorky stránek/odpovědí). Lze promazat.
- `docs/index.html` – webový přehled nad `data.json` (GitHub Pages **není zapnuté**, Bob ho nepoužívá).
- `requirements.txt` – requests, beautifulsoup4, lxml.

## Zdroje
- **Bazoš (jediný aktivní)**: `reality.bazos.cz/{prodam|pronajmu}/{rubrika}/{offset}/` s `hlokalita=11000&humkreis=70`
  (40 inzerátů/str., offset po 40). Jedno velké hledání na rubriku (`BAZOS_SEARCHES`), pak filtr podle PSČ (`near`):
  - rubriky: byt, dum, garaz (prodej i pronájem), pozemek, chata (jen prodej).
  - pozemky: **pole, louky, lesy, zemědělská půda se vyřazují** (`FIELD_RE`), pokud nejde o stavební / k bydlení (`BUILD_RE`) – Bob je nechce.
  - posílá se Praha (PSČ `1xx xx`) + `NEAR_PSC` = první 3 číslice PSČ (poštovní obvod ≈ obec + ~10 km): Brandýs, Úvaly,
    Čelákovice, Odolena Voda, Klecany, Zdiby (250), Říčany… (251), Praha-západ obce (252), Hostivice (253), Benešov (256/257),
    Dobříš (263), Beroun (266/267), Kladno, Unhošť (272/273), Slaný (274), Mělník (276), Neratovice (277), Kralupy (278),
    Kolín (280/281), Nymburk, Lysá n. L. (288/289).
  - **drahé**: `/prodam/` přes všechny rubriky, `cenaod=5000000`, okruh 90 km, Praha + Středočeský kraj (PSČ 25x–29x) – `expensive`.
    Typ se u nich odhaduje z titulku (`guess_typ`), jinak „jiná nemovitost".
  - Změna schématu hledání (`SCHEME` v `data.json`) → první běh jen uloží (`first_load`), nic nepošle.
  - Detail inzerátu (`bazos_detail`) dává jméno prodávajícího, celý popis, `seller_id` (idphone).
  - Inzeráty bez načteného jména čekají (`pending`, max. 3 běhy), pak se tiše zahodí – nikdy se neposílají bez posouzení.
  - Poptávky (titulek začíná Hledám/Koupím/Poptávám/Sháním) se přeskakují – Bob je nechce.
- **UlovDomov**: implementováno, ale **vypnuto** (`UD_ENABLED = False`) – Bob: skoro samé realitky.
  API `ud.api.ulovdomov.cz/v1/offer/find` (POST, bounds Prahy), kontakt `www.ulovdomov.cz/fe-api/offer/contact-info/{id}` (`is_private_landlord`).
- **Zamítnuté zdroje (neřešit znovu)**: Sbazar a Bezrealitky (robots.txt zakazuje), Sreality (podmínky), Realingo (zakazuje detaily/API),
  iDNES Reality (100 % realitky), Hyperinzerce (téměř nulový objem), Bazar.cz (nemá nemovitosti), Facebook (zákaz scrapingu – neobcházet).
  - Průzkum 11/2026 (`tools/probe_sources.py`, workflow `probe-sources`, ruční spuštění): **byty.cz** (podmínky výslovně zakazují
    scraping), **Avizo, Annonce, ceskereality.cz, Digireality, RealCity** (ochrana proti botům – neobcházet), **Eurobydlení**
    (robots.txt zakazuje ClaudeBot), **Expats.cz** (soukromých jen pár, podmínky zakazují kopírování), **reality.cz, RealityMix**
    (téměř jen RK), iReality/realitni-inzerce (mrtvé domény), Sousedé.cz (není inzerce).

## Filtr realitek (`classify` → `rk` / `soukromy` / `nejiste`)
Posílá se jen `soukromy` a `nejiste` (`SELLER_FILTER = "rk_ven"`). Vyřadí se jako RK, pokud:
- jméno je na seznamu `RK_SELLERS` (Bobův seznam – M&M, Paschke, HVB, Finpos, Next Reality, ZOOM, Bohemian Estates, Ideální nájemce,
  Dumrealit, Ladislav Burian/REALBrána, Pavelková, Jiří Beneš…; navíc `RK_SELLER_IDS` = Bazoš idphone nahlášených RK, chytí je i pod jiným jménem; když Bob nahlásí další, přidej sem),
- jméno obsahuje firmu (`Jméno - Firma`, čárku, s.r.o./spol., `…Real/Reality/Estate/Invest`, `REAL…`),
- text obsahuje `NO_RK_WORDS` („RK nevolat" apod. – Bob tyto majitele nechce oslovovat),
- text obsahuje silné RK výrazy (`RK_WORDS`: provize, makléř, zprostředkuje, výhradní zastoupení, ID nabídky, ev. č., …webrealit.cz…),
- stejný prodávající/telefon má ≥ 3 inzeráty (`RK_MIN_LISTINGS`), nebo byl dříve vyřazen (paměť `RK_KNOWN`, `RK_PHONES`).
Slabé znaky (`RK_WEAK`: „nabízíme k pronájmu", samotné „RK", „exkluzivní") inzerát nevyřadí, jen označí ❔.
Priorita Boba: **raději občas propustit realitku, než přijít o soukromníka.**

## Duplicity
`find_duplicate`: stejný typ+akce, dispozice, plocha ±1 m², cena ±2 %, stejná čtvrť/obec (nebo stejný telefon) z jiného zdroje → neposílat.

## Telegram zpráva
HTML: titulek, cena, dispozice/m²/Kč/m²/lokalita/zdroj, 👤 jméno, 📞 telefon (pokud je),
odkazy „Otevřít inzerát · 📲 WhatsApp" (odkaz na Google Bob nechce) (wa.me s předvyplněnou zprávou `WA_TEXT`,
varianty pronájem/prodej, byt/dům). Max. 15 samostatných zpráv na běh, zbytek souhrnem.
Je-li v textu inzerátu e-mail, zpráva ukáže ✉️ adresu + text e-mailu v `<code>` (klepnutím se zkopíruje; Telegram `mailto:` odkazy nebere).
Automatické odesílání WhatsApp zpráv ani e-mailů **nedělat** (ban čísla, nevyžádaná obchodní sdělení) – jen předvyplněný odkaz, Bob odesílá sám.

## Rozhodnuto (neřešit znovu)
- **Telefon z Bazoše se nezískává** – Bazoš číslo nevydává (ad-phone.php vrací 200 bez čísla). Bob: nezkoušet.
  `bazos_phone` jen vezme `tel:` odkaz, pokud je přímo ve stránce, a `idphone` jako `seller_id` – žádné další požadavky.
- Podpis ve `WA_TEXT` je „Robert Harman" – správně, neměnit. Jiné příjmení nikde nepoužívat.

## Otevřené body
1. `daily_rk_digest` (denní souhrn vyřazených) existuje, ale je vypnutý – Bob nechtěl víc zpráv.
2. `docs/probe/` a staré probe funkce lze uklidit.
