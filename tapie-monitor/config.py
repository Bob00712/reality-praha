# -*- coding: utf-8 -*-
"""
=====================================================================
  TAPIE-MONITOR – VŠECHNA NASTAVENÍ NA JEDNOM MÍSTĚ
=====================================================================
Tady si můžeš sám upravovat filtry. Pravidla úprav:
  * text piš do uvozovek "takhle", položky odděluj čárkou,
  * řádek začínající # je jen poznámka (program ho ignoruje),
  * po úpravě na GitHubu klikni "Commit changes" – změna platí od
    příštího běhu.
Když si nejsi jistý, změň jen čísla nebo přidej/uber slova v seznamech.
"""

# ---------------------------------------------------------------
# 1) SPOLEČNÉ
# ---------------------------------------------------------------
MODULE_FIRMA_ENABLED = True      # Modul 1: insolvence firem
MODULE_APP_ENABLED = True        # Modul 2: upadající aplikace
MODULE_DIGITAL_ENABLED = True    # Modul 3: upadající digitální byznys v EU (à la Bending Spoons)

# DIGITAL – AAA jen když zpráva uvádí konkrétní velikost:
DIGITAL_MIN_USERS = 10_000       # aspoň tolik uživatelů/zákazníků …
DIGITAL_MAX_USERS = 20_000_000   # … ale ne globální gigant
DIGITAL_MAX_STAFF = 300          # nebo 10–300 zaměstnanců
DIGITAL_NEWS_DAYS = 14           # jak daleko zpět číst zprávy
DIGITAL_MIN_REVENUE = 1_000_000  # nebo tržby/ARR 1–100 mil. (EUR/USD)
DIGITAL_MAX_REVENUE = 100_000_000
DIGITAL_TECH_SITES = True        # číst i TechCrunch, Sifted, tech.eu, EU-Startups, t3n, Maddyness…
DIGITAL_LAYOFFS_ARE_STRONG = True  # propouštění = signál, že se nedaří (nejen insolvence)

# Posílat JEN případy, které sedí ve všech třech kritériích (známka AAA):
#  FIRMA: typ řízení (konkurs/reorganizace/Sanierung/Eigenverwaltung…) +
#         obor A/B/C (známý) + velikost 10–150 zaměstnanců (známá)
#  APP:   silný signál (propad/prodej/ukončení) + jazyky/vzdělávání +
#         velká základna (APP_AAA_MIN_RATINGS hodnocení)
ONLY_AAA = True
ANALYSIS_ENABLED = True   # ke každému případu potenciál, rizika, doporučení
APP_AAA_MIN_RATINGS = 10_000    # "hodně používaná" = aspoň tolik hodnocení (v EU obchodě, kde je v žebříčku)
APP_MIN_AVG_RATING = 3.0        # průměrné hodnocení pod tím = rozbitá/mrtvá appka → vynechat
APP_REQUIRE_FOCUS = False       # False = obor aplikace je jedno (jen ne hry/krypto)
# Horní hranice: aplikace s víc hodnoceními jsou globální giganti (ChatGPT, Outlook…),
# které nikdo neprodá – to nejsou příležitosti.
APP_MAX_RATINGS = 3_000_000
# Zprávy (Google News) samy případ NEVYTVOŘÍ – jen doplní kontext k aplikaci,
# která skutečně padá v žebříčku. (Párování zpráv na aplikace podle jména
# dávalo nesmysly typu ChatGPT, Outlook, SmartThings.)
APP_NEWS_CREATE_CASES = False
# Vlastníci, kteří aplikace neprodávají (big tech, média, banky, státní instituce).
# Porovnává se s vývojářem/prodejcem v App Store (malými písmeny, stačí část).
APP_OWNER_BLACKLIST = [
    "apple", "google", "microsoft", "meta platforms", "facebook", "instagram", "whatsapp",
    "amazon", "samsung", "openai", "anthropic", "bytedance", "tiktok", "tencent", "alibaba",
    "netflix", "spotify", "uber", "lyft", "airbnb", "snap inc", "x corp", "twitter",
    "pinterest", "linkedin", "paypal", "ebay", "walmart", "target corporation", "disney",
    "warner", "hbo", "paramount", "comcast", "nbcuniversal", "verizon", "at&t", "t-mobile",
    "united states postal", "usps", "adobe", "yahoo", "zoom", "salesforce", "oracle", "ibm",
    "intuit", "sony", "nintendo", "huawei", "xiaomi", "temu", "shein", "pdd", "booking.com",
    "expedia", "starbucks", "mcdonald", "dropbox", "duolingo", "roblox", "discord", "reddit",
    "telegram", "signal messenger", "nike", "ikea", "bank", "government", "ministry",
    "block, inc", "square, inc", "cash app", "robinhood", "coinbase", "binance",
    # státní a veřejné instituce, velká média a koncerny (neprodávají)
    "institut", "instituut", "ministère", "ministerie", "ministerium", "ministero",
    "france travail", "pôle emploi", "bundesamt", "bundesagentur", "agence", "agency",
    "agentur", "université", "university", "universität", "gemeente", "kommune",
    "stadt", "ville de", "comune", "ayuntamiento", "région", "regione", "landkreis",
    "bending spoons", "evernote", "zepp", "huami", "axel springer", "ringier",
    "aviv group", "schibsted", "adevinta", "mediaset", "rai", "orf", "zdf", "ard",
    "bbc", "deutsche bahn", "sncf", "trenitalia", "renfe", "öbb", "deutsche post",
    "la poste", "telekom", "orange", "vodafone", "telefónica", "allianz", "axa",
    "volkswagen", "bmw", "mercedes", "stellantis", "lidl", "aldi", "carrefour",
]
APP_NEWS_MAX_AGE_DAYS = 14      # zprávy o aplikacích: jak daleko zpět hledat

