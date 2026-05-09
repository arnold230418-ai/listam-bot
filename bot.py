import asyncio
import json
import os
import time
from datetime import datetime, timedelta
import re

import requests
from bs4 import BeautifulSoup
from telegram import Bot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL = 60  # seconds

# List.am URLs (apartments only для теста)
URLS = [
    "https://www.list.am/en/category/56",  # apartments
]

# Filters
MAX_PRICE = 260000
MIN_PRICE = 1

ALLOWED_DISTRICTS = [
    "Arabkir",
    "Kanaker-Zeytun",
    "Ajapnyak",
    "Nor Nork",
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
    # Обработка разных валют
    text = text.replace("֏", "").replace("$", "").replace("€", "").replace(",", "").strip()
    # Берем только первое число, если их несколько
    match = re.search(r'\d+', text)
    if not match:
        return None
    return int(match.group())

def extract_date(ad_element):
    """Пытается найти дату объявления"""
    try:
        date_elements = ad_element.select(".date, .time, .data, .date-time")
        
        for el in date_elements:
            date_text = el.get_text(" ", strip=True).lower()
            if "сегодня" in date_text or "today" in date_text:
                return datetime.now().date()
            if "вчера" in date_text or "yesterday" in date_text:
                return datetime.now().date() - timedelta(days=1)
            
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', date_text)
            if date_match:
                day, month, year = date_match.groups()
                return datetime(int(year), int(month), int(day)).date()
        
        return None  # Не можем определить дату
    except:
        return None

def is_recent(ad_element):
    """Проверяет, добавлено ли объявление сегодня или вчера"""
    ad_date = extract_date(ad_element)
    if ad_date is None:
        # Если дату определить не можем - считаем новым (не фильтруем)
        return True
    
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    return ad_date == today or ad_date == yesterday

def matches_filters(title, description, price_text):
    """Проверяет цену и район"""
    full_text = f"{title} {description}".lower()
    
    price = parse_price(price_text)
    
    if not price:
        return False
    
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    
    # Проверка районов
    if not any(d.lower() in full_text for d in ALLOWED_DISTRICTS):
        return False
    
    # Исключаем агенства
    if "agency" in full_text:
        return False
    
    return True

def clean_text(text):
    """Очищает текст от проблемных символов"""
    if not text:
        return ""
    text = text.replace('\n', ' ').replace('\r', ' ').strip()
    text = ' '.join(text.split())
    return text

def scrape_ads():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Connection": "keep-alive",
    }
    
    ads = []
    
    for url in URLS:
        try:
            print(f"Проверяю: {url}")
            time.sleep(2)
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("div.dl")
            
            if not items:
                items = soup.select("div[data-id]")
            
            print(f"Найдено элементов: {len(items)}")
            
            for item in items:
                try:
                    title_el = item.select_one("a")
                    price_el = item.select_one(".price")
                    desc_el = item.select_one(".l")
                    
                    if not title_el or not price_el:
                        continue
                    
                    title = clean_text(title_el.get_text(" ", strip=True))
                    href = title_el.get("href", "")
                    if href.startswith("/"):
                        link = "https://www.list.am" + href
                    else:
                        link = href
                    
                    price = clean_text(price_el.get_text(" ", strip=True))
                    
                    description = ""
                    if desc_el:
                        description = clean_text(desc_el.get_text(" ", strip=True))
                    
                    if not matches_filters(title, description, price):
                        continue
                    
                    if not is_recent(item):
                        continue
                    
                    ads.append({
                        "id": link,
                        "title": title,
                        "price": price,
                        "link": link,
                    })
                    print(f"НАЙДЕНО: {title} - {price}")
                    
                except Exception as e:
                    print(f"Ошибка парсинга элемента: {e}")
                    
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе {url}: {e}")
        except Exception as e:
            print(f"Общая ошибка: {e}")
    
    return ads

async def send_message(bot, ad):
    """Отправляет сообщение о новом объявлении"""
    # Максимально простой формат без лишних символов
    title = ad['title'][:150]
    price = ad['price']
    link = ad['link']
    
    text = f"NEW LISTING\n\n{title}\nPrice: {price}\n\n{link}"
    
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text)
        print(f"SENT: {title[:50]}")
    except Exception as e:
        print(f"Send error: {e}")

async def main():
    if not TOKEN or not CHAT_ID:
        raise ValueError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    
    bot = Bot(token=TOKEN)
    
    # Простая проверка связи без лишних символов
    try:
        await bot.send_message(chat_id=CHAT_ID, text="Bot started")
        print("Test message sent")
    except Exception as e:
        print(f"Test send failed: {e}")
        # Не выходим, продолжаем работу
    
    seen = load_seen()
    print("Bot started:", datetime.now())
    
    while True:
        try:
            print(f"\n--- Check at {datetime.now().strftime('%H:%M:%S')} ---")
            ads = scrape_ads()
            
            new_count = 0
            for ad in ads:
                if ad["id"] not in seen:
                    print(f"SENDING: {ad['title'][:50]}")
                    await send_message(bot, ad)
                    seen.add(ad["id"])
                    new_count += 1
                    await asyncio.sleep(1)
            
            save_seen(seen)
            print(f"New ads sent: {new_count}")
            
        except Exception as e:
            print(f"ERROR: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
