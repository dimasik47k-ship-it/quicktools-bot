# QuickTools Bot — версия БЕЗ ИИ
# Все настройки через .env

import asyncio, random, string, logging, base64, sqlite3, os
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
import aiohttp, qrcode
from io import BytesIO
from aiohttp import web

load_dotenv()

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", 9150))
PROXY_LOGIN = os.getenv("PROXY_LOGIN", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")
USE_PROXY = os.getenv("USE_PROXY", "true").lower() == "true"

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден в .env!"); exit(1)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('quicktools.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, username TEXT, first_use TEXT, last_use TEXT, commands_count INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS commands_log 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, command TEXT, timestamp TEXT)''')
    conn.commit(); conn.close()

def log_command(user_id: int, command: str):
    conn = sqlite3.connect('quicktools.db'); c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT INTO commands_log (user_id, command, timestamp) VALUES (?, ?, ?)", (user_id, command, now))
    c.execute("""INSERT OR REPLACE INTO users (user_id, username, first_use, last_use, commands_count) 
                 VALUES (?, ?, COALESCE((SELECT first_use FROM users WHERE user_id=?), ?), ?, 
                         COALESCE((SELECT commands_count FROM users WHERE user_id=?), 0) + 1)""",
              (user_id, None, user_id, now, now, user_id))
    conn.commit(); conn.close()

def get_user_stats(user_id: int):
    conn = sqlite3.connect('quicktools.db'); c = conn.cursor()
    c.execute("SELECT commands_count, first_use, last_use FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone(); conn.close()
    return result

init_db()

# ========== БОТ С ПРОКСИ ==========
def create_bot_with_proxy():
    if USE_PROXY:
        proxy = f"socks5://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}" if PROXY_LOGIN else f"socks5://{PROXY_HOST}:{PROXY_PORT}"
        session = AiohttpSession(proxy=proxy)
    else:
        session = AiohttpSession()
    return Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

bot: Bot = None
dp = Dispatcher()

# ========== КЛАВИАТУРЫ ==========
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
        [InlineKeyboardButton(text="📊 Статистика", callback_data="tool_stats")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="tool_help")]
    ])

def get_retry_keyboard(cb: str):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Ещё раз", callback_data=cb)]])

def get_try_keyboard(command: str, text: str):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✨ {text}", callback_data=f"try_{command}")]])

# ========== СТАРТ ==========
async def on_startup():
    logger.info("🤖 QUICKTOOLS BOT (без ИИ) ЗАПУСКАЕТСЯ...")
    try:
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот: @{bot_info.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ========== HEALTH ДЛЯ RENDER ==========
async def health_handler(request):
    return web.json_response({"status": "ok", "bot": getattr(bot, '_me', None) and bot._me.username}, status=200)

async def start_web_server():
    app = web.Application(); app.router.add_get('/health', health_handler)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port); await site.start()
    logger.info(f"🏥 Health on 0.0.0.0:{port}")
    return runner

# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    log_command(message.from_user.id, "/start")
    await message.answer(
        f"👋 <b>Привет! Я QuickTools Bot!</b>\n\n"
        f"🛠 <b>Инструменты:</b>\n"
        f"🔗 /short — ссылка | 📱 /qr — QR-код\n"
        f"🔐 /pass — пароль | 🎲 /rand — число\n"
        f"🧮 /calc — калькулятор | 🔄 /text — текст\n"
        f"🔢 /b64 — Base64 | 🎨 /color — цвета | 📊 /stats — статистика",
        reply_markup=get_tools_inline()
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    log_command(message.from_user.id, "/help")
    await message.answer(
        "📚 <b>СПРАВКА</b>\n\n"
        "🔗 /short [ссылка] | 📱 /qr [текст] | 🔐 /pass [длина]\n"
        "🎲 /rand [min] [max] | 🧮 /calc [выражение]\n"
        "🔄 /text [mode] [текст] | 🔢 /b64 [encode/decode] [текст]\n"
        "🎨 /color [HEX/RGB] | 📊 /stats",
        reply_markup=get_tools_inline()
    )

@dp.message(Command("calc"))
async def cmd_calc(message: types.Message):
    log_command(message.from_user.id, "/calc")
    try:
        expr = message.text.replace("/calc ", "").strip()
        if not expr: await message.answer("❌ /calc 2+2*2", reply_markup=get_retry_keyboard("tool_calc")); return
        if not all(c in "0123456789+-*/(). " for c in expr): await message.answer("❌ Только цифры и + - * / ( )"); return
        result = eval(expr, {"__builtins__": {}}, {})
        await message.answer(f"🧮 <b>Результат:</b>\n<code>{expr} = {result}</code>", reply_markup=get_retry_keyboard("tool_calc"))
    except Exception as e: await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("text"))
