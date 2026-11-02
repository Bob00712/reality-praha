# Tapie-monitor – hlídač příležitostí k převzetí

Každé ráno (cca 5:23 v zimě, 6:23 v létě) projde zdroje a pošle do Telegramu **jen nové** případy:

- **[FIRMA]** – firmy v insolvenci (ČR, Rakousko, Bavorsko), kde jde koupit firmu nebo majetek
  od správce nebo vstoupit do reorganizace / Sanierungsplanu. Dluhy se nepřebírají.
- **[APP]** – aplikace, které upadají (propad v žebříčcích, dlouho bez aktualizace, propouštění,
  ukončení produktu, vlastník chce prodávat).

Každé pondělí přijde navíc **souhrn týdne** seřazený podle hodnocení A → B → C.
Všechny filtry jsou v jednom souboru: **`config.py`**.

---

## Zprovoznění
Hlídač běží v repozitáři **reality-praha** (složka `tapie-monitor/`). Do Telegramu posílá
do **vlastního kanálu** (nemíchá se s realitami):

1. V Telegramu: tužka ✏️ → **Nový kanál** → název např. *Tapie příležitosti* → Soukromý.
2. V kanálu: **Správci → Přidat správce →** najdi svého bota (stejného jako u realit) → potvrď.
3. Napiš do kanálu jakoukoliv zprávu (např. „start“).
4. GitHub: **Actions → tapie-monitor → Run workflow**, mode `chats`. V logu kroku
   „Spustit monitor“ najdi řádek `[telegram] CHAT -100… | channel | Tapie příležitosti`.
5. **Settings → Secrets and variables → Actions → New repository secret:**
   název `TAPIE_TELEGRAM_CHAT_ID`, hodnota to číslo (včetně mínusu).
   (Volitelně vlastní bot: secret `TAPIE_TELEGRAM_TOKEN`.)

Dokud `TAPIE_TELEGRAM_CHAT_ID` chybí, do Telegramu se nic neposílá (a nic se neoznačí
jako odeslané).

- **Zkouška:** Actions → *tapie-monitor* → *Run workflow* → mode `test`.
  Do Telegramu přijde „✅ spojení funguje“.
- **Ostrý běh hned:** totéž s `normal`. První běh trvá déle (až ~50 min, načítá ISIR zpětně).
- Jinak běží samo každé ráno.

---

## Co znamenají zprávy

```
[FIRMA] A · CNC Kovo s.r.o.
🇨🇿 Země: CZ
⚖️ Řízení: konkurs
🏭 Obor: B – strojírenství / kovovýroba / tepelná technika (NACE 25620)
👥 Velikost: 50–99 zaměstnanců
💶 Závazky: ?
📇 Správce: Mgr. Jan Novák, Brno – insolvenční správce
🔗 otevřít zdroj
```
- `?` = údaj ve zdroji chybí. **Případ se kvůli tomu nevyřazuje.**
- **[FIRMA] … PRODEJ Z MAJETKOVÉ PODSTATY** – u firmy, kterou už hlídáš, se v ISIR objevilo
  zpeněžení / výběrové řízení. To je ten okamžik, kdy jde koupit majetek nebo celý závod.
- **ZMĚNA: úpadek → konkurs** – firma, kterou jsi už dostal, přešla do konkursu/reorganizace.

### Jak se hodnotí (A / B / C)
Body se sčítají; hranice jsou v `config.py` (`RATING_A_MIN = 7`, `RATING_B_MIN = 4`).

| Co | Body |
|---|---|
| Typ řízení: konkurs / reorganizace / Sanierungsverfahren / Eigenverwaltung / Schutzschirm | 3 |
| Úpadek, moratorium, insolvenční návrh (typ ještě neurčen) | 2 |
| Obor A, B nebo C | 3 · neznámý obor `?` 1 · e-shop 1 (e-shop max. B) |
| Zaměstnanci 10–150 | 3 · částečně v rozsahu 2 · neznámo `?` 1 |
| Závazky do 20 mil. EUR | 2 · neznámo `?` 1 |

**[APP] AAA** = aplikace je v žebříčku App Store (tedy používaná) a zároveň (a) výrazně padá v pořadí
nebo (b) ji vlastník přes 18 měsíců neaktualizuje; má 100 000 – 3 000 000 hodnocení; vlastník není big tech,
banka, médium ani stát (`APP_OWNER_BLACKLIST`); nejde o hru ani krypto. Zprávy z Google News případ samy
nevytvoří – jen se k padající aplikaci dohledají jako kontext.

**Vyřazuje se:** gastro, ubytování, stavebnictví, nemovitosti, holdingy, sezónní byznys,
fyzické osoby (oddlužení), hry, krypto. A firmy, o kterých *víme*, že mají méně než 10
nebo víc než 150 zaměstnanců (vypneš `DROP_IF_SIZE_KNOWN_OUT_OF_RANGE = False`).

