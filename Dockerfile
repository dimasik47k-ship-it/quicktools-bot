FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Порт для health checks
EXPOSE 8080

# Запуск
CMD ["python", "main.py"]