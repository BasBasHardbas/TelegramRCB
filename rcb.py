import json, os, re, requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
LIST_URL = "https://www.gov.pl/web/rcb"
STATE = "seen.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TITLE_RE = re.compile(r"alert rcb", re.I)
REGION_RE = re.compile(
    r"podkarpack|rzesz[oó]w|krosno|przemy[sś]l|tarnobrzeg|jaros[łl]aw|mielec|"
    r"sanok|stalowa wola|dębica|lubaczów|leżajsk|ropczyc|strzyżów|brzozów",
    re.I,
)

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )

def main():
    first_run = not os.path.exists(STATE)
    seen = set(json.load(open(STATE))) if not first_run else set()

    alerts = {}
    for a in get(LIST_URL).select("a[href]"):
        title = a.get_text(" ", strip=True)
        if TITLE_RE.search(title):
            alerts[urljoin(LIST_URL, a["href"])] = title

    for link, title in alerts.items():
        if link in seen:
            continue
        seen.add(link)
        if first_run:
            continue
        body = get(link).get_text(" ", strip=True)
        if REGION_RE.search(title) or REGION_RE.search(body):
            send(f"⚠️ {title}\n{link}")

    json.dump(sorted(seen), open(STATE, "w"))

if __name__ == "__main__":
    main()