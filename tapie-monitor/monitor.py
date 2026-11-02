# -*- coding: utf-8 -*-
"""TAPIE-MONITOR – hlavní program. Spouští ho GitHub Actions 1× denně.

  python monitor.py            běžný denní běh (v pondělí i týdenní souhrn)
  python monitor.py --test     jen pošle zkušební zprávu do Telegramu
  python monitor.py --weekly   pošle týdenní souhrn hned
  python monitor.py --only firma|app
"""
import argparse
import json
import html
import sys
import traceback
from datetime import timedelta

import config
from common import (CASES_FILE, STATE_FILE, esc, format_case, load_json, log, now_utc,
                    save_json, telegram_send, today)

ORDER = {"A": 0, "B": 1, "C": 2}


def collect(state, seen, fps, only=None):
    cases, errors = [], []

    def safe(label, fn):
        try:
            res = fn()
            cases.extend(res)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            errors.append(f"{label}: {e}"[:200])

    if config.MODULE_FIRMA_ENABLED and only in (None, "firma"):
        if config.CZ_ENABLED:
            from sources import isir
            safe("ČR ISIR", lambda: isir.run(state, seen))
        from sources import at_de
        safe("AT/DE zprávy", lambda: at_de.run(seen, fps))
    if config.MODULE_APP_ENABLED and only in (None, "app"):
        from sources import apps
        safe("App Store", lambda: apps.run_charts(state, seen))
        safe("APP zprávy", lambda: apps.run_news(seen, fps))
    if getattr(config, "MODULE_DIGITAL_ENABLED", False) and only in (None, "digital"):
        from sources import digital
        safe("DIGITAL zprávy", lambda: digital.run(seen, fps))
    return cases, errors


def send_daily(cases, errors):
    if config.ONLY_AAA:
        dropped = [c for c in cases if c.get("grades") != "AAA"]
        cases = [c for c in cases if c.get("grades") == "AAA"]
        log(f"[filtr] AAA: {len(cases)}, nevyhovělo: {len(dropped)}")
        if not cases:
            log("[telegram] žádný AAA případ – nic se neposílá")
            return []
    if not config.SHOW_RATING_C:
        cases = [c for c in cases if c["rating"] != "C"]
    cases.sort(key=lambda c: (ORDER.get(c["rating"], 3), c["module"], -c.get("points", 0)))
    n_f = sum(c["module"] == "FIRMA" for c in cases)
    n_a = len(cases) - n_f
    head = f"☀️ <b>Tapie-monitor {today()}</b>\nNové: {len(cases)} (FIRMA {n_f}, APP {n_a})"
    if errors:
        head += "\n⚠️ Zdroje s chybou dnes: " + "; ".join(esc(e) for e in errors)
    if not cases:
        telegram_send(head + "\nDnes nic nového.")
        return []
    sent = []
    if not telegram_send(head):
        return []
    detailed = cases[: config.MAX_MESSAGES_PER_RUN]
    for c in detailed:
        if telegram_send(format_case(c)):
            sent.append(c)
    rest = cases[config.MAX_MESSAGES_PER_RUN:]
    if rest:
        lines = [f"➕ <b>Další {len(rest)} případů (zkráceně)</b>"]
        for c in rest:
            link = f' – <a href="{html.escape(c["link"])}">odkaz</a>' if c.get("link") else ""
            lines.append(f"[{c['module']}] {c['rating']} · {esc(c['name'])} · {esc(c.get('procedure'))}{link}")
        if telegram_send("\n".join(lines)):
            sent.extend(rest)
    return sent


def weekly_summary(log_cases):
    since = (now_utc() - timedelta(days=7)).strftime("%Y-%m-%d")
    week = [c for c in log_cases if c.get("date", "") >= since]
    week = [c for c in week if ":sale:" not in (c.get("key") or "")]
    if config.ONLY_AAA:
        week = [c for c in week if c.get("grades") == "AAA"]
    week.sort(key=lambda c: (ORDER.get(c["rating"], 3), c["module"], c["name"]))
    lines = [f"📊 <b>Souhrn týdne (od {since})</b> – {len(week)} případů"]
    if not week:
        lines.append("Tento týden nic nového.")
    cur = None
    for c in week:
        if c["rating"] != cur:
            cur = c["rating"]
            lines.append(f"\n<b>Hodnocení {'AAA' if config.ONLY_AAA else cur}</b>")
        link = f' – <a href="{html.escape(c["link"])}">odkaz</a>' if c.get("link") else ""
        lines.append(f"[{c['module']}] {esc(c['name'])} ({esc(c.get('country'))}) · "
                     f"{esc(c.get('procedure'))} · {esc(c.get('size'))}{link}")
    telegram_send("\n".join(lines))


