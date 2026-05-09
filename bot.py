
import asyncio
import json
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from telegram import Bot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 60  # seconds

# List.am URLs (apartments + houses, long-term rent)
URLS = [
    "https://www.list.am/en/category/56",  # apartments
    "https://www.list.am/en/category/57",  # houses
]

# Filters
MAX_PRICE = 260000
MIN_PRICE = 1

ALLOWED_DISTRICTS = [
    "Arabkir",
    "Kanaker-Zeytun",
    "Ajapnyak",
]

PETS_KEYWORDS = [
    "pets",
    "pet",
    "animal",
    "dog",
    "cat",
    "по договоренности",
    "с животными",
]

OWNER_KEYWORDS = [
    "owner",
    "from owner",
]

SEEN_FILE = "seen_ads.json"


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)


def parse_price(text):
    text = text.replace("֏", "").replace(",", "").strip()

    digits = "".join(ch for ch in text if ch.isdigit())

    if not digits:
        return None

    return int(digits)


def matches_filters(title, description, price_text):
    full_text = f"{title} {description}".lower()

    price = parse_price(price_text)

    if not price:
        return False

    if price < MIN_PRICE or price > MAX_PRICE:
        return False

    if not any(d.lower() in full_text for d in ALLOWED_DISTRICTS):
        return False

    # owner only
    if "agency" in full_text:
        return False

    # pets allowed / negotiable
    if not any(k in full_text for k in PETS_KEYWORDS):
        return False

    return True


def scrape_ads():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    ads = []

    for url in URLS:
        response = requests.get(url, headers=headers, timeout=30)

        soup = BeautifulSoup(response.text, "html.parser")

        items = soup.select("div.dl")

        for item in items:
            try:
                title_el = item.select_one("a")
                price_el = item.select_one(".price")
                desc_el = item.select_one(".l")

                if not title_el or not price_el:
                    continue

                title = title_el.get_text(" ", strip=True)
                link = "https://www.list.am" + title_el.get("href")
                price = price_el.get_text(" ", strip=True)

                description = ""
                if desc_el:
                    description = desc_el.get_text(" ", strip=True)

                if matches_filters(title, description, price):
                    ads.append({
                        "id": link,
                        "title": title,
                        "price": price,
                        "description": description,
                        "link": link,
                    })

            except Exception as e:
                print("Parse error:", e)

    return ads


async def send_message(bot, ad):
    text = (
        f"🏠 Новое объявление\n\n"
        f"{ad['title']}\n"
        f"💰 {ad['price']}\n\n"
        f"{ad['description']}\n\n"
        f"{ad['link']}"
    )

    await bot.send_message(chat_id=CHAT_ID, text=text)


async def main():
    if not TOKEN or not CHAT_ID:
        raise ValueError(
            "Укажи TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в переменных окружения"
        )

    bot = Bot(token=TOKEN)

    seen = load_seen()

    print("Бот запущен:", datetime.now())

    while True:
        try:
            ads = scrape_ads()

            for ad in ads:
                if ad["id"] not in seen:
                    print("NEW:", ad["title"])

                    await send_message(bot, ad)

                    seen.add(ad["id"])

            save_seen(seen)

        except Exception as e:
            print("ERROR:", e)

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
