# reality-praha – hlídač inzerátů od soukromníků (Bazoš → Telegram)

## Pro koho a jak komunikovat
- Majitel: Bob (Robert Harman), realitní makléř (Dominius reality). **Netechnický uživatel.**
- Odpovídej česky, stručně a prakticky. Změny dělej sám přímo v repu (commit do `main`), ne návodem „stáhni a nahraj".
- Po každé změně ověř, že běh v GitHub Actions doběhl ✅ (log kroku „Run python scraper.py").

## Co to dělá
Každých 15 minut stáhne nové inzeráty bytů a domů (prodej i pronájem) z **Bazoš.cz** v Praze a 22 obcích kolem,
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
- **Bazoš (jediný aktivní)**: `reality.bazos.cz/{prodam|pronajmu}/{byt|dum}/` s `hlokalita=<PSČ>&humkreis=<km>`.
  - Praha: PSČ 11000, 15 km + filtr PSČ `1xx xx`, až `MAX_PAGES` stránek.
  - `BAZOS_LOCATIONS`: Beroun, Benešov, Úvaly, Kralupy n. Vlt., Neratovice, Brandýs n. L., Říčany, Průhonice, Jesenice, Černošice,
    Rudná, Roztoky, Klecany, Odolena Voda, Hostivice, Čelákovice, Mnichovice, Strančice, Mníšek p. Brdy, Dobřichovice, Řevnice, Kladno
    – vše 5 km, `LOC_PAGES = 1`. Radotín je součást Prahy.
  - Nová lokalita se při prvním načtení jen uloží (`first_load`, nic se nepošle).
  - Detail inzerátu (`bazos_detail`) dává jméno prodávajícího, celý popis, `seller_id` (idphone).
  - Inzeráty bez načteného jména čekají (`pending`, max. 3 běhy), pak se tiše zahodí – nikdy se neposílají bez posouzení.
  - Poptávky (titulek začíná Hledám/Koupím/Poptávám/Sháním) se přeskakují – Bob je nechce.
- **UlovDomov**: implementováno, ale **vypnuto** (`UD_ENABLED = False`) – Bob: skoro samé realitky.
  API `ud.api.ulovdomov.cz/v1/offer/find` (POST, bounds Prahy), kontakt `www.ulovdomov.cz/fe-api/offer/contact-info/{id}` (`is_private_landlord`).
- **Zamítnuté zdroje (neřešit znovu)**: Sbazar a Bezrealitky (robots.txt zakazuje), Sreality (podmínky), Realingo (zakazuje detaily/API),
  iDNES Reality (100 % realitky), Hyperinzerce (téměř nulový objem), Bazar.cz (nemá nemovitosti), Facebook (zákaz scrapingu – neobcházet).

## Filtr realitek (`classify` → `rk` / `soukromy` / `nejiste`)
Posílá se jen `soukromy` a `nejiste` (`SELLER_FILTER = "rk_ven"`). Vyřadí se jako RK, pokud:
- jméno je na seznamu `RK_SELLERS` (Bobův seznam – M&M, Paschke, HVB, Finpos, Next Reality, ZOOM, Bohemian Estates, Ideální nájemce,
  Dumrealit, Ladislav Burian/REALBrána…; když Bob nahlásí další, přidej sem),
- jméno obsahuje firmu (`Jméno - Firma`, čárku, s.r.o./spol., `…Real/Reality/Estate/Invest`, `REAL…`),
- text obsahuje `NO_RK_WORDS` („RK nevolat" apod. – Bob tyto majitele nechce oslovovat),
- text obsahuje silné RK výrazy (`RK_WORDS`: provize, makléř, zprostředkuje, ID nabídky, ev. č., …webrealit.cz…),
- stejný prodávající/telefon má ≥ 3 inzeráty (`RK_MIN_LISTINGS`), nebo byl dříve vyřazen (paměť `RK_KNOWN`, `RK_PHONES`).
Slabé znaky (`RK_WEAK`: „nabízíme k pronájmu", samotné „RK", „exkluzivní") inzerát nevyřadí, jen označí ❔.
Priorita Boba: **raději občas propustit realitku, než přijít o soukromníka.**

## Duplicity
`find_duplicate`: stejný typ+akce, dispozice, plocha ±1 m², cena ±2 %, stejná čtvrť/obec (nebo stejný telefon) z jiného zdroje → neposílat.

## Telegram zpráva
HTML: titulek, cena, dispozice/m²/Kč/m²/lokalita/zdroj, 👤 jméno, 📞 telefon (pokud je),
odkazy „Otevřít inzerát · 🔎 Google (hledá jen telefon, jinak jméno) · 📲 WhatsApp" (wa.me s předvyplněnou zprávou `WA_TEXT`,
varianty pronájem/prodej, byt/dům). Max. 15 samostatných zpráv na běh, zbytek souhrnem.
Automatické odesílání WhatsApp zpráv **nedělat** (ban čísla, nevyžádaná obchodní sdělení) – jen předvyplněný odkaz, Bob odesílá sám.

## Rozhodnuto (neřešit znovu)
- **Telefon z Bazoše se nezískává** – Bazoš číslo nevydává (ad-phone.php vrací 200 bez čísla). Bob: nezkoušet.
  `bazos_phone` jen vezme `tel:` odkaz, pokud je přímo ve stránce, a `idphone` jako `seller_id` – žádné další požadavky.
- Podpis ve `WA_TEXT` je „Robert Harman" – správně, neměnit. Jiné příjmení nikde nepoužívat.

## Otevřené body
1. `daily_rk_digest` (denní souhrn vyřazených) existuje, ale je vypnutý – Bob nechtěl víc zpráv.
2. `docs/probe/` a staré probe funkce lze uklidit.
