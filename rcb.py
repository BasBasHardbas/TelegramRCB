import json, os, re, sys
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Warsaw")
except Exception:
    TZ = None

DRY = "--dry" in sys.argv
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
LIST_URL = "https://www.gov.pl/web/rcb/komunikaty"
STATE = "state.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TITLE_RE = re.compile(r"alert rcb.*\((\d{1,2})\.(\d{1,2})\)", re.I)
REGION_RE = re.compile(r"podkarpack|lubelsk", re.I)
REGION_NAMES = {"podkarpack": "podkarpackie", "lubelsk": "lubelskie"}
CANCEL_RE = re.compile(r"odwoła|odwołan|zakończ|ustał|minęło|wygaszon", re.I)
NOISE_RE = re.compile(r"odsłon|wyświetle|drukuj|udostępnij|data publikacji|ostatnia aktualizacja", re.I)


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def send(text):
    text = text[:3800]
    if DRY:
        print("--- TELEGRAM (dry run) ---\n" + text + "\n")
        return True
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )
    return r.ok


def todays_articles(today):
    found = {}
    for a in get(LIST_URL).select("a[href]"):
        title = a.get_text(" ", strip=True)
        m = TITLE_RE.search(title)
        if m and (int(m.group(1)), int(m.group(2))) == (today.day, today.month):
            found[urljoin(LIST_URL, a["href"])] = title
    return found


def article_lines(soup):
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    root = (soup.select_one("#main-content") or soup.select_one("main")
            or soup.select_one("article") or soup.body or soup)
    lines = [l.strip() for l in root.get_text("\n").split("\n")]
    return [l for l in lines if l and not NOISE_RE.search(l)]


def main():
    if not DRY and not (TOKEN and CHAT_ID):
        sys.exit("Brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID")

    today = datetime.now(TZ)
    day = f"{today.day:02d}.{today.month:02d}"
    state = {}
    if os.path.exists(STATE):
        state = json.load(open(STATE, encoding="utf-8"))

    articles = todays_articles(today)
    if DRY:
        print(f"Dziś: {day}, znalezione artykuły: {len(articles)}")

    for link, title in articles.items():
        try:
            lines = article_lines(get(link))
        except Exception as e:
            print("Błąd pobierania", link, e)
            continue
        if not lines:
            continue

        old = state.get(link, {"lines": [], "notified": False})
        old_set = set(old["lines"])
        new = [l for l in lines if l not in old_set]
        full = " ".join(lines)
        regions = sorted({REGION_NAMES.get(m.lower(), m.lower())
                          for m in REGION_RE.findall(full)})
        notified = old["notified"]

        if DRY:
            print(f"\n=== {title}\n{link}")
            print("Regiony w treści:", regions or "brak")
            print("Odwołanie w treści:", bool(CANCEL_RE.search(full)))
            print("Treść artykułu (pierwsze 40 linijek):")
            for l in lines[:40]:
                print("  |", l)

        if new and (notified or regions):
            cancel = bool(CANCEL_RE.search(" ".join(new)))
            if cancel:
                header = "✅ Odwołanie / zakończenie"
            elif notified:
                header = "🔄 Aktualizacja"
            else:
                header = "⚠️ Nowy alert"
            msg = f"{header}\n{title}\n"
            if regions:
                msg += f"Dotyczy: {', '.join(regions)}\n"
            msg += "\n" + "\n".join("• " + l for l in new[:15]) + f"\n\n{link}"
            if not send(msg):
                continue            # nie zapisuj stanu, spróbuje ponownie
            notified = True

        state[link] = {"day": day, "lines": lines, "notified": notified}

    state = {k: v for k, v in state.items() if v.get("day") == day}
    if not DRY:
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