WEEKLY_SUMMARY_WEEKDAY = 0       # 0 = pondělí (souhrn týdne)
MAX_MESSAGES_PER_RUN = 25        # pojistka proti zahlcení Telegramu
SHOW_RATING_C = True             # False = posílat jen A a B

# Hodnocení: body -> známka (viz README, kapitola "Jak se hodnotí")
# FIRMA: max. 11 bodů. A = sedí řízení + obor + velikost (známá).
RATING_A_MIN = 9
RATING_B_MIN = 8
# APP: max. ~10 bodů.
APP_RATING_A_MIN = 8
APP_RATING_B_MIN = 6

# ---------------------------------------------------------------
# 2) MODUL FIRMA – velikost
# ---------------------------------------------------------------
EMPLOYEES_MIN = 10
EMPLOYEES_MAX = 150
LIABILITIES_MAX_EUR = 20_000_000
# True = firmu, o které VÍME, že je mimo rozsah zaměstnanců, vůbec
# neposílat. Když údaj chybí ("?"), firma se pošle vždy.
DROP_IF_SIZE_KNOWN_OUT_OF_RANGE = True
# True = firmu, jejíž HLAVNÍ obor známe a není v kategoriích A/B/C ani e-shop,
# neposílat (lékárny, doprava, agentury práce…). Neznámý obor "?" se pošle.
DROP_OTHER_FIELDS = True

# ---------------------------------------------------------------
# 3) MODUL FIRMA – Česko (ISIR + ARES)
# ---------------------------------------------------------------
CZ_ENABLED = True
# Při úplně prvním spuštění projde program události ISIR za posledních
# N dní (aby nezačínal od nuly). Pak už jen nové.
CZ_BACKFILL_DAYS = 14
# Aby program znal dlužníky i u starších řízení (konkurs bývá prohlášen
# 1–3 měsíce po podání návrhu), při prvním běhu si načte i starší
# události – ale jen si je zapamatuje, neposílá je.
CZ_CACHE_BACKFILL_DAYS = 120
CZ_MAX_RUNTIME_MIN = 50   # když nestihne, pokračuje zítra tam, kde skončil

