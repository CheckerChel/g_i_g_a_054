import os
import random
import threading
import time
import sqlite3
import telebot
from decimal import ROUND_DOWN, Decimal
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
			coins REAL DEFAULT 0,
			time INTEGER DEFAULT 0,
			wins INTEGER DEFAULT 0,
			losses INTEGER DEFAULT 0
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
        cursor.execute(f"SELECT bot_id, real_id, coins, time, wins, losses FROM Users WHERE {field} = ?", (value,))
        return cursor.fetchone()


@bot.message_handler(imc=True, func=lambda m: m.from_user.id in ADMINS and m.text and (m.text.startswith('+$') or m.text.startswith('-$')))
def admin_modify_coins(message):
    args = message.text.split(maxsplit=1)
    command = args[0]
    is_add = command.startswith('+$')
    
    amount_str = command[2:]
    if not amount_str:
        return
        
    try:
        amount = Decimal(amount_str).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    except Exception:
        return
        
    if amount <= 0:
        return

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
        
    bot_id, real_id, coins_val, time_val, _, _ = target_user
    current_coins = Decimal(str(coins_val or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    if is_add:
        new_coins = current_coins + amount
    else:
        if amount > current_coins:
            bot.reply_to(message, f"Максимум: {current_coins}$")
            return
        new_coins = current_coins - amount
        
    new_coins_float = float(new_coins)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_coins_float, bot_id))
        conn.commit()
        
    action_text = f"🎩Выдано {amount}" if is_add else f"🎩Отобрано {amount}"
    bot.reply_to(message, f"{action_text}$ — #{bot_id}")


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
    bot_id, real_id, coins, time_val, _, _ = target_user
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET time = 0 WHERE bot_id = ?", (bot_id,))
        conn.commit()
    bot.reply_to(message, f"<b>Сброшен КД у {bot_id}</b>", parse_mode="HTML")


