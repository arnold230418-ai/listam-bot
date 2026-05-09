
# Telegram бот для отслеживания аренды на List.am

## Что делает бот

Бот проверяет новые объявления по долгосрочной аренде квартир и домов на List.am
и отправляет уведомление в Telegram.

## Фильтры

- Только собственник (без agency)
- Цена: 1–260000 драм
- Районы:
  - Arabkir
  - Kanaker-Zeytun
  - Ajapnyak
- С животными / по договоренности

## Установка

### 1. Установи Python 3.11+

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

### 3. Создай Telegram-бота

Напиши @BotFather в Telegram:

```text
/newbot
```

Скопируй токен.

### 4. Узнай свой chat_id

Напиши что-нибудь своему боту.

Потом открой:

https://api.telegram.org/bot<TOKEN>/getUpdates

Найди:

```json
"chat":{"id":123456789}
```

### 5. Запусти

Linux / Mac:

```bash
export TELEGRAM_BOT_TOKEN="TOKEN"
export TELEGRAM_CHAT_ID="CHAT_ID"

python bot.py
```

Windows PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="TOKEN"
$env:TELEGRAM_CHAT_ID="CHAT_ID"

python bot.py
```

## Автозапуск

Можно запускать на:
- VPS
- Railway
- Render
- PythonAnywhere
- Raspberry Pi

## Важно

List.am иногда меняет HTML-структуру.
Если бот перестанет находить объявления —
нужно будет обновить CSS-селекторы.
