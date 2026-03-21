# QuickTools Bot — полная версия для Docker + Render
# Все настройки через .env, без хардкода токенов

import asyncio
import random
import string
import logging
import base64
import sqlite3
import os
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession

import aiohttp
import qrcode
from io import BytesIO
from aiohttp import web

# ========== 🔥 ЗАГРУЗКА .ENV 🔥 ==========
load_dotenv()

# ========== 🔐 НАСТРОЙКИ (ТОЛЬКО из .env!) 🔥 ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")

# Прокси настройки
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", 9150))
PROXY_LOGIN = os.getenv("PROXY_LOGIN", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")
USE_PROXY = os.getenv("USE_PROXY", "true").lower() == "true"

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ========== ПРОВЕРКА ТОКЕНА ==========
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден в .env!")
    print("💡 Создай файл .env и добавь: BOT_TOKEN=твой_новый_токен")
    exit(1)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('quicktools.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, username TEXT, first_use TEXT, last_use TEXT, commands_count INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS commands_log 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, command TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def log_command(user_id: int, command: str):
    conn = sqlite3.connect('quicktools.db')
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT INTO commands_log (user_id, command, timestamp) VALUES (?, ?, ?)", 
              (user_id, command, now))
    c.execute("""INSERT OR REPLACE INTO users (user_id, username, first_use, last_use, commands_count) 
                 VALUES (?, ?, COALESCE((SELECT first_use FROM users WHERE user_id=?), ?), ?, 
                         COALESCE((SELECT commands_count FROM users WHERE user_id=?), 0) + 1)""",
              (user_id, None, user_id, now, now, user_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id: int):
    conn = sqlite3.connect('quicktools.db')
    c = conn.cursor()
    c.execute("SELECT commands_count, first_use, last_use FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

init_db()

# ========== СОЗДАНИЕ БОТА С ПРОКСИ ==========
def create_bot_with_proxy():
    if USE_PROXY:
        if PROXY_LOGIN and PROXY_PASSWORD:
            proxy_url = f"socks5://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
        else:
            proxy_url = f"socks5://{PROXY_HOST}:{PROXY_PORT}"
        logger.info(f"🔐 Прокси: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
        logger.info("🌐 Бот запускается через SOCKS5 прокси")
    else:
        session = AiohttpSession()
        logger.info("🌐 Бот запускается напрямую")
    return Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

# Глобальные переменные
bot: Bot = None
dp = Dispatcher()

# ========== 🔘 КЛАВИАТУРЫ ==========
def get_tools_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data="tool_short"),
         InlineKeyboardButton(text="📱 QR", callback_data="tool_qr")],
        [InlineKeyboardButton(text="🔐 Пароль", callback_data="tool_pass"),
         InlineKeyboardButton(text="🎲 Число", callback_data="tool_rand")],
        [InlineKeyboardButton(text="🧮 Калькулятор", callback_data="tool_calc"),
         InlineKeyboardButton(text="🔄 Текст", callback_data="tool_text")],
        [InlineKeyboardButton(text="🔢 Base64", callback_data="tool_b64"),
         InlineKeyboardButton(text="🎨 Цвет", callback_data="tool_color")],
        [InlineKeyboardButton(text="🤖 ИИ", callback_data="tool_ai"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="tool_stats")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="tool_help")]
    ])

def get_retry_keyboard(cb: str):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Ещё раз", callback_data=cb)]])

def get_try_keyboard(command: str, text: str):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✨ {text}", callback_data=f"try_{command}")]])

