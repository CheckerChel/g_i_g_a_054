import os
import random
import threading
import time
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

token = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(token)
CHATS = [-1003724538567, 7163427034]
LOCKS = {}
ADMINS=[7163427034]


class Filter(telebot.SimpleCustomFilter):
    key = "imc"
    def check(self, obj):
        if isinstance(obj, telebot.types.Message):
            return obj.chat.id in CHATS
        if isinstance(obj, telebot.types.CallbackQuery):
            return obj.message.chat.id in CHATS
        return False
bot.add_custom_filter(Filter())


os.makedirs("data", exist_ok=True)
DB_PATH = "data/wow.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
		CREATE TABLE IF NOT EXISTS Users (
			bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
			real_id INTEGER NOT NULL,
			coins INTEGER DEFAULT 0,
			time INTEGER DEFAULT 0
		)
		""")
        conn.commit()


def check(id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Users WHERE real_id = ?", (id,))
        user = cursor.fetchone()
        if user is None:
            cursor.execute("INSERT INTO Users (real_id) VALUES (?)", (id,))
            conn.commit()


def get_user_data(field, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT bot_id, real_id, coins, time FROM Users WHERE {field} = ?", (value,))
        return cursor.fetchone()


@bot.message_handler(imc=True, func=lambda m: m.from_user.id in ADMINS and m.text and m.text.lower().startswith('+ж '))
def admin_add_coins(message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return
    amount = int(args[1])
    target_user = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        target_user = get_user_data("real_id", message.from_user.id)
    if not target_user:
        return
    bot_id, real_id, coins, time_val = target_user
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (amount, bot_id))
        conn.commit()
    mention = f'<a href="https://telegram.me/{real_id}">#{bot_id}</a>'
    bot.reply_to(message, f"Выдано {amount}Ж на {mention}", parse_mode="HTML")


@bot.message_handler(imc=True, func=lambda m: m.from_user.id in ADMINS and m.text and m.text.lower().startswith('-ж '))
def admin_remove_coins(message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return
    amount = int(args[1])
    target_user = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        target_user = get_user_data("real_id", message.from_user.id)
    if not target_user:
        return
    bot_id, real_id, coins, time_val = target_user
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (amount, bot_id))
        conn.commit()
    mention = f'<a href="https://telegram.me/{real_id}">#{bot_id}</a>'
    bot.reply_to(message, f"Отобрано {amount}Ж у {mention}", parse_mode="HTML")


@bot.message_handler(imc=True, func=lambda m: m.from_user.id in ADMINS and m.text and m.text.lower().startswith('-кд'))
def admin_reset_cooldown(message):
    args = message.text.split()
    target_user = None
    if len(args) > 1:
        t_id = args[1].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        target_user = get_user_data("real_id", message.from_user.id)
    if not target_user:
        return
    bot_id, real_id, coins, time_val = target_user
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET time = 0 WHERE bot_id = ?", (bot_id,))
        conn.commit()
    mention = f'<a href="https://telegram.me/{real_id}">#{bot_id}</a>'
    bot.reply_to(message, f"Сброшен КД у {mention}", parse_mode="HTML")


@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() == "бонус")
def get_bonus(message):
    user_id = message.from_user.id
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
    if not LOCKS[user_id].acquire(blocking=False):
        return
    try:
        check(user_id)
        current_time = int(time.time())
        user_data = get_user_data("real_id", user_id)
        if not user_data:
            return
        bot_id, real_id, coins, last_time = user_data
        cooldown = 6 * 3600
        if current_time - last_time < cooldown:
            remains = cooldown - (current_time - last_time)
            hours = remains // 3600
            mins = (remains % 3600) // 60
            secs = remains % 60
            bot.reply_to(message, f"⏳Подожди ещё:\n{hours}ч. {mins}мин. {secs}сек.")
            return
        bonus = random.randint(100, 500)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = coins + ?, time = ? WHERE real_id = ?", (bonus, current_time, user_id))
            conn.commit()
        bot.reply_to(message, f"🎁Вам даровано {bonus}Ж, возвращайтесь через 6 часов")
    finally:
        LOCKS[user_id].release()


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() in ['проф'] or m.text.lower().startswith('проф ')))
def show_profile(message):
    target_user = None
    is_invalid_format = False
    args = message.text.split(maxsplit=1)
    if message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
    elif len(args) > 1:
        t_id_raw = args[1]
        t_id = t_id_raw.replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
        else:
            is_invalid_format = True
    else:
        check(message.from_user.id)
        target_user = get_user_data("real_id", message.from_user.id)
    if is_invalid_format:
        bot.reply_to(message, "Правильный формат:\nпроф #айди")
        return
    if not target_user:
        bot.reply_to(message, "Пользователь не найден")
        return
    bot_id, real_id, coins, last_time = target_user
    mention = f'<a href="https://telegram.me/{real_id}">#{bot_id}</a>'
    text = f"👤{mention}\n💰Жетонов: {coins}Ж"
    current_time = int(time.time())
    cooldown = 6 * 3600
    if current_time - last_time < cooldown and last_time != 0:
        remains = cooldown - (current_time - last_time)
        hours = remains // 3600
        mins = (remains % 3600) // 60
        secs = remains % 60
        text += f"\n\n⏳До окончания КД:\n{hours}ч. {mins}мин. {secs}сек."
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() == 'дать' or m.text.lower().startswith('дать ')))
def request_transfer(message):
    args = message.text.split()
    if len(args) == 1:
        bot.reply_to(message, "Правильный формат:\nдать [сумма] #айди")
        return
    if len(args) < 2 or not args[1].isdigit():
        return
    amount = int(args[1])
    if amount <= 0:
        return
    check(message.from_user.id)
    sender = get_user_data("real_id", message.from_user.id)
    if not sender:
        return
    if sender[2] < amount:
        bot.reply_to(message, "Недостаточно средств")
        return
    target_user = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        bot.reply_to(message, "Правильный формат:\nдать [сумма] #айди")
        return
    if not target_user:
        bot.reply_to(message, "Пользователь не найден")
        return
    if sender[0] == target_user[0]:
        return
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton(text="✅Подтвердить", callback_data=f"pay_{sender[0]}_{target_user[0]}_{amount}", style="success")
    markup.add(btn)
    mention = f'<a href="https://telegram.me/{target_user[1]}">#{target_user[0]}</a>'
    bot.reply_to(message, f"Вы уверены, что хотите передать {amount}Ж на {mention}?", parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def confirm_transfer(call):
    _, s_bot_id_str, t_bot_id_str, amount_str = call.data.split("_")
    s_bot_id, t_bot_id, amount = int(s_bot_id_str), int(t_bot_id_str), int(amount_str)
    sender = get_user_data("bot_id", s_bot_id)
    if not sender:
        bot.answer_callback_query(call.id, "Вы не зарегистрированы в системе", show_alert=True)
        return
    if call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id, "Это не ваша операция", show_alert=True)
        return
    if s_bot_id not in LOCKS:
        LOCKS[s_bot_id] = threading.Lock()
    if not LOCKS[s_bot_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins FROM Users WHERE bot_id = ?", (s_bot_id,))
            res = cursor.fetchone()
            if not res or res[0] < amount:
                bot.answer_callback_query(call.id)
                try:
                    bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return
            bot.answer_callback_query(call.id)
            cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (amount, s_bot_id))
            cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (amount, t_bot_id))
            conn.commit()
        target = get_user_data("bot_id", t_bot_id)
        s_mention = f'<a href="https://telegram.me/{sender[1]}">#{s_bot_id}</a>'
        t_mention = f'<a href="https://telegram.me/{target[1]}">#{t_bot_id}</a>'
        new_text = f"{s_mention} перевёл {amount}Ж на {t_mention}"
        try:
            bot.edit_message_text(new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass
    finally:
        LOCKS[s_bot_id].release()


@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() in ['лидер', 'лидеры'])
def show_leaderboard(message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_id, real_id, coins FROM Users WHERE coins > 0 ORDER BY coins DESC, bot_id ASC LIMIT 20")
        leaders = cursor.fetchall()
    if not leaders:
        bot.reply_to(message, "Топ лидеров отсутствует")
        return
    text = "👑<b>Топ-20 лидеров</b>\n\n"
    for idx, (bot_id, real_id, coins) in enumerate(leaders, 1):
        mention = f'<a href="https://telegram.me/{real_id}">#{bot_id}</a>'
        text += f"• {idx}. {mention} — {coins}Ж\n"
    bot.send_message(chat_id=message.chat.id, text=text, parse_mode="HTML")


# ИГРЫ ИГРЫ ИГРЫ

# ИГРЫ ИГРЫ ИГРЫ

# ИГРЫ ИГРЫ ИГРЫ





if __name__ == "__main__":
    init_db()
    print("есть")
    bot.infinity_polling()