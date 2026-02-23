import os
import json
import time
import hashlib
from datetime import datetime, timezone

import feedparser
import requests

# ====== AYARLAR ======
# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # ör: @engelhaberleri

# RSS listesi (başlangıç için örnek; sen sonra çoğaltırsın)
RSS_URLS = [
    # Google News RSS: "engelli" araması (TR)
    "https://news.google.com/rss/search?q=engelli&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=eri%C5%9Filebilirlik&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=paralimpik&hl=tr&gl=TR&ceid=TR:tr",
]

# Paylaşım filtresi (pozitif anahtar kelimeler)
KEYWORDS = [
    "engelli", "erişilebilir", "tekerlekli", "otizm", "down sendrom",
    "görme engelli", "işitme engelli", "paralimpik", "rehabilitasyon",
    "özel eğitim", "ekpss", "engelli maaşı"
]

SEEN_FILE = "seen.json"
MAX_POSTS_PER_RUN = 5  # her çalıştırmada en fazla kaç haber atsın


def normalize_text(s: str) -> str:
    return (s or "").lower().strip()


def make_id(title: str, link: str) -> str:
    # Başlık + linkten sabit id üret (dedup için)
    raw = f"{title}::{link}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen_set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen_set))[-5000:], f, ensure_ascii=False, indent=2)


def matches_keywords(title: str, summary: str) -> bool:
    text = normalize_text(title) + " " + normalize_text(summary)
    return any(k in text for k in KEYWORDS)


def telegram_send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def format_message(entry):
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    summary = (entry.get("summary") or "").strip()

    # kısa özet
    short = summary.replace("\n", " ").strip()
    if len(short) > 350:
        short = short[:347].rstrip() + "..."

    # tarih
    published = entry.get("published", "")
    if published:
        pub = published
    else:
        pub = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    msg = (
        f"<b>{title}</b>\n"
        f"<i>{pub}</i>\n\n"
        f"{short}\n\n"
        f"Devamı: {link}"
    )
    return msg


def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN veya CHAT_ID ortam değişkeni eksik. GitHub Secrets ayarla.")

    seen = load_seen()
    posted = 0

    # RSS'leri gez
    for rss in RSS_URLS:
        feed = feedparser.parse(rss)

        for entry in feed.entries[:20]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")

            if not title or not link:
                continue

            if not matches_keywords(title, summary):
                continue

            uid = make_id(title, link)
            if uid in seen:
                continue

            # Mesaj at
            msg = format_message(entry)
            telegram_send_message(msg)

            seen.add(uid)
            posted += 1
            time.sleep(1.2)  # Telegram rate-limit'e takılma

            if posted >= MAX_POSTS_PER_RUN:
                break

        if posted >= MAX_POSTS_PER_RUN:
            break

    save_seen(seen)
    print(f"Posted: {posted}")


if __name__ == "__main__":
    main()
