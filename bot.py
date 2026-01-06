import asyncio 
import json
import os
from datetime import datetime, timedelta

import requests
import matplotlib.pyplot as plt
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types.input_file import BufferedInputFile

# ================== CONFIG ==================
TOKEN = "7612951812:AAHNUkjAaqyOCmJrbgwP2mnST9dTDRfrahc"
ADMIN_ID = 6317061646
ALPHA_API_KEY = "03956EYMTDRM24QT"
CARD_NUMBER = "5168745199251551"

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY"]
TIMEFRAMES = ["5min", "10min", "15min"]

DB_FILE = "users.json"
# ============================================

bot = Bot(TOKEN)
dp = Dispatcher()

# ================== DB ==================
def load_users():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def has_access(user_id: int):
    if user_id == ADMIN_ID:
        return True
    users = load_users()
    user = users.get(str(user_id))
    if not user:
        return False
    if user.get("pending"):
        return False
    exp = user.get("expires")
    if not exp:
        return False
    return datetime.fromisoformat(exp) > datetime.now()

def give_access(user_id: int, days=7):
    users = load_users()
    expires = datetime.now() + timedelta(days=days)
    users[str(user_id)] = {"expires": expires.isoformat()}
    save_users(users)

# ================== SIGNAL ==================
def get_signal(symbol: str, interval: str):
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "RSI",
        "symbol": symbol.replace("/", ""),
        "interval": interval,
        "time_period": 14,
        "series_type": "close",
        "apikey": ALPHA_API_KEY
    }
    r = requests.get(url, params=params, timeout=10).json()
    data = r.get("Technical Analysis: RSI")
    if not data:
        return None, None

    last_time = list(data.keys())[0]
    rsi = float(data[last_time]["RSI"])

    if rsi < 30:
        return "BUY", rsi
    elif rsi > 70:
        return "SELL", rsi
    else:
        return "WAIT", rsi

def draw_chart(symbol, rsi, action):
    plt.figure(figsize=(4, 3))
    plt.bar(["RSI"], [rsi])
    plt.axhline(30, color="green", linestyle="--")
    plt.axhline(70, color="red", linestyle="--")
    plt.title(f"{symbol} | {action}")
    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf.read()

# ================== KEYBOARDS ==================
def main_menu(user_id: int):
    if user_id == ADMIN_ID:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📊 Отримати сигнал")],
                [KeyboardButton(text="🛠 Адмін панель")]
            ],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📊 Отримати сигнал")]],
        resize_keyboard=True
    )

def pay_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Я оплатив")]],
        resize_keyboard=True
    )

def pairs_keyboard():
    kb = InlineKeyboardBuilder()
    for p in PAIRS:
        kb.button(text=p, callback_data=f"pair:{p}")
    kb.adjust(1)
    return kb.as_markup()

def timeframe_keyboard(pair):
    kb = InlineKeyboardBuilder()
    for tf in TIMEFRAMES:
        kb.button(text=tf, callback_data=f"tf:{pair}:{tf}")
    kb.adjust(3)
    return kb.as_markup()

# ================== START ==================
@dp.message(Command("start"))
async def start(msg: Message):
    if has_access(msg.from_user.id):
        await msg.answer("📊 Обери дію:", reply_markup=main_menu(msg.from_user.id))
        return

    text = (
        "📈 *Forex Signals Bot*\n\n"
        "💳 Доступ:\n"
        "7 днів — 150 грн\n\n"
        f"🏦 ПриватБанк:\n`{CARD_NUMBER}`\n\n"
        "Після оплати натисни кнопку 👇"
    )
    await msg.answer(text, reply_markup=pay_keyboard(), parse_mode="Markdown")

# ================== PAYMENT ==================
@dp.message(F.text == "✅ Я оплатив")
async def paid(msg: Message):
    users = load_users()
    users[str(msg.from_user.id)] = {"pending": True}
    save_users(users)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Надати доступ",
                callback_data=f"approve:{msg.from_user.id}"
            )
        ]]
    )

    await bot.send_message(
        ADMIN_ID,
        f"💰 Оплата від {msg.from_user.full_name} ({msg.from_user.id})",
        reply_markup=kb
    )
    await msg.answer("⏳ Оплату прийнято. Чекай підтвердження.")

# ================== APPROVE ==================
@dp.callback_query(F.data.startswith("approve:"))
async def approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    uid = call.data.split(":")[1]
    give_access(int(uid))

    await bot.send_message(
        int(uid),
        "✅ Доступ активовано!",
        reply_markup=main_menu(int(uid))
    )
    await call.message.edit_text("✅ Доступ надано")

# ================== USER FLOW ==================
@dp.message(F.text == "📊 Отримати сигнал")
async def choose_pair(msg: Message):
    if not has_access(msg.from_user.id):
        await msg.answer("❌ Немає доступу")
        return
    await msg.answer("🔽 Обери валютну пару:", reply_markup=pairs_keyboard())

@dp.callback_query(F.data.startswith("pair:"))
async def choose_tf(call: CallbackQuery):
    pair = call.data.split(":")[1]
    await call.message.edit_text(
        f"⏱ Обери таймфрейм для {pair}:",
        reply_markup=timeframe_keyboard(pair)
    )

@dp.callback_query(F.data.startswith("tf:"))
async def send_signal(call: CallbackQuery):
    _, pair, tf = call.data.split(":")
    action, rsi = get_signal(pair, tf)
    if not action:
        await call.answer("Дані недоступні", show_alert=True)
        return

    img = draw_chart(pair, rsi, action)
    photo = BufferedInputFile(img, filename="signal.png")

    text = (
        f"📊 {pair}\n"
        f"⏱ {tf}\n"
        f"RSI: {round(rsi,2)}\n\n"
        f"{'🟢 ВГОРУ (BUY)' if action=='BUY' else '🔴 ВНИЗ (SELL)' if action=='SELL' else '⚪ WAIT'}"
    )

    await bot.send_photo(
        call.from_user.id,
        photo=photo,
        caption=text,
        reply_markup=pairs_keyboard()
    )

# ================== ADMIN PANEL ==================
@dp.message(F.text == "🛠 Адмін панель")
async def admin_panel(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    users = load_users()
    text = "👑 Адмін панель\n\nАктивні користувачі:\n"
    for uid, u in users.items():
        exp = u.get("expires", "❌")
        text += f"- {uid}: до {exp}\n"
    await msg.answer(text)

# ================== AUTO BLOCK ==================
async def auto_block():
    while True:
        users = load_users()
        changed = False
        for uid, u in users.items():
            exp = u.get("expires")
            if exp and datetime.fromisoformat(exp) <= datetime.now():
                u["pending"] = True
                changed = True
        if changed:
            save_users(users)
        await asyncio.sleep(3600)

# ================== MAIN ==================
async def main():
    asyncio.create_task(auto_block())
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

