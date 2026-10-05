# Nové reality Praha (Bazoš + Sbazar)

Každých 30 min stáhne nové inzeráty bytů a domů v Praze (prodej i pronájem),
uloží je do `docs/data.json` a zobrazí na webu přes GitHub Pages.

## Zprovoznění (cca 10 min)
1. Na GitHubu vytvoř nový repozitář a nahraj do něj obsah této složky (i skrytou složku `.github`).
2. **Settings → Actions → General → Workflow permissions** → zvol *Read and write permissions*.
3. **Settings → Pages** → Source: *Deploy from a branch*, branch `main`, složka `/docs`.
4. **Actions → scrape → Run workflow** (první ruční běh). Pak už to jede samo.
5. Web najdeš na `https://<tvuj-ucet>.github.io/<repo>/`.

## Sbazar
Otevři Sbazar v prohlížeči, vyfiltruj Praha + byty (domy) + prodej (pronájem),
zkopíruj URL a vlož do `SBAZAR_URLS` v `scraper.py`. Prázdná URL se přeskočí.

## Telegram notifikace (volitelné)
1. V Telegramu napiš @BotFather → /newbot → získáš token.
2. Napiš svému botovi cokoliv, pak otevři `https://api.telegram.org/bot<TOKEN>/getUpdates` a najdi `chat.id`.
3. **Settings → Secrets and variables → Actions**: přidej `TELEGRAM_TOKEN` a `TELEGRAM_CHAT_ID`.
4. Podmínky upozornění nastav v `NOTIFY` v `scraper.py` (cena, m², dispozice…).

## Když něco nefunguje
Actions → poslední běh → log kroku „Run python scraper.py“. Řádky `[bazos]` / `[sbazar]`
ukazují, kolik inzerátů se načetlo. 0 nebo CHYBA = změna webu nebo blokace.
