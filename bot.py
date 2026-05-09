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
    "Nor Nork",  # Добавлен для теста
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

def extract_date(ad_element):
    """Пытается найти дату объявления"""
    try:
        date_elements = ad_element.select(".date, .time, .data, .date-time")
        
        for el in date_elements:
            date_text = el.get_text(" ", strip=True)
            if "сегодня" in date_text.lower() or "today" in date_text.lower():
                return datetime.now().date()
            if "вчера" in date_text.lower() or "yesterday" in date_text.lower():
                return datetime.now().date() - timedelta(days=1)
            
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', date_text)
            if date_match:
                day, month, year = date_match.groups()
                return datetime(int(year), int(month), int(day)).date()
        
        return datetime.now().date()
    except:
        return datetime.now().date()

def is_recent(ad_element):
    """Проверяет, добавлено ли объявление сегодня или вчера"""
    try:
        ad_date = extract_date(ad_element)
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        return ad_date == today or ad_date == yesterday
    except:
        return False

def matches_filters(title, description, price_text):
    """Проверяет цену и район (без проверки на животных)"""
    full_text = f"{title} {description}".lower()
    
    price = parse_price(price_text)
    
    if not price:
        return False
    
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    
    # Проверка районов
    if not any(d.lower() in full_text for d in ALLOWED_DISTRICTS):
        return False
    
    # Исключаем агенства (опционально, можно закомментировать)
    if "agency" in full_text:
        return False
    
    return True

def clean_text(text):
    """Очищает текст от проблемных символов"""
    if not text:
        return ""
    # Убираем лишние пробелы и переносы строк
    text = text.replace('\n', ' ').replace('\r', ' ').strip()
    # Убираем множественные пробелы
    text = ' '.join(text.split())
    return text

def scrape_ads():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    ads = []
    
    for url in URLS:
        try:
            print(f"Проверяю: {url}")
            time.sleep(2)  # Задержка между запросами
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("div.dl")
            
            # Альтернативный селектор, если div.dl не найден
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
                    link = "https://www.list.am" + title_el.get("href")
                    price = clean_text(price_el.get_text(" ", strip=True))
                    
                    description = ""
                    if desc_el:
                        description = clean_text(desc_el.get_text(" ", strip=True))
                    
                    # Фильтрация
                    if not matches_filters(title, description, price):
                        continue
                    
                    # Проверка даты (только сегодня/вчера)
                    if not is_recent(item):
                        continue
                    
                    ads.append({
                        "id": link,
                        "title": title,
                        "price": price,
                        "description": description,
                        "link": link,
                    })
                    print(f"НАЙДЕНО: {title} - {price}")
                    
                except Exception as e:
                    print(f"Ошибка парсинга элемента: {e}")
                    
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе {url}: {e}")
            if "403" in str(e):
                print("Ошибка 403 - доступ запрещен. Возможно, IP заблокирован.")
        except Exception as e:
            print(f"Общая ошибка при обработке {url}: {e}")
    
    return ads

async def send_message(bot, ad):
    """Отправляет сообщение о новом объявлении (упрощенная версия)"""
    # Упрощаем текст, убираем все возможные спецсимволы
    title = ad['title'][:100]  # Ограничиваем длину
    price = ad['price']
    link = ad['link']
    
    text = f"НОВОЕ ОБЪЯВЛЕНИЕ\n\n{title}\nЦена: {price}\n\n{link}"
    
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text)
        print(f"Сообщение отправлено: {title}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

async def send_test_message(bot):
    """Отправляет тестовое сообщение при запуске"""
    text = f"БОТ ЗАПУЩЕН\n\nЦена: {MIN_PRICE} - {MAX_PRICE} AMD\nРайоны: {', '.join(ALLOWED_DISTRICTS)}\nПроверка каждые {CHECK_INTERVAL} секунд"
    
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text)
        print("Тестовое сообщение отправлено")
    except Exception as e:
        print(f"Ошибка отправки тестового сообщения: {e}")

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
            
            new_count = 0
            for ad in ads:
                if ad["id"] not in seen:
                    print(f"ОТПРАВЛЯЮ: {ad['title']}")
                    await send_message(bot, ad)
                    seen.add(ad["id"])
                    new_count += 1
                    await asyncio.sleep(1)  # Пауза между отправками
            
            save_seen(seen)
            print(f"Отправлено новых объявлений: {new_count}")
            
        except Exception as e:
            print(f"ОШИБКА в основном цикле: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