# Stav řízení, který chceme (porovnává se bez diakritiky, stačí část slova)
CZ_WANTED_STATES = {
    "KONKURS": "konkurs",
    "REORGAN": "reorganizace",
    "UPADEK": "úpadek (způsob řešení zatím neurčen)",
    "MORATOR": "moratorium (předstupeň reorganizace)",
}
# Body za typ řízení (víc = lepší)
CZ_STATE_POINTS = {"konkurs": 3, "reorganizace": 3,
                   "úpadek (způsob řešení zatím neurčen)": 2,
                   "moratorium (předstupeň reorganizace)": 2}

# Události, které znamenají PRODEJ Z MAJETKOVÉ PODSTATY (pošle se
# zvláštní upozornění u firmy, kterou už sledujeme)
CZ_SALE_KEYWORDS = ["zpeněž", "zpenez", "výběrové řízení", "vyberove rizeni",
                    "prodej", "dražb", "drazb", "nabídk", "nabidk"]

# ---------------------------------------------------------------
# 4) OBORY (CZ-NACE) – kategorie A / B / C a vyloučené obory
#    Stačí začátek kódu: "25" = celý oddíl 25, "2562" = jen CNC obrábění
# ---------------------------------------------------------------
NACE_CATEGORY_A = [  # výrobci s vlastním produktem, celoroční spotřební zboží
    "10", "11", "13", "14", "15", "16", "17", "18", "20", "21", "22",
    "23", "26", "27", "29", "30", "31", "32",
]
NACE_CATEGORY_B = [  # strojírenství, CNC, kovovýroba, tepelná technika
    "24", "25", "28", "33", "2521", "2530", "2562", "2811", "2821", "2825",
]
NACE_CATEGORY_C = [  # software a aplikace
    "62", "63", "582",
]
NACE_ESHOP = ["4791"]  # e-shopy / značky – jen výjimečné příležitosti
NACE_EXCLUDED = [      # NECHCI
    "55", "56",               # gastro, ubytování
    "41", "42", "43",         # stavebnictví
    "68",                     # nemovitosti
    "642", "701",             # holdingy, činnost vedení podniků
    "932", "0113", "0121",    # zábavní parky, sezónní zemědělství
]
CATEGORY_POINTS = {"A": 3, "B": 3, "C": 3, "E-SHOP": 1, "?": 1, "jiný obor": 0}

# Klíčová slova pro zprávy (AT/DE) a pro názvy firem bez NACE
KEYWORDS_CATEGORY = {
    "A": ["hersteller", "produktion", "erzeuger", "möbel", "moebel", "textil",
          "lebensmittel", "kosmetik", "spielwaren", "manufaktur", "brauerei",
          "výrob", "vyrob"],
    "B": ["maschinenbau", "cnc", "metall", "stahl", "zerspan", "dreherei",
          "fräs", "fraes", "blech", "schweiß", "schweiss", "gießerei",
          "giesserei", "wärmetechnik", "waermetechnik", "kessel", "turbin",
          "anlagenbau", "werkzeugbau", "strojír", "strojir", "kovo", "obráb"],
    "C": ["software", "app ", "apps", "it-dienstleist", "digital", "plattform",
          "saas", "start-up", "startup", "aplikac"],
    "E-SHOP": ["onlineshop", "online-shop", "e-commerce", "versandhandel",
               "e-shop", "marke "],
}
KEYWORDS_EXCLUDED = [
    "gastro", "restaurant", "hotel", "wirtshaus", "café", "cafe ", "bar ",
    "catering", "bäckerei-café", "skigebiet", "seilbahn", "freizeitpark",
    "baufirma", "bauunternehm", "baumeister", "hochbau", "tiefbau", "bauträger",
    "immobilien", "projektentwickl", "holding", "privatkonkurs",
    "schuldenregulierung", "privatinsolvenz", "verbraucherinsolvenz",
    "privatperson", "stavebn", "realit", "oddlužení", "oddluzeni",
]

