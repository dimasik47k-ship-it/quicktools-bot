# 🔧 QuickTools Bot

Набор полезных инструментов для Telegram.

## 🛠 Функции

· 🔗 Сокращение ссылок  
· 📱 Создание QR-кодов  
· 🔐 Генерация паролей  
· 🔢 Случайные числа  
· 🧮 Калькулятор  
· ✍️ Форматирование текста  
· 🔄 Base64 кодирование  
· 🎨 Конвертер цветов  
· 📊 Статистика использования  

## 🚀 Запуск локально

```bash
# 1. Клонировать репозиторий
git clone https://github.com/твой_ник/quicktools-bot.git
cd quicktools-bot

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить .env
cp .env.example .env
# Открой .env и добавь BOT_TOKEN

# 5. Запустить
python main.py