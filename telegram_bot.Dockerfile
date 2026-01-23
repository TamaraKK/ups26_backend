# telegram_bot.Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY telegram_bot.py .

CMD ["uvicorn", "telegram_bot:app", "--host", "0.0.0.0", "--port", "8080"]
