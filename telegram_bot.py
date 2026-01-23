import os
import time
from telegram import Bot, error
from fastapi import FastAPI, Request
import asyncio

# --- CONFIG ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8208965134:AAE_RhvGcYbTpbGbqSLvh6BUU8xi5Sdkg5c")
USER_IDS = os.environ.get("TELEGRAM_USER_IDS", "524936744,640937673").split(",")
ALERT_COOLDOWN_SECONDS = 180  # 3 минуты

# --- STATE ---
bot = Bot(token=BOT_TOKEN)
app = FastAPI()
# Словарь для хранения временных меток последней отправки алерта
# Ключ - alert fingerprint, значение - timestamp
last_alert_timestamps = {}

@app.post("/webhook")
async def alertmanager_webhook(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        print(f"Error decoding JSON: {e}")
        return {"status": "error", "message": "Invalid JSON"}, 400

    alerts_to_notify = []
    current_time = time.time()

    for alert in data.get('alerts', []):
        fingerprint = alert.get('fingerprint')
        if not fingerprint:
            continue

        last_sent_time = last_alert_timestamps.get(fingerprint)
        
        # Проверяем, прошел ли кулдаун
        if last_sent_time and (current_time - last_sent_time) < ALERT_COOLDOWN_SECONDS:
            print(f"Cooldown active for alert {fingerprint}. Skipping.")
            continue

        alerts_to_notify.append(alert)
        # Обновляем время отправки только после успешной попытки
        last_alert_timestamps[fingerprint] = current_time

    if alerts_to_notify:
        status = data.get('status', 'N/A').upper()
        common_labels = data.get('commonLabels', {})
        alert_name = common_labels.get('alertname', 'N/A')

        message = f"🚨 *{status}: {len(alerts_to_notify)} new {alert_name} alert(s)* 🚨\n\n"

        for i, alert in enumerate(alerts_to_notify):
            annotations = alert.get('annotations', {})
            summary = annotations.get('summary', 'No summary')
            description = annotations.get('description', 'No description')
            
            message += f"*{i+1}. {summary}*\n"
            message += f"  *Description*: {description}\n\n"

        # Асинхронная отправка всем пользователям
        send_tasks = [
            bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
            for user_id in USER_IDS
        ]
        try:
            await asyncio.gather(*send_tasks)
        except error.BadRequest as e:
            print(f"Error sending message: {e}. One of the USER_IDS is likely invalid or the bot isn't in the chat.")
        
    return {"status": "ok"}

@app.get("/")
def root():
    return {"status": "ok", "message": "Bot is running"}