async def cmd_text(message: types.Message):
    log_command(message.from_user.id, "/text")
    try:
        parts = message.text.replace("/text ", "").strip().split(maxsplit=1)
        if len(parts) < 2: await message.answer("❌ /text upper привет", reply_markup=get_retry_keyboard("tool_text")); return
        mode, text = parts[0].lower(), parts[1]
        if mode == "upper": result = text.upper()
        elif mode == "lower": result = text.lower()
        elif mode == "reverse": result = text[::-1]
        elif mode == "title": result = text.title()
        else: await message.answer("❌ Режимы: upper, lower, reverse, title"); return
        await message.answer(f"🔄 <b>Результат:</b>\n<code>{result}</code>", reply_markup=get_retry_keyboard("tool_text"))
    except Exception as e: await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("b64"))
async def cmd_b64(message: types.Message):
    log_command(message.from_user.id, "/b64")
    try:
        parts = message.text.replace("/b64 ", "").strip().split(maxsplit=1)
        if len(parts) < 2: await message.answer("❌ /b64 encode текст", reply_markup=get_retry_keyboard("tool_b64")); return
        mode, text = parts[0].lower(), parts[1]
        if mode == "encode": result = base64.b64encode(text.encode()).decode()
        elif mode == "decode": result = base64.b64decode(text.encode()).decode(errors="ignore")
        else: await message.answer("❌ Режимы: encode, decode"); return
        await message.answer(f"🔢 <b>Base64:</b>\n<code>{result}</code>", reply_markup=get_retry_keyboard("tool_b64"))
    except Exception as e: await message.answer(f"❌ Ошибка: <code>{e}</code>")