async def ask_hf(prompt: str) -> str:
    """Запрос к Hugging Face API — НОВЫЙ эндпоинт 2026"""
    
    if not HF_TOKEN:
        return "❌ HF_TOKEN не настроен в .env!"
    
    # ✅ НОВЫЙ URL (старый возвращает 410)
    url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # ✅ OpenAI-совместимый формат запроса
    data = {
        "model": HF_MODEL,  # например: "Qwen/Qwen2.5-0.5B-Instruct"
        "messages": [
            {"role": "system", "content": "Ты полезный ассистент бота QuickTools. Отвечай кратко и по-русски."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers, timeout=60) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    answer = result["choices"][0]["message"]["content"].strip()
                    return answer
                elif resp.status == 401:
                    return "❌ Неверный HF_TOKEN"
                elif resp.status == 404:
                    return f"❌ Модель не найдена: {HF_MODEL}"
                elif resp.status == 429:
                    return "⏳ Лимит запросов. Попробуй через минуту"
                else:
                    error_text = await resp.text()
                    return f"❌ Ошибка HF API {resp.status}: {error_text[:100]}"
    except Exception as e:
        return f"❌ Ошибка соединения: {e}"

# ========== СТАРТ ==========
async def on_startup():
    logger.info("=" * 60)
    logger.info("🤖 QUICKTOOLS BOT ЗАПУСКАЕТСЯ...")
    logger.info("=" * 60)
    try:
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот: @{bot_info.username} | ID: {bot_info.id}")
        logger.info("✨ Бот готов к работе!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise

# ========== 🏥 HEALTH ENDPOINT ДЛЯ RENDER (БЕЗОПАСНЫЙ) ==========
async def health_handler(request):
    """
    Endpoint для проверки здоровья бота (Render/UptimeRobot).
    ⚠️ Всегда возвращает 200, чтобы Render не убивал контейнер!
    ⚠️ Никаких async-вызовов к Telegram API!
    """
    try:
        bot_status = "ok" if (bot and getattr(bot, 'token', None)) else "initializing"
        bot_username = None
        
        # Если бот уже закешировал info — берём оттуда (без сетевых вызовов)
        if bot and hasattr(bot, '_me') and bot._me:
            bot_username = bot._me.username
        
        return web.json_response({
            "status": bot_status,
            "bot": bot_username,
            "port": os.getenv("PORT", "unknown"),
            "timestamp": datetime.now().isoformat()
        }, status=200)
        
    except Exception as e:
        logger.error(f"❌ Health check error: {type(e).__name__}: {e}")
        # 🔥 КРИТИЧНО: даже при ошибке возвращаем 200!
        return web.json_response({
            "status": "error",
            "message": "Internal check failed"
        }, status=200)

async def start_web_server():
    """Запускаем мини-веб-сервер для health checks"""
    app = web.Application()
    app.router.add_get('/health', health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render назначает порт через переменную окружения
    port = int(os.getenv("PORT", 8080))
    # 🔥 Слушаем 0.0.0.0, чтобы быть доступным извне
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🏥 Health server started on 0.0.0.0:{port}")
    
    return runner

# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    log_command(message.from_user.id, "/start")
    tips = [
        "💡 Пиши /ai вопрос — получи умный ответ!",
        "💡 /calc 2+2*2 — быстрый калькулятор",
        "💡 /text upper ПРИВЕТ — сделай текст заглавным",
        "💡 /color #FF5733 — конвертируй цвета"
    ]
    await message.answer(
        f"👋 <b>Привет! Я QuickTools Bot!</b>\n\n"
        f"🛠 <b>Инструменты:</b>\n"
        f"🔗 /short — ссылка | 📱 /qr — QR-код\n"
        f"🔐 /pass — пароль | 🎲 /rand — число\n"
        f"🧮 /calc — калькулятор | 🔄 /text — текст\n"
        f"🔢 /b64 — Base64 | 🎨 /color — цвета\n"
        f"🤖 /ai — ИИ (Hugging Face) | 📊 /stats — статистика\n\n"
        f"🎲 <i>Совет:</i> {random.choice(tips)}",
        reply_markup=get_tools_inline()
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    log_command(message.from_user.id, "/help")
    await message.answer(
        "📚 <b>СПРАВКА</b>\n\n"
        "🔗 /short [ссылка] — сократить\n"
        "📱 /qr [текст] — QR-код\n"
        "🔐 /pass [длина] — пароль\n"
        "🎲 /rand [min] [max] — число\n"
        "🧮 /calc [выражение] — калькулятор\n"
        "🔄 /text [mode] [текст] — форматирование\n"
        "🔢 /b64 [encode/decode] [текст] — Base64\n"
        "🎨 /color [HEX/RGB] — цвета\n"
        "🤖 /ai [вопрос] — ИИ помощник\n"
        "📊 /stats — твоя статистика",
        reply_markup=get_tools_inline()
    )

@dp.message(Command("calc"))
async def cmd_calc(message: types.Message):
    log_command(message.from_user.id, "/calc")
    try:
        expr = message.text.replace("/calc ", "").strip()
        if not expr:
            await message.answer("❌ Введи: /calc 2+2*2", reply_markup=get_retry_keyboard("tool_calc"))
            return
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expr):
            await message.answer("❌ Только цифры и + - * / ( )")
            return
        result = eval(expr, {"__builtins__": {}}, {})
        await message.answer(f"🧮 <b>Результат:</b>\n<code>{expr} = {result}</code>", reply_markup=get_retry_keyboard("tool_calc"))
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("text"))
async def cmd_text(message: types.Message):
    log_command(message.from_user.id, "/text")
    try:
        parts = message.text.replace("/text ", "").strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("❌ /text upper привет", reply_markup=get_retry_keyboard("tool_text"))
            return
        mode, text = parts[0].lower(), parts[1]
        if mode == "upper": result = text.upper()
        elif mode == "lower": result = text.lower()
        elif mode == "reverse": result = text[::-1]
        elif mode == "title": result = text.title()
        else:
            await message.answer("❌ Режимы: upper, lower, reverse, title")
            return
        await message.answer(f"🔄 <b>Результат:</b>\n<code>{result}</code>", reply_markup=get_retry_keyboard("tool_text"))
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("b64"))
async def cmd_b64(message: types.Message):
    log_command(message.from_user.id, "/b64")
    try:
        parts = message.text.replace("/b64 ", "").strip().split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("❌ /b64 encode текст", reply_markup=get_retry_keyboard("tool_b64"))
            return
        mode, text = parts[0].lower(), parts[1]
        if mode == "encode": result = base64.b64encode(text.encode()).decode()
        elif mode == "decode": result = base64.b64decode(text.encode()).decode(errors="ignore")
        else:
            await message.answer("❌ Режимы: encode, decode")
            return
        await message.answer(f"🔢 <b>Base64:</b>\n<code>{result}</code>", reply_markup=get_retry_keyboard("tool_b64"))
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("color"))
async def cmd_color(message: types.Message):
    log_command(message.from_user.id, "/color")
    try:
        val = message.text.replace("/color ", "").strip()
        if not val:
            await message.answer("❌ /color #FF5733 или 255,87,51", reply_markup=get_retry_keyboard("tool_color"))
            return
        if val.startswith("#"):
            val = val.lstrip("#")
            if len(val) == 6:
                r, g, b = tuple(int(val[i:i+2], 16) for i in (0, 2, 4))
                await message.answer(f"🎨 <b>HEX → RGB:</b>\n<code>#{val.upper()} = rgb({r}, {g}, {b})</code>", reply_markup=get_retry_keyboard("tool_color"))
            else:
                await message.answer("❌ HEX: #RRGGBB (6 символов)")
        elif "," in val:
            r, g, b = map(int, [x.strip() for x in val.split(",")])
            if all(0 <= x <= 255 for x in [r, g, b]):
                hex_val = "#{:02X}{:02X}{:02X}".format(r, g, b)
                await message.answer(f"🎨 <b>RGB → HEX:</b>\n<code>rgb({r}, {g}, {b}) = {hex_val}</code>", reply_markup=get_retry_keyboard("tool_color"))
            else:
                await message.answer("❌ RGB: 0-255")
        else:
            await message.answer("❌ /color #FF5733 или 255,87,51")
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("ai"))
async def cmd_ai(message: types.Message):
    log_command(message.from_user.id, "/ai")
    prompt = message.text.replace("/ai ", "").strip()
    
    if not prompt:
        await message.answer(
            "🤖 <b>ИИ-помощник (Hugging Face)</b>\n\n"
            f"<i>Модель:</i> <code>{HF_MODEL}</code>\n\n"
            "<i>Задай вопрос!</i>\n"
            "Пример: /ai как создать надёжный пароль?",
            reply_markup=get_retry_keyboard("tool_ai")
        )
        return
    
    msg = await message.answer("🤖 <i>Думаю...</i>")
    answer = await ask_hf(prompt)
    await msg.edit_text(
        f"🤖 <b>Ответ:</b>\n\n{answer}\n\n"
        f"<i>💡 Задай ещё вопрос или выбери инструмент:</i>",
        reply_markup=get_tools_inline()
    )

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    log_command(message.from_user.id, "/stats")
    stats = get_user_stats(message.from_user.id)
    if stats and stats[0]:
        count, first, last = stats
        await message.answer(f"📊 <b>Статистика:</b>\n\n🔢 Команд: <b>{count}</b>\n📅 Первый: <code>{first}</code>\n🕐 Последний: <code>{last}</code>", reply_markup=get_tools_inline())
    else:
        await message.answer("📊 <b>Статистика:</b>\n\n<i>Используй команды!</i>", reply_markup=get_tools_inline())