---

## Zdroje – co jde automatizovat a co ne

| Zdroj | Stav | Poznámka |
|---|---|---|
| **ISIR** (CZ insolvenční rejstřík) | ✅ automaticky | Oficiální veřejná webová služba MSp *IsirWsPublicService*, zdarma, bez registrace, určená ke strojovému čtení. |
| **ARES** (CZ-NACE, počet zaměstnanců) | ✅ automaticky | Oficiální REST API Ministerstva financí, zdarma. |
| **AT Ediktsdatei** | ❌ ne přímo → ✅ náhrada | Strojové převzetí dat je dovoleno jen s **licencí IWG** od rakouského Ministerstva spravedlnosti (žádost e-mailem na IWG-Antrag@bmj.gv.at, BMJ uvádí poplatek cca 90 € + měsíční poplatek). Web proto nestahuji. **Náhrada:** zprávy KSV1870 / AKV / Creditreform a médií přes Google News RSS (téměř vždy uvádějí počet zaměstnanců, pasiva i správce). Když budeš chtít oficiální data, požádej o licenci – připojení doprogramuju. |
| **DE insolvenzbekanntmachungen.de** (Bavorsko) | ❌ ne → ✅ náhrada | Portál nemá API, podle vyhlášky InsBekV §2 je chráněný proti hromadnému kopírování a vyhledávání je záměrně omezené. **Náhrada:** zprávy (BR, Süddeutsche, Merkur, nordbayern, JUVE, tiskové zprávy správců Pluta, Schultze & Braun, Anchor…) přes Google News RSS, filtrováno na bavorská místa a soudy. Ruční kontrola: [insolvenzbekanntmachungen.de](https://neu.insolvenzbekanntmachungen.de/). |
| **App Store** žebříčky + detail aplikace | ✅ automaticky | Veřejné RSS žebříčky Apple a iTunes Search/Lookup API (vlastník, web vývojáře, počet hodnocení, datum poslední aktualizace). Propad se pozná po ~10 dnech sbírání historie. |
| **Google Play** | ❌ ne | Nemá veřejné API, stahování webu porušuje podmínky. Většina významných aplikací je i v App Store, takže pokrytí je dostatečné. |
| **Google News RSS** (propouštění, ukončení, prodej) | ✅ jen jako kontext | U aplikací jen doplní zprávu k aplikaci, která už padá v žebříčku (párování zpráv podle jména dávalo nesmysly). |
| **layoffs.fyi** | ❌ ne → ✅ náhrada | Nemá API (data v Airtable), automatické stahování není povoleno. Stejné zprávy chytá Google News RSS. |
| **Acquire.com, Flippa** | ❌ ne → 📧 náhrada | Podmínky zakazují automatické stahování, Acquire.com navíc vyžaduje přihlášení. **Náhrada:** založ si tam účet a ulož hledání s e-mailovým upozorněním (filtr: *Education / Consumer / SaaS / E-commerce*, *Revenue > 0*, *min. 10 000 uživatelů nebo $5k MRR*). Nabídky pak chodí e-mailem. |

---

## Úpravy filtrů (`config.py`)
Na GitHubu otevři `config.py` → tužka ✏️ (Edit) → uprav → **Commit changes**.
Nejčastější úpravy:
- `EMPLOYEES_MIN`, `EMPLOYEES_MAX`, `LIABILITIES_MAX_EUR` – velikost firem.
- `NACE_CATEGORY_A/B/C`, `NACE_EXCLUDED` – obory (kódy CZ-NACE, stačí začátek).
- `KEYWORDS_CATEGORY`, `KEYWORDS_EXCLUDED` – slova pro rakouské a bavorské zprávy.
- `APP_WATCHLIST` – aplikace, které chceš hlídat vždy (např. Mondly).
- `APP_COUNTRIES`, `APP_GENRES` – země a kategorie App Store.
- `SHOW_RATING_C = False` – posílat jen A a B.

Čas spuštění změníš v `.github/workflows/tapie-monitor.yml` (v kořeni repozitáře) (řádek `cron`, čas je v UTC).

## Když něco nefunguje
**Actions → poslední běh → krok „Spustit monitor“.** Řádky `[isir]`, `[AT]`, `[DE-Bayern]`,
`[app]` ukazují, kolik se toho načetlo. Když zdroj selže, ranní zpráva obsahuje
„⚠️ Zdroje s chybou dnes“. Ostatní zdroje běží dál.

Stav (co už bylo posláno) je v `data/state.json` a `data/cases.json`. Když je smažeš,
monitor začne od nuly.

## Pro technicky zdatné
- `python monitor.py --test | --weekly | --only firma|app`
- Offline test bez internetu: `python tests/test_offline.py`