@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() == "бонус")
def get_bonus(message):
    user_id = message.from_user.id
    
    # Исправленная инициализация блокировки:
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
            
        # Добавили _, _ в конец для успешного принятия 6 значений от get_user_data
        bot_id, real_id, coins, last_time, _, _ = user_data
        cooldown = 6 * 3600
        
        if current_time - last_time < cooldown:
            remains = cooldown - (current_time - last_time)
            hours = remains // 3600
            mins = (remains % 3600) // 60
            secs = remains % 60
            bot.reply_to(message, f"⏳Подожди ещё:\n{hours}ч. {mins}мин. {secs}сек.")
            return
        
        bonus_raw = random.uniform(0.05, 0.1)
        bonus = Decimal(str(bonus_raw)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        
        current_coins = Decimal(str(coins or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        new_coins = float(current_coins + bonus)
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = ?, time = ? WHERE real_id = ?", (new_coins, current_time, user_id))
            conn.commit()
        bot.reply_to(message, f"🎁Вам даровано {bonus}$, возвращайтесь через 6 часов")
    finally:
        LOCKS[user_id].release()


def get_user_data(field, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT bot_id, real_id, coins, time, wins, losses FROM Users WHERE {field} = ?", (value,))
        return cursor.fetchone()


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() == 'проф' or m.text.lower().startswith('проф ')))
def show_profile(message):
    target_user = None
    is_invalid_format = False
    args = message.text.split(maxsplit=1)
    
    if message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
        name = message.reply_to_message.from_user.first_name
    elif len(args) > 1:
        t_id_raw = args[1]
        t_id = t_id_raw.replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
            name = f"User #{t_id}"
        else:
            is_invalid_format = True
    else:
        check(message.from_user.id)
        target_user = get_user_data("real_id", message.from_user.id)
        name = message.from_user.first_name
        
    if is_invalid_format:
        bot.reply_to(message, "Правильный формат:\nпроф #айди")
        return
    if not target_user:
        bot.reply_to(message, "Пользователь не найден")
        return
        
    bot_id, real_id, coins_val, last_time, wins, losses = target_user
    coins_dec = Decimal(str(coins_val or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    text = f"👤{name}\n🆔 #{bot_id} | <b>${coins_dec}</b>\n🌹{wins} | {losses}🥀"
    
    current_time = int(time.time())
    cooldown = 6 * 3600
    if current_time - last_time < cooldown and last_time != 0:
        remains = cooldown - (current_time - last_time)
        hours = remains // 3600
        mins = (remains % 3600) // 60
        secs = remains % 60
        text += f"\n\n<b>До окончания КД:</b>\n⏳{hours}ч. {mins}м. {secs}с."
        
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() == 'дать' or m.text.lower().startswith('дать ')))
def request_transfer(message):
    args = message.text.split()
    if len(args) == 1:
        bot.reply_to(message, "Правильный формат:\nдать [сумма] #айди")
        return
    if len(args) < 2:
        return
        
    amount_raw = args[1]
    try:
        amount_dec = Decimal(amount_raw)
        if amount_dec.as_tuple().exponent < -2:
            bot.reply_to(message, "Поддерживаются числа только формата 0.00")
            return
        amount = amount_dec.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    except Exception:
        return
        
    if amount <= 0:
        return
        
    check(message.from_user.id)
    sender = get_user_data("real_id", message.from_user.id)
    if not sender:
        return
        
    sender_coins = Decimal(str(sender[2] or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    if sender_coins < amount:
        bot.reply_to(message, "Недостаточно средств")
        return
        
    target_user = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
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
    bot.reply_to(message, f"Вы уверены, что хотите передать ${amount} на #{target_user[0]}?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def confirm_transfer(call):
    _, s_bot_id_str, t_bot_id_str, amount_str = call.data.split("_")
    s_bot_id, t_bot_id = int(s_bot_id_str), int(t_bot_id_str)
    amount = Decimal(amount_str).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
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
            if not res:
                bot.answer_callback_query(call.id)
                return
                
            sender_coins = Decimal(str(res[0] or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            if sender_coins < amount:
                bot.answer_callback_query(call.id)
                try:
                    bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return
                
            bot.answer_callback_query(call.id)
            
            cursor.execute("SELECT coins FROM Users WHERE bot_id = ?", (t_bot_id,))
            t_res = cursor.fetchone()
            target_coins = Decimal(str(t_res[0] or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            
            new_sender_coins = float(sender_coins - amount)
            new_target_coins = float(target_coins + amount)
            
            cursor.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_sender_coins, s_bot_id))
            cursor.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_target_coins, t_bot_id))
            conn.commit()
            
        new_text = f"💸 #{s_bot_id} перевёл ${amount} на #{t_bot_id}"
        try:
            bot.edit_message_text(new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass
    finally:
        LOCKS[s_bot_id].release()


@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() in ['лидер', 'лидеры'])
def show_leaderboard(message):
    check(message.from_user.id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_id, coins FROM Users WHERE coins > 0 ORDER BY coins DESC, bot_id ASC LIMIT 20")
        leaders = cursor.fetchall()
        
    if not leaders:
        bot.reply_to(message, "Топ лидеров отсутствует")
        return
        
    text = "👑<b>Топ-20 лидеров</b>\n\n"
    for idx, (bot_id, coins_val) in enumerate(leaders, 1):
        coins_dec = Decimal(str(coins_val or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        
        coins_str = f"{coins_dec:g}"
        text += f"• {idx}. #{bot_id} — {coins_str}$\n"
    bot.send_message(chat_id=message.chat.id, text=text, parse_mode="HTML")


# ИГРЫ ИГРЫ ИГРЫ

# ИГРЫ ИГРЫ ИГРЫ

# ИГРЫ ИГРЫ ИГРЫ


def get_game_keyboard(amount, selected_main):
    markup = InlineKeyboardMarkup()
    
    b1_style = "primary" if selected_main == "1" else None
    b2_style = "primary" if selected_main == "2" else None
    b3_style = "primary" if selected_main.startswith("3") else None
    
    markup.row(
        InlineKeyboardButton("1 бросок", callback_data=f"game_menu_1_{amount}", style=b1_style),
        InlineKeyboardButton("2 броска", callback_data=f"game_menu_2_{amount}", style=b2_style),
        InlineKeyboardButton("3 броска", callback_data=f"game_menu_3_{amount}", style=b3_style)
    )
    
    if selected_main == "1":
        markup.row(
            InlineKeyboardButton("Больше (х2)", callback_data=f"game_play_1_big_{amount}"),
            InlineKeyboardButton("Меньше (х2)", callback_data=f"game_play_1_small_{amount}")
        )
        markup.row(
            InlineKeyboardButton("Чётное (х2)", callback_data=f"game_play_1_even_{amount}"),
            InlineKeyboardButton("Нечётное (х2)", callback_data=f"game_play_1_odd_{amount}")
        )
        markup.row(
            InlineKeyboardButton("1 (х6)", callback_data=f"game_play_1_num1_{amount}"),
            InlineKeyboardButton("2 (х6)", callback_data=f"game_play_1_num2_{amount}"),
            InlineKeyboardButton("3 (х6)", callback_data=f"game_play_1_num3_{amount}")
        )
        markup.row(
            InlineKeyboardButton("4 (х6)", callback_data=f"game_play_1_num4_{amount}"),
            InlineKeyboardButton("5 (х6)", callback_data=f"game_play_1_num5_{amount}"),
            InlineKeyboardButton("6 (х6)", callback_data=f"game_play_1_num6_{amount}")
        )
        
    elif selected_main == "2":
        markup.row(
            InlineKeyboardButton("Оба больше (х4)", callback_data=f"game_play_2_bothbig_{amount}"),
            InlineKeyboardButton("Оба меньше (х4)", callback_data=f"game_play_2_bothsmall_{amount}")
        )
        markup.row(
            InlineKeyboardButton("Оба чётные (х4)", callback_data=f"game_play_2_botheven_{amount}"),
            InlineKeyboardButton("Оба нечёт (х4)", callback_data=f"game_play_2_bothodd_{amount}")
        )
        markup.row(
            InlineKeyboardButton("№1 > №2 (х2.4)", callback_data=f"game_play_2_1gt2_{amount}"),
            InlineKeyboardButton("№2 > №1 (х2.4)", callback_data=f"game_play_2_2gt1_{amount}")
        )
        markup.row(
            InlineKeyboardButton("Лесенка вверх (х2.4)", callback_data=f"game_play_2_ladderup_{amount}"),
            InlineKeyboardButton("Лесенка вниз (х2.4)", callback_data=f"game_play_2_ladderdown_{amount}")
        )
        markup.row(
            InlineKeyboardButton("Любая лесенка (х1.2)", callback_data=f"game_play_2_anyladder_{amount}"),
            InlineKeyboardButton("Любой дубль (х6)", callback_data=f"game_play_2_anydouble_{amount}")
        )
        markup.row(
            InlineKeyboardButton("1 (х36)", callback_data=f"game_play_2_num1_{amount}"),
            InlineKeyboardButton("2 (х36)", callback_data=f"game_play_2_num2_{amount}"),
            InlineKeyboardButton("3 (х36)", callback_data=f"game_play_2_num3_{amount}")
        )
        markup.row(
            InlineKeyboardButton("4 (х36)", callback_data=f"game_play_2_num4_{amount}"),
            InlineKeyboardButton("5 (х36)", callback_data=f"game_play_2_num5_{amount}"),
            InlineKeyboardButton("6 (х36)", callback_data=f"game_play_2_num6_{amount}")
        )
    elif selected_main.startswith("3"):
        current_sub = "std" if selected_main in ["3", "3_std"] else "lad"
        std_style = "primary" if current_sub == "std" else None
        lad_style = "primary" if current_sub == "lad" else None
        
        markup.row(
            InlineKeyboardButton("Стандарт", callback_data=f"game_menu_3_std_{amount}", style=std_style),
            InlineKeyboardButton("Лесенка", callback_data=f"game_menu_3_lad_{amount}", style=lad_style)
        )
        
        if current_sub == "std":
            markup.row(
                InlineKeyboardButton("Трое больше (х8)", callback_data=f"game_play_3_allbig_{amount}"),
                InlineKeyboardButton("Трое меньше (х8)", callback_data=f"game_play_3_allsmall_{amount}")
            )
            markup.row(
                InlineKeyboardButton("Трое чётные (х8)", callback_data=f"game_play_3_alleven_{amount}"),
                InlineKeyboardButton("Трое нечёт (х8)", callback_data=f"game_play_3_allodd_{amount}")
            )
            markup.row(
                InlineKeyboardButton("Любой дубль (х2.4)", callback_data=f"game_play_3_anydouble_{amount}"),
                InlineKeyboardButton("Любой трипл (х36)", callback_data=f"game_play_3_anytriple_{amount}")
            )
            markup.row(
                InlineKeyboardButton("1 (х216)", callback_data=f"game_play_3_num1_{amount}"),
                InlineKeyboardButton("2 (х216)", callback_data=f"game_play_3_num2_{amount}"),
                InlineKeyboardButton("3 (х216)", callback_data=f"game_play_3_num3_{amount}")
            )
            markup.row(
                InlineKeyboardButton("4 (х216)", callback_data=f"game_play_3_num4_{amount}"),
                InlineKeyboardButton("5 (х216)", callback_data=f"game_play_3_num5_{amount}"),
                InlineKeyboardButton("6 (х216)", callback_data=f"game_play_3_num6_{amount}")
            )
        else:
            markup.row(
                InlineKeyboardButton("Лесенка вверх (х10.8)", callback_data=f"game_play_3_ladderup_{amount}"),
                InlineKeyboardButton("Лесенка вниз (х10.8)", callback_data=f"game_play_3_ladderdown_{amount}")
            )
            markup.row(
                InlineKeyboardButton("Любая лесенка (х5.4)", callback_data=f"game_play_3_anyladder_{amount}")
            )

    markup.row(InlineKeyboardButton("Отказаться", callback_data=f"game_cancel_{amount}", style="danger"))
    return markup


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.strip() == "$" or m.text.strip().startswith("$")))
def init_game_dice(message):
    check(message.from_user.id)
    text = message.text.strip()
    
    if text == "$":
        bot.reply_to(message, "Правильный формат:\n${сумма}")
        return
        
    amount_str = text[1:].strip()
    
    if " " in amount_str or amount_str.startswith("-"):
        return
        
    try:
        amount_dec = Decimal(amount_str)
        if amount_dec.as_tuple().exponent < -2:
            return
        amount = amount_dec.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    except Exception:
        return
        
    if amount <= 0:
        return
        
    if amount < Decimal('0.03'):
        bot.reply_to(message, "Минимальная ставка — $0.03")
        return
        
    user_data = get_user_data("real_id", message.from_user.id)
    if not user_data or Decimal(str(user_data[2] or 0)) < amount:
        bot.reply_to(message, "Недостаточно средств")
        return
        
    name = message.from_user.first_name
    markup = get_game_keyboard(amount=amount, selected_main="none")
    
    sent_msg = bot.reply_to(
        message, 
        f"{name}, выберите исход.\nСтавка: ${amount}", 
        reply_markup=markup
    )
    
    GAME_SESSIONS[sent_msg.message_id] = {
        "user_id": message.from_user.id,
        "amount": amount,
        "lock": threading.Lock()
    }


@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def handle_game_clicks(call):
    msg_id = call.message.message_id
    if msg_id not in GAME_SESSIONS:
        bot.answer_callback_query(call.id)
        return
        
    session = GAME_SESSIONS[msg_id]
    
    if call.from_user.id != session["user_id"]:
        bot.answer_callback_query(call.id)
        return
        
    if not session["lock"].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return
        
    try:
        user_data = get_user_data("real_id", call.from_user.id)
        if not user_data or Decimal(str(user_data or 0)) < session["amount"]:
            bot.answer_callback_query(call.id, "Недостаточно средств", show_alert=True)
            try:
                bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=msg_id, reply_markup=None)
            except Exception: pass
            GAME_SESSIONS.pop(msg_id, None)
            return

        data_parts = call.data.split("_")
        action = data_parts
        
        if action == "cancel":
            bot.answer_callback_query(call.id)
            name = call.from_user.first_name
            try:
                bot.edit_message_text(f"🤚{name} <b>отказался от игры</b>", chat_id=call.message.chat.id, message_id=msg_id, parse_mode="HTML", reply_markup=None)
            except Exception: pass
            GAME_SESSIONS.pop(msg_id, None)
            return
            
        if action == "menu":
            bot.answer_callback_query(call.id)
            selected = data_parts
            if len(data_parts) == 5 and data_parts in ["std", "lad"]:
                selected = f"3_{data_parts}"
                
            markup = get_game_keyboard(amount=session["amount"], selected_main=selected)
            try:
                bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=msg_id, reply_markup=markup)
            except Exception: pass
            return
        if action == "play":
            bot.answer_callback_query(call.id)
            try:
                bot.delete_message(chat_id=call.message.chat.id, message_id=msg_id)
            except Exception: pass
            GAME_SESSIONS.pop(msg_id, None)
            
            dice_count = int(data_parts[2])
            choice_type = data_parts[3]
            amount = session["amount"]
            
            # ОТПРАВЛЯЕМ НАСТОЯЩИЕ АНИМИРОВАННЫЕ КУБИКИ ТЕЛЕГРАМА
            rolls = []
            for _ in range(dice_count):
                res = bot.send_dice(chat_id=call.message.chat.id, emoji="🎲")
                rolls.append(res.dice.value) # Телеграм сам возвращает число от 1 до 6
                
            is_win = False
            coef = Decimal('0')
            readable_choice = ""
            
            if dice_count == 1:
                r1 = rolls[0]
                if choice_type == "big":
                    is_win = (r1 > 3)
                    coef, readable_choice = Decimal('2'), "Больше"
                elif choice_type == "small":
                    is_win = (r1 < 4)
                    coef, readable_choice = Decimal('2'), "Меньше"
                elif choice_type == "even":
                    is_win = (r1 % 2 == 0)
                    coef, readable_choice = Decimal('2'), "Чётное"
                elif choice_type == "odd":
                    is_win = (r1 % 2 != 0)
                    coef, readable_choice = Decimal('2'), "Нечётное"
                elif choice_type.startswith("num"):
                    target = int(choice_type[3:])
                    is_win = (r1 == target)
                    coef, readable_choice = Decimal('6'), str(target)
                    
            elif dice_count == 2:
                r1, r2 = rolls[0], rolls[1]
                if choice_type == "bothbig":
                    is_win = (r1 > 3 and r2 > 3)
                    coef, readable_choice = Decimal('4'), "Оба больше"
                elif choice_type == "bothsmall":
                    is_win = (r1 < 4 and r2 < 4)
                    coef, readable_choice = Decimal('4'), "Оба меньше"
                elif choice_type == "botheven":
                    is_win = (r1 % 2 == 0 and r2 % 2 == 0)
                    coef, readable_choice = Decimal('4'), "Оба чётные"
                elif choice_type == "bothodd":
                    is_win = (r1 % 2 != 0 and r2 % 2 != 0)
                    coef, readable_choice = Decimal('4'), "Оба нечёт"
                elif choice_type == "1gt2":
                    is_win = (r1 > r2)
                    coef, readable_choice = Decimal('2.4'), "№1 > №2"
                elif choice_type == "2gt1":
                    is_win = (r2 > r1)
                    coef, readable_choice = Decimal('2.4'), "№2 > №1"
                elif choice_type == "ladderup":
                    is_win = (r1 < r2)
                    coef, readable_choice = Decimal('2.4'), "Лесенка вверх"
                elif choice_type == "ladderdown":
                    is_win = (r1 > r2)
                    coef, readable_choice = Decimal('2.4'), "Лесенка вниз"
                elif choice_type == "anyladder":
                    is_win = (r1 != r2)
                    coef, readable_choice = Decimal('1.2'), "Любая лесенка"
                elif choice_type == "anydouble":
                    is_win = (r1 == r2)
                    coef, readable_choice = Decimal('6'), "Любой дубль"
                elif choice_type.startswith("num"):
                    target = int(choice_type[3:])
                    is_win = (r1 == target or r2 == target)
                    coef, readable_choice = Decimal('36'), str(target)
                    
            elif dice_count == 3:
                r1, r2, r3 = rolls[0], rolls[1], rolls[2]
                if choice_type == "allbig":
                    is_win = (r1 > 3 and r2 > 3 and r3 > 3)
                    coef, readable_choice = Decimal('8'), "Трое больше"
                elif choice_type == "allsmall":
                    is_win = (r1 < 4 and r2 < 4 and r3 < 4)
                    coef, readable_choice = Decimal('8'), "Трое меньше"
                elif choice_type == "alleven":
                    is_win = (r1 % 2 == 0 and r2 % 2 == 0 and r3 % 2 == 0)
                    coef, readable_choice = Decimal('8'), "Трое чётные"
                elif choice_type == "allodd":
                    is_win = (r1 % 2 != 0 and r2 % 2 != 0 and r3 % 2 != 0)
                    coef, readable_choice = Decimal('8'), "Трое нечёт"
                elif choice_type == "anydouble":
                    is_win = (r1 == r2 or r2 == r3 or r1 == r3)
                    coef, readable_choice = Decimal('2.4'), "Любой дубль"
                elif choice_type == "anytriple":
                    is_win = (r1 == r2 == r3)
                    coef, readable_choice = Decimal('36'), "Любой трипл"
                elif choice_type == "ladderup":
                    is_win = (r1 < r2 < r3)
                    coef, readable_choice = Decimal('10.8'), "Лесенка вверх"
                elif choice_type == "ladderdown":
                    is_win = (r1 > r2 > r3)
                    coef, readable_choice = Decimal('10.8'), "Лесенка вниз"
                elif choice_type == "anyladder":
                    is_win = (r1 < r2 < r3 or r1 > r2 > r3)
                    coef, readable_choice = Decimal('5.4'), "Любая лесенка"
                elif choice_type.startswith("num"):
                    target = int(choice_type[3:])
                    is_win = (r1 == target or r2 == target or r3 == target)
                    coef, readable_choice = Decimal('216'), str(target)

            with DICE_PROCESSING_LOCK:
                user_check = get_user_data("real_id", call.from_user.id)
                if not user_check or Decimal(str(user_check[2] or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN) < amount:
                    bot.send_message(chat_id=call.message.chat.id, text="Недостаточно средств")
                    return
                    
                bot_id, real_id, current_db_coins, _, db_wins, db_losses = user_check
                current_balance = Decimal(str(current_db_coins or 0)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                name = call.from_user.first_name
                
                if is_win:
                    net_profit = (amount * coef - amount).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                    final_coins = float(current_balance + net_profit)
                    new_wins = db_wins + 1
                    
                    with sqlite3.connect(DB_PATH) as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE Users SET coins = ?, wins = ? WHERE bot_id = ?", (final_coins, new_wins, bot_id))
                        conn.commit()
                        
                    res_coins_str = f"{Decimal(str(final_coins)):g}"
                    bot.send_message(
                        chat_id=call.message.chat.id,
                        text=f"🌹{name} <b>выиграл {net_profit}$!</b>\n"
                             f"Ставка: {amount}$ на {readable_choice}\n"
                             f"🆔 #{bot_id} | <b>{res_coins_str}$</b>",
                        parse_mode="HTML"
                    )
                else:
                    final_coins = float(current_balance - amount)
                    new_losses = db_losses + 1
                    
                    with sqlite3.connect(DB_PATH) as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE Users SET coins = ?, losses = ? WHERE bot_id = ?", (final_coins, new_losses, bot_id))
                        conn.commit()
                        
                    res_coins_str = f"{Decimal(str(final_coins)):g}"
                    bot.send_message(
                        chat_id=call.message.chat.id,
                        text=f"🥀{name} <b>проиграл {amount}$!</b>\n"
                             f"Ставка: {amount}$ на {readable_choice}\n"
                             f"🆔 #{bot_id} | <b>{res_coins_str}$</b>",
                        parse_mode="HTML"
                    )
    finally:
        if msg_id in GAME_SESSIONS:
            GAME_SESSIONS[msg_id]["lock"].release()



if __name__ == "__main__":
    init_db()
    print("есть")
    bot.infinity_polling()