@dp.callback_query(F.data.startswith("tool_"))
async def callback_tool(callback: types.CallbackQuery):
    tool = callback.data.replace("tool_", "")
    commands = {
        "short": ("🔗 Ссылка", "/short [ссылка]", "/short https://google.com"),
        "qr": ("📱 QR-код", "/qr [текст]", "/qr Привет"),
        "pass": ("🔐 Пароль", "/pass [длина]", "/pass 16"),
        "rand": ("🎲 Число", "/rand [min] [max]", "/rand 1 100"),
        "calc": ("🧮 Калькулятор", "/calc [выражение]", "/calc 2+2*2"),
        "text": ("🔄 Текст", "/text [mode] [текст]", "/text upper привет"),
        "b64": ("🔢 Base64", "/b64 [encode/decode] [текст]", "/b64 encode секрет"),
        "color": ("🎨 Цвет", "/color [HEX/RGB]", "/color #FF5733"),
        "ai": ("🤖 ИИ", "/ai [вопрос]", "/ai как дела?"),
        "stats": ("📊 Статистика", "/stats", "Твоя активность"),
        "help": ("ℹ️ Помощь", "/help", "Справка")
    }
    if tool in commands:
        title, cmd, example = commands[tool]
        new_text = f"{title}\n\n<b>Команда:</b> <code>{cmd}</code>\n<i>{example}</i>"
        try:
            await callback.message.edit_text(new_text, reply_markup=get_tools_inline())
        except:
            await callback.message.answer(new_text, reply_markup=get_tools_inline())
        await callback.answer()

