# Используем официальный Python образ
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY . .

# Переменная чтобы Python не буферизировал логи
ENV PYTHONUNBUFFERED=1

# Health check для Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Запускаем бота
CMD ["python", "main.py"]