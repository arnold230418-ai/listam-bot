import asyncio
import json
import os
from datetime import datetime, timedelta
import re

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

def extract_date(ad_element):
    """Пытается найти дату объявления"""
    try:
        # Ищем элементы с датой
        date_elements = ad_element.select(".date, .time, .data, .date-time")
        
        for el in date_elements:
            date_text = el.get_text(" ", strip=True)
            # Проверяем разные форматы дат
            if "сегодня" in date_text.lower() or "today" in date_text.lower():
                return datetime.now().date()
            if "вчера" in date_text.lower() or "yesterday" in date_text.lower():
                return datetime.now().date() - timedelta(days=1)
            
            # Пробуем распарсить конкретную дату
            # Формат: DD.MM.YYYY или DD/MM/YYYY
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', date_text)
            if date_match:
                day, month, year = date_match.groups()
                return datetime(int(year), int(month), int(day)).date()
        
        # Если дата не найдена, считаем объявление новым
        return datetime.now().date()
    except:
        # По умолчанию считаем сегодняшним
        return datetime.now().date()

def is_recent(ad_element):
    """Проверяет, добавлено ли объявление сегодня или вчера"""
    try:
        ad_date = extract_date(ad_element)
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        return ad_date == today or ad_date == yesterday
    except:
        # Если не можем определить дату, пропускаем
        return False

def matches_filters(title, description, price_text):
    """Только проверка цены"""
    price = parse_price(price_text)
    
    if not price:
        return False
    
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    
    return True

def scrape_ads():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    ads = []
    
    for url in URLS:
        try:
            print(f"Проверяю: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("div.dl")
            
            print(f"Найдено объявлений: {len(items)}")
            
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
                    
                    # Проверяем фильтры
                    if not matches_filters(title, description, price):
                        continue
                    
                    # Проверяем, что объявление новое (сегодня/вчера)
                    if not is_recent(item):
                        print(f"Пропущено (старое): {title}")
                        continue
                    
                    ads.append({
                        "id": link,
                        "title": title,
                        "price": price,
                        "description": description,
                        "link": link,
                    })
                    print(f"✅ НАЙДЕНО: {title} - {price}")
                    
                except Exception as e:
                    print(f"Ошибка парсинга элемента: {e}")
                    
        except Exception as e:
            print(f"Ошибка при запросе {url}: {e}")
    
    return ads

async def send_message(bot, ad):
    text = (
        f"🏠 НОВОЕ ОБЪЯВЛЕНИЕ\n\n"
        f"📌 {ad['title']}\n"
        f"💰 {ad['price']}\n\n"
        f"📝 {ad['description'][:200]}\n\n"
        f"🔗 {ad['link']}"
    )
    
    await bot.send_message(chat_id=CHAT_ID, text=text)

async def send_test_message(bot):
    """Отправляет тестовое сообщение при запуске"""
    await bot.send_message(
        chat_id=CHAT_ID, 
        text="🤖 БОТ ЗАПУЩЕН!\n\n"
             f"💰 Цена: {MIN_PRICE} - {MAX_PRICE} AMD\n"
             f"📅 Показываю: сегодня и вчера\n"
             f"⏱ Проверка каждые {CHECK_INTERVAL} сек."
    )

async def main():
    if not TOKEN or not CHAT_ID:
        raise ValueError(
            "Укажи TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в переменных окружения"
        )
    
    bot = Bot(token=TOKEN)
    
    # Отправляем тестовое сообщение
    await send_test_message(bot)
    
    seen = load_seen()
    print("Бот запущен:", datetime.now())
    
    while True:
        try:
            print(f"\n--- Проверка в {datetime.now().strftime('%H:%M:%S')} ---")
            ads = scrape_ads()
            
            for ad in ads:
                if ad["id"] not in seen:
                    print(f"📨 ОТПРАВЛЯЮ: {ad['title']}")
                    await send_message(bot, ad)
                    seen.add(ad["id"])
            
            save_seen(seen)
            print(f"Всего найдено новых: {len([a for a in ads if a['id'] not in seen])}")
            
        except Exception as e:
            print(f"ОШИБКА: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