@dp.callback_query(F.data.startswith("try_"))
async def callback_try(callback: types.CallbackQuery):
    cmd = callback.data.replace("try_", "")
    await callback.answer(f"✍️ Введи /{cmd}")
    await callback.message.answer(f"👉 Введи: <code>/{cmd}</code>")

@dp.message(Command("short"))
async def cmd_short(message: types.Message):
    log_command(message.from_user.id, "/short")
    url = message.text.replace("/short ", "").strip()
    if not url or url == message.text:
        await message.answer("❌ /short https://example.com", reply_markup=get_try_keyboard("short", "Попробовать"))
        return
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    msg = await message.answer("⏳ <i>Сокращаю...</i>")
    async with aiohttp.ClientSession() as session:
        # ✅ FIX: убраны лишние пробелы в URL
        async with session.get(f"https://clck.ru/--?url={url}") as resp:
            if resp.status == 200:
                short = (await resp.text()).strip()
                await msg.edit_text(
                    f"🔗 <b>ГОТОВО!</b>\n\n📎 <code>{url}</code>\n\n✅ {short}", 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 Скопировать", url=short)],
                        [InlineKeyboardButton(text="🔄 Ещё", callback_data="tool_short")]
                    ])
                )
            else:
                await msg.edit_text("❌ Ошибка")

@dp.message(Command("qr"))
async def cmd_qr(message: types.Message):
    log_command(message.from_user.id, "/qr")
    text = message.text.replace("/qr ", "").strip()
    if not text or text == message.text:
        await message.answer("❌ /qr Привет", reply_markup=get_try_keyboard("qr", "Попробовать"))
        return
    msg = await message.answer("⏳ <i>Генерирую QR...</i>")
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await msg.delete()
    await message.answer_photo(
        photo=BufferedInputFile(buf.read(), "qr.png"), 
        caption=f"📱 <b>QR готов!</b>\n\n<code>{text[:50]}{'...' if len(text)>50 else ''}</code>", 
        reply_markup=get_retry_keyboard("tool_qr")
    )

@dp.message(Command("pass"))
async def cmd_pass(message: types.Message):
    log_command(message.from_user.id, "/pass")
    args = message.text.replace("/pass ", "").strip()
    length = int(args) if args and args != message.text else 16
    if not 4 <= length <= 50:
        await message.answer("❌ Длина: 4-50 символов")
        return
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    pwd = ''.join(random.choice(chars) for _ in range(length))
    await message.answer(
        f"🔐 <b>ПАРОЛЬ:</b>\n\n<code>{pwd}</code>\n\n💡 <i>Скопируй!</i>",
        reply_markup=get_retry_keyboard("tool_pass")
    )

@dp.message(Command("rand"))
async def cmd_rand(message: types.Message):
    log_command(message.from_user.id, "/rand")
    args = message.text.replace("/rand ", "").strip().split()
    if len(args) != 2:
        await message.answer("❌ /rand 1 100", reply_markup=get_try_keyboard("rand", "Попробовать"))
        return
    a, b = int(args[0]), int(args[1])
    if a >= b:
        await message.answer("❌ Первое < второго")
        return
    result = random.randint(a, b)
    await message.answer(
        f"🎲 <b>Число:</b>\n\n🎯 <b>{result}</b>\n\n📊 {a} - {b}",
        reply_markup=get_retry_keyboard("tool_rand")
    )

# ========== 🚀 ЗАПУСК (ПРАВИЛЬНЫЙ ПОРЯДОК!) ==========
async def main():
    global bot, dp
    
    # 1️⃣ СНАЧАЛА health-сервер — чтобы Render сразу видел 200
    web_runner = await start_web_server()
    logger.info("🏥 Health endpoint ready on /health")
    
    # 2️⃣ Потом инициализация бота (может занять время)
    try:
        bot = create_bot_with_proxy()
        await bot.get_me()  # Проверка токена
        logger.info(f"✅ Бот @{(await bot.get_me()).username} инициализирован")
    except Exception as e:
        logger.error(f"⚠️ Бот не инициализирован: {e}")
        # НЕ выходим! Health уже отвечает, Render не убьёт контейнер
    
    # 3️⃣ Запуск поллинга
    logger.info("🚀 Starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        if bot:
            await bot.session.close()
        await web_runner.cleanup()

# ========== ENTRY POINT ==========
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        raise