# Slova, kvůli kterým se ČESKÁ firma vyřadí podle NÁZVU (holdingy, investice,
# nemovitosti, stavebnictví):
NAME_EXCLUDED_WORDS = [
    "holding", "invest", "capital", "development", "estate", "reality", "realit",
    "building", "stavb", "stavebn", "group s.r.o", "asset", "finance", "leasing",
    "restaurant", "bistro", "kavárna", "hotel", "pension", "penzion",
]

# ---------------------------------------------------------------
# 5) MODUL FIRMA – Rakousko a Bavorsko (náhrada přes zprávy)
#    Ediktsdatei a insolvenzbekanntmachungen.de NEJDOU legálně
#    automatizovat zdarma (viz README). Používáme proto Google News RSS:
#    KSV1870, AKV, Creditreform a regionální média o insolvencích firem
#    píšou téměř vždy, i s počtem zaměstnanců a správcem.
# ---------------------------------------------------------------
AT_ENABLED = True
AT_NEWS_QUERIES = [
    'Sanierungsverfahren eröffnet Dienstnehmer',
    'Sanierungsverfahren Eigenverwaltung Gläubigerschutzverband',
    'Konkursverfahren eröffnet Unternehmen Dienstnehmer KSV1870',
    'Insolvenz Masseverwalter Fortführung Unternehmen',
    'Insolvenz AKV Sanierungsplan Quote',
]
# Zpráva musí obsahovat něco rakouského (místo nebo rakouský odborný výraz):
AT_MARKERS = [
    "österreich", "oesterreich", "wien", "graz", "linz", "salzburg", "innsbruck",
    "klagenfurt", "villach", "st. pölten", "wels", "steyr", "dornbirn", "bregenz",
    "eisenstadt", "leoben", "krems", "wiener neustadt", "kärnten", "tirol",
    "vorarlberg", "steiermark", "niederösterreich", "oberösterreich", "burgenland",
    "ksv1870", "ksv 1870", "akv", "creditreform österreich", "masseverwalter",
    "sanierungsverfahren", "dienstnehmer", "landesgericht",
]
AT_PROCEDURES = {  # klíčové slovo -> typ řízení (a body)
    "sanierungsverfahren mit eigenverwaltung": ("Sanierungsverfahren (Eigenverwaltung)", 3),
    "sanierungsverfahren": ("Sanierungsverfahren", 3),
    "sanierungsplan": ("Sanierungsverfahren / Sanierungsplan", 3),
    "konkursverfahren": ("Konkurs", 3),
    "konkurs": ("Konkurs", 3),
    "insolvenz": ("insolvence (typ ?)", 1),
}

BAVARIA_ENABLED = True
BAVARIA_NEWS_QUERIES = [
    'Insolvenz Bayern Mitarbeiter Amtsgericht',
    'Insolvenzantrag Amtsgericht München Mitarbeiter',
    'Insolvenzantrag Amtsgericht Nürnberg Mitarbeiter',
    'Eigenverwaltung Bayern Unternehmen Investor',
    'Schutzschirmverfahren Bayern',
    'Insolvenzverwalter Investorensuche Bayern',
]
# Zpráva musí zmínit Bavorsko nebo bavorské místo/soud:
BAVARIA_PLACES = [
    "bayern", "bayerisch", "münchen", "muenchen", "nürnberg", "nuernberg",
    "augsburg", "regensburg", "ingolstadt", "würzburg", "wuerzburg", "fürth",
    "erlangen", "bamberg", "bayreuth", "landshut", "passau", "rosenheim",
    "kempten", "hof ", "coburg", "aschaffenburg", "schweinfurt", "weiden",
    "amberg", "straubing", "deggendorf", "memmingen", "neu-ulm", "ansbach",
    "traunstein", "weilheim", "wolfratshausen", "oberpfalz", "franken",
    "schwaben", "allgäu", "allgaeu",
]
DE_PROCEDURES = {
    "schutzschirm": ("Schutzschirmverfahren", 3),
    "eigenverwaltung": ("Eigenverwaltung", 3),
    "regelinsolvenz": ("Regelinsolvenz", 3),
    "insolvenzverfahren eröffnet": ("Regelinsolvenz", 3),
    "vorläufige insolvenzverwalt": ("Regelinsolvenz (vorläufige)", 2),
    "vorläufiger insolvenzverwalt": ("Regelinsolvenz (vorläufige)", 2),
    "insolvenzantrag": ("Insolvenzantrag (typ ?)", 2),
    "insolvenz": ("insolvence (typ ?)", 1),
}
NEWS_MAX_AGE_DAYS = 3   # starší zprávy ignorovat

