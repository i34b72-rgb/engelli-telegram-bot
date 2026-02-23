import os
import json
import time
import hashlib
from datetime import datetime, timezone

import feedparser
import requests
from html import escape

# ====== AYARLAR ======
# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # ör: @engelhaberleri

# RSS listesi (başlangıç için örnek; sen sonra çoğaltırsın)
RSS_URLS = [

    # Google News - İstanbul + engelli (son 1 saat)
    "https://news.google.com/rss/search?q=%C4%B0stanbul+engelli+when%3A1h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+eri%C5%9Filebilirlik+when%3A1h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+paralimpik+when%3A1h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+tekerlekli+sandalye+when%3A1h&hl=tr&gl=TR&ceid=TR:tr",

    # Son 24 saat (yedek - daha fazla haber)
    "https://news.google.com/rss/search?q=%C4%B0stanbul+engelli+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+engelli+belediye+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+eri%C5%9Filebilirlik+belediye+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+engelli+proje+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",

    # Spesifik konular
    "https://news.google.com/rss/search?q=%C4%B0stanbul+g%C3%B6rme+engelli+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+i%C5%9Fitme+engelli+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+down+sendromu+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",
    "https://news.google.com/rss/search?q=%C4%B0stanbul+otizm+when%3A24h&hl=tr&gl=TR&ceid=TR:tr",

]

# Paylaşım filtresi (pozitif anahtar kelimeler)
KEYWORDS = [
    "engelli", "erişilebilir", "tekerlekli", "otizm", "down sendrom",
    "görme engelli", "işitme engelli", "paralimpik", "rehabilitasyon",
    "özel eğitim", "engelli maaşı", "engelli hak", "erişim", "rampa",
    "belediye", "proje", "destek", "erişilebilirlik"
]

SEEN_FILE = "seen.json"
MAX_POSTS_PER_RUN = 2  # her çalıştırmada en fazla kaç haber atsın


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

    # 1) İstanbul şart
    # Türkçe i/İ bazen farklı unicode gelir, iki türlü de kontrol ediyoruz.
    if "istanbul" not in text and "i̇stanbul" not in text:
        return False

    # 2) Engelli teması şart
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
    if not r.ok:
        print("Telegram error:", r.status_code, r.text)  # <-- log'a düşer
    r.raise_for_status()


def format_message(entry):
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    summary = (entry.get("summary") or "").strip()

    # kısa özet
    short = summary.replace("\n", " ").strip()
    if len(short) > 350:
        short = short[:347].rstrip() + "..."

    # Telegram HTML parse için kaçış
    safe_title = escape(title)
    safe_short = escape(short)
    safe_link = escape(link)

    # tarih
    published = entry.get("published", "")
    pub = published if published else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    msg = (
        f"<b>{safe_title}</b>\n"
        f"<i>{escape(pub)}</i>\n\n"
        f"{safe_short}\n\n"
        f'<a href="{safe_link}">Devamını oku</a>'
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