def merge_state(our_state_path, our_cases_path):
    """Souběžný běh uložil stav dřív než my – spoj oba, ať se nic nepošle dvakrát."""
    theirs = load_json(STATE_FILE, {})
    ours = load_json(our_state_path, {})
    seen = theirs.setdefault("seen", {})
    for k, v in ours.get("seen", {}).items():
        seen.setdefault(k, v)
    fps = {json.dumps(f, sort_keys=True): f for f in theirs.get("fps", []) + ours.get("fps", [])}
    theirs["fps"] = list(fps.values())
    ti, oi = theirs.setdefault("isir", {}), ours.get("isir", {})
    if oi.get("last_id", 0) > ti.get("last_id", 0):
        ti["last_id"] = oi["last_id"]
    for sz, c in oi.get("cases", {}).items():
        ti.setdefault("cases", {}).setdefault(sz, c)
    if ours.get("apps", {}).get("best_day", "") >= theirs.get("apps", {}).get("best_day", ""):
        theirs["apps"] = ours.get("apps", theirs.get("apps", {}))
    theirs["weekly_sent"] = max(theirs.get("weekly_sent", ""), ours.get("weekly_sent", ""))
    for k, v in ours.items():
        theirs.setdefault(k, v)
    cases = load_json(CASES_FILE, [])
    have = {(c.get("key"), c.get("date")) for c in cases}
    cases += [c for c in load_json(our_cases_path, []) if (c.get("key"), c.get("date")) not in have]
    save_json(STATE_FILE, theirs)
    save_json(CASES_FILE, cases)
    log(f"[merge] sloučeno: {len(seen)} odeslaných klíčů, {len(cases)} případů v logu")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--chats", action="store_true")
    ap.add_argument("--merge", nargs=2, metavar=("OUR_STATE", "OUR_CASES"),
                    help="sloučí náš stav do novějšího stavu z repa (po souběžném běhu)")
    ap.add_argument("--only", choices=["firma", "app", "digital"])
    args = ap.parse_args()

    if args.merge:
        merge_state(*args.merge)
        return
    if args.chats:
        from common import telegram_find_chats
        telegram_find_chats()
        return
    if args.test:
        ok = telegram_send("✅ Tapie-monitor: spojení s Telegramem funguje.")
        sys.exit(0 if ok else 1)

    state = load_json(STATE_FILE, {})
    log_cases = load_json(CASES_FILE, [])
    if args.weekly:
        weekly_summary(log_cases)
        return

    seen = state.setdefault("seen", {})
    fp_store = state.setdefault("fps", [])
    cutoff = (now_utc() - timedelta(days=21)).strftime("%Y-%m-%d")
    fp_store[:] = [f for f in fp_store if f.get("d", "") >= cutoff]
    fps = [f["fp"] for f in fp_store]

    cases, errors = collect(state, seen, fps, args.only)
    # odstranění duplicit v rámci jednoho běhu
    uniq = {}
    for c in cases:
        uniq.setdefault(c["key"], c)
    cases = list(uniq.values())

    # Aplikace jen 1× týdně (Bob 2.11.2026): denně se neposílají, jen se zapíšou
    # do logu a přijdou v pondělním souhrnu týdne.
    queued = []
    if getattr(config, "APP_WEEKLY_ONLY", False):
        queued = [c for c in cases if c["module"] == "APP"
                  and (not config.ONLY_AAA or c.get("grades") == "AAA")]
        cases = [c for c in cases if c["module"] != "APP"]
        log(f"[app] {len(queued)} aplikací odloženo do týdenního souhrnu")
    sent = send_daily(cases, errors)
    t = today()
    for c in sent + queued:
        seen[c["key"]] = {"date": t, "stage": c.get("stage"), "rating": c["rating"]}
        if c.get("alias") and not c.get("update"):
            seen[c["alias"]] = seen[c["key"]]
        if c.get("fp"):
            fp_store.append({"d": t, "fp": c["fp"]})
        log_cases.append({k: c.get(k) for k in
                          ("key", "module", "name", "country", "procedure", "size",
                           "rating", "grades", "link")} | {"date": t})
    # případy, které jsme vyřadili jen kvůli SHOW_RATING_C, si také pamatujeme
    for c in cases:
        if c["key"] not in seen and c["rating"] == "C" and not config.SHOW_RATING_C:
            seen[c["key"]] = {"date": t, "stage": c.get("stage"), "rating": "C"}

    # úklid: pamatuj si klíče 400 dní, log 60 dní
    old = (now_utc() - timedelta(days=400)).strftime("%Y-%m-%d")
    for k in [k for k, v in seen.items() if v.get("date", "") < old]:
        del seen[k]
    log_cutoff = (now_utc() - timedelta(days=60)).strftime("%Y-%m-%d")
    log_cases = [c for c in log_cases if c.get("date", "") >= log_cutoff]

    # týdenní souhrn jen jednou za den (i když běh spustíme víckrát)
    if now_utc().weekday() == config.WEEKLY_SUMMARY_WEEKDAY and state.get("weekly_sent") != t:
        weekly_summary(log_cases)
        state["weekly_sent"] = t

    save_json(STATE_FILE, state)
    save_json(CASES_FILE, log_cases)
    log(f"[hotovo] odesláno {len(sent)} z {len(cases)}; chyby: {errors or 'žádné'}")


if __name__ == "__main__":
    main()