# ---------------------------------------------------------------
# 6) MODUL APP – upadající aplikace
# ---------------------------------------------------------------
# App Store žebříčky (oficiální veřejné RSS od Apple). Země a kategorie:
# EU trh bez Bulharska, Rumunska a Polska (kódy obchodů App Store):
APP_COUNTRIES = ["de", "fr", "it", "es", "nl", "be", "at", "se", "dk", "fi", "ie", "pt",
                 "cz", "sk", "hu", "gr", "si", "hr", "lu", "ee", "lv", "lt", "cy", "mt"]
APP_GENRES = {          # číslo kategorie Apple -> název (10 kategorií = běh do ~15 min)
    6017: "Education",
    6012: "Lifestyle",
    6007: "Productivity",
    6024: "Shopping",
    6000: "Business",
    6013: "Health & Fitness",
    6008: "Photo & Video",
    6003: "Travel",
    # Utilities a Food & Drink vyřazeny (Bob 2.11.2026): baterky, QR čtečky, počasí
    # nemají hodnotu k převzetí; jídlo = gastro, které Bob nechce.
}
APP_CHART_LIMIT = 100
APP_HISTORY_DAYS = 30   # kolik dní historie pořadí si pamatovat
# Pokles v žebříčku: aplikace byla v posledních 30 dnech aspoň
# APP_MIN_DAYS_IN_TOP dní v TOP APP_TOP_RANK a teď je o víc než
# APP_DROP_POSITIONS míst níž (nebo z žebříčku vypadla na 7+ dní).
APP_TOP_RANK = 50
APP_MIN_DAYS_IN_TOP = 10
APP_DROP_POSITIONS = 50
APP_ABSENT_DAYS = 7
# Dlouho bez aktualizace u velké aplikace:
APP_STALE_MONTHS = 18
APP_MIN_RATINGS = 5_000        # spodní hranice pro známku B (počet hodnocení)
# Mrtvý produkt (Bob 2.11.2026, případ Apollo for Reddit): aplikace bez aktualizace
# déle než tolik měsíců se VYŘADÍ úplně – i když padá v žebříčku. Tím je vypnutý
# i samostatný signál „neaktualizuje se 18 měsíců“ (APP_STALE_SIGNAL).
APP_MAX_MONTHS_SINCE_UPDATE = 12
APP_STALE_SIGNAL = False
# Aplikace závislé na API cizí platformy (vlastník platformy jim může vypnout
# přístup – Reddit 2023, Twitter/X 2023). Vyřadí se, když:
#  a) název obsahuje jméno platformy (celé slovo), nebo
#  b) popis obsahuje typickou frázi neoficiálního klienta.
APP_PLATFORM_NAME_WORDS = [
    "reddit", "twitter", "tweet", "tweets", "instagram", "tiktok", "youtube",
    "snapchat", "pinterest", "facebook", "whatsapp", "telegram", "discord",
    "twitch", "spotify",
]
APP_PLATFORM_DESC_PHRASES = [
    "client for reddit", "reddit client", "app for reddit", "browse reddit",
    "client for twitter", "twitter client", "client for x", "unofficial client",
    "unofficial app", "third-party client", "third party client",
    "not affiliated with reddit", "not affiliated with twitter",
    "not affiliated with instagram", "not affiliated with meta",
    "not affiliated with tiktok", "not affiliated with youtube",
    "not affiliated with google", "not affiliated with spotify",
]