@dp.message(Command("color"))
async def cmd_color(message: types.Message):
    log_command(message.from_user.id, "/color")
    try:
        val = message.text.replace("/color ", "").strip()
        if not val: await message.answer("❌ /color #FF5733 или 255,87,51", reply_markup=get_retry_keyboard("tool_color")); return
        if val.startswith("#"):
            val = val.lstrip("#")
            if len(val) == 6:
                r, g, b = tuple(int(val[i:i+2], 16) for i in (0, 2, 4))
                await message.answer(f"🎨 <b>HEX → RGB:</b>\n<code>#{val.upper()} = rgb({r}, {g}, {b})</code>", reply_markup=get_retry_keyboard("tool_color"))
            else: await message.answer("❌ HEX: #RRGGBB (6 символов)")
        elif "," in val:
            r, g, b = map(int, [x.strip() for x in val.split(",")])
            if all(0 <= x <= 255 for x in [r, g, b]):
                hex_val = "#{:02X}{:02X}{:02X}".format(r, g, b)
                await message.answer(f"🎨 <b>RGB → HEX:</b>\n<code>rgb({r}, {g}, {b}) = {hex_val}</code>", reply_markup=get_retry_keyboard("tool_color"))
            else: await message.answer("❌ RGB: 0-255")
        else: await message.answer("❌ /color #FF5733 или 255,87,51")
    except Exception as e: await message.answer(f"❌ Ошибка: <code>{e}</code>")

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
        "stats": ("📊 Статистика", "/stats", "Твоя активность"),
        "help": ("ℹ️ Помощь", "/help", "Справка")
    }
    if tool in commands:
        title, cmd, example = commands[tool]
        new_text = f"{title}\n\n<b>Команда:</b> <code>{cmd}</code>\n<i>{example}</i>"
        try: await callback.message.edit_text(new_text, reply_markup=get_tools_inline())
        except: await callback.message.answer(new_text, reply_markup=get_tools_inline())
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
    if not url or url == message.text: await message.answer("❌ /short https://example.com", reply_markup=get_try_keyboard("short", "Попробовать")); return
    if not url.startswith(("http://", "https://")): url = "https://" + url
    msg = await message.answer("⏳ <i>Сокращаю...</i>")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://clck.ru/--?url={url}") as resp:
            if resp.status == 200:
                short = (await resp.text()).strip()
                await msg.edit_text(f"🔗 <b>ГОТОВО!</b>\n\n📎 <code>{url}</code>\n\n✅ {short}", 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Скопировать", url=short)], [InlineKeyboardButton(text="🔄 Ещё", callback_data="tool_short")]]))
            else: await msg.edit_text("❌ Ошибка")

@dp.message(Command("qr"))
async def cmd_qr(message: types.Message):
    log_command(message.from_user.id, "/qr")
    text = message.text.replace("/qr ", "").strip()
    if not text or text == message.text: await message.answer("❌ /qr Привет", reply_markup=get_try_keyboard("qr", "Попробовать")); return
    msg = await message.answer("⏳ <i>Генерирую QR...</i>")
    qr = qrcode.QRCode(version=1, box_size=10, border=4); qr.add_data(text); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    await msg.delete()
    await message.answer_photo(photo=BufferedInputFile(buf.read(), "qr.png"), 
        caption=f"📱 <b>QR готов!</b>\n\n<code>{text[:50]}{'...' if len(text)>50 else ''}</code>", reply_markup=get_retry_keyboard("tool_qr"))

@dp.message(Command("pass"))
async def cmd_pass(message: types.Message):
    log_command(message.from_user.id, "/pass")
    args = message.text.replace("/pass ", "").strip()
    length = int(args) if args and args != message.text else 16
    if not 4 <= length <= 50: await message.answer("❌ Длина: 4-50 символов"); return
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    pwd = ''.join(random.choice(chars) for _ in range(length))
    await message.answer(f"🔐 <b>ПАРОЛЬ:</b>\n\n<code>{pwd}</code>\n\n💡 <i>Скопируй!</i>", reply_markup=get_retry_keyboard("tool_pass"))

@dp.message(Command("rand"))
async def cmd_rand(message: types.Message):
    log_command(message.from_user.id, "/rand")
    args = message.text.replace("/rand ", "").strip().split()
    if len(args) != 2: await message.answer("❌ /rand 1 100", reply_markup=get_try_keyboard("rand", "Попробовать")); return
    a, b = int(args[0]), int(args[1])
    if a >= b: await message.answer("❌ Первое < второго"); return
    result = random.randint(a, b)
    await message.answer(f"🎲 <b>Число:</b>\n\n🎯 <b>{result}</b>\n\n📊 {a} - {b}", reply_markup=get_retry_keyboard("tool_rand"))

# ========== ЗАПУСК ==========
async def main():
    global bot, dp
    web_runner = await start_web_server()
    try:
        bot = create_bot_with_proxy()
        await bot.get_me()
        logger.info(f"✅ Бот @{(await bot.get_me()).username} инициализирован")
    except Exception as e:
        logger.error(f"⚠️ Бот не инициализирован: {e}")
        return
    logger.info("🚀 Starting polling...")
    try: await dp.start_polling(bot)
    finally:
        if bot: await bot.session.close()
        await web_runner.cleanup()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("👋 Остановлен")
    except Exception as e: logger.error(f"💥 Критическая ошибка: {e}"); raise