# Aplikace, které chceš hlídat vždy (název z App Store):
APP_WATCHLIST = [
    "Mondly", "Busuu", "Memrise", "Babbel", "Drops: Language learning",
    "Rosetta Stone", "Lingvist", "Beelinguapp", "Mango Languages",
    "Quizlet", "Photomath", "Elevate", "Blinkist",
]

APP_FOCUS_KEYWORDS = [  # zaměření (pro zprávy)
    "language", "learning", "edtech", "education", "tutoring", "app",
    "consumer", "e-commerce", "ecommerce", "shopify", "subscription",
    "fitness app", "productivity",
]
APP_EXCLUDED_KEYWORDS = [  # hry a krypto ignorovat
    "game", "gaming", "esports", "casino", "crypto", "bitcoin", "blockchain",
    "nft", "web3", "token", "defi", "games",
    # počasí ve více jazycích (i když je appka zařazená v jiné kategorii)
    "weather", "wetter", "météo", "meteo", "počasí", "pocasi", "počasie", "tiempo",
    "rain radar", "regenradar", "pluie", "pioggia", "väder", "vejret", "sää", "időjárás",
    "weer", "kachelmann", "windy",
    # zaměnitelné utility
    "flashlight", "taschenlampe", "lampe torche", "torcia", "linterna", "baterka",
    "qr code", "qr-code", "barcode", "qr scanner", "qr reader",
]
APP_EXCLUDED_GENRES = [  # celé kategorie, které nemají hodnotu k převzetí
    "Games", "Finance",          # hry, krypto/burzy
    "Weather",                   # počasí (Bob 2.11.2026) – data od cizích služeb, nulová loajalita
    "Utilities",                 # baterky, QR čtečky, ovladače – zaměnitelné, zdarma všude
    "Reference", "News",         # Bible, slovníky, zpravodajství – obsah nepatří vlastníkovi appky
    "Navigation",                # radary, mapy – závislé na datech třetích stran
    "Music",                     # rádia, streamy – licence k obsahu
    "Food & Drink",              # gastro
]

APP_NEWS_QUERIES = [
    '"language learning app" layoffs',
    '"language app" sale OR divest OR "strategic review"',
    'edtech app layoffs',
    'edtech "exploring a sale"',
    'app "shut down" OR "sunset" OR "discontinue" consumer app',
    'Pearson OR Chegg OR Coursera OR Duolingo OR Babbel app divest OR sale OR layoffs',
    '"consumer app" layoffs startup',
    'e-commerce tool app acquired OR "for sale" OR layoffs',
    'app "strategic alternatives"',
    'popular app "shutting down" OR "will shut down"',
    'app maker layoffs OR "lays off"',
    'app "acquired by" OR "agreed to sell" consumer',
    'company "sells" app OR "divests" app',
    'subscription app "for sale" OR "exploring sale"',
]
APP_NEWS_SIGNALS = {   # slovo ve zprávě -> signál (a body)
    "for sale": ("vlastník prodává", 3),
    "exploring a sale": ("vlastník zvažuje prodej", 3),
    "strategic alternatives": ("vlastník zvažuje prodej", 3),
    "strategic review": ("strategická revize / možný prodej", 3),
    "divest": ("odprodej divize", 3),
    "sell ": ("vlastník prodává", 2),
    "shut down": ("ukončení produktu", 3),
    "shutting down": ("ukončení produktu", 3),
    "sunset": ("ukončení produktu", 3),
    "discontinu": ("ukončení produktu", 3),
    "layoff": ("propouštění", 2),
    "lays off": ("propouštění", 2),
    "laid off": ("propouštění", 2),
    "job cuts": ("propouštění", 2),
    "restructur": ("restrukturalizace", 2),
}
