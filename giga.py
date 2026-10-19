import os
import random
import threading
import time
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
        if hasattr(obj, 'chat'):
            return obj.chat.id in CHATS
        if hasattr(obj, 'message'):
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


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() in ['проф', 'п'] or m.text.lower().startswith('проф ')))
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
    btn = InlineKeyboardButton(text="✅Подтвердить", callback_data=f"pay_{sender[0]}_{target_user[0]}_{amount}", color="access")
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


@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() in ['бет', 'бэт'] or m.text.lower().startswith(('бет ', 'бэт '))))
def game_bet_handler(message):
    args = message.text.split()
    if len(args) == 1:
        bot.reply_to(message, "Правильный формат:\nбет [сумма]")
        return
    if len(args) < 2 or not args[1].isdigit():
        return
    bet = int(args[1])
    if bet <= 0:
        return
    check(message.from_user.id)
    user_data = get_user_data("real_id", message.from_user.id)
    if not user_data:
        return
    bot_id, real_id, coins, time_val = user_data
    if coins < bet:
        bot.reply_to(message, "Недостаточно средств")
        return
    markup = InlineKeyboardMarkup()
    btn_cubes = InlineKeyboardButton(text="🎲", callback_data=f"g_menu_cubes_{bot_id}_{bet}", style="primary")
    btn_mines = InlineKeyboardButton(text="💣", callback_data=f"g_menu_mines_{bot_id}_{bet}", style="primary")
    markup.row(btn_cubes, btn_mines)
    mention = f'<a href="https://telegram.me/{real_id}">#{bot_id}</a>'
    bot.reply_to(message, f"{mention}, выбери игру.\n💰Ставка: {bet}Ж", parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("g_menu_"))
def game_menu_callback(call):
    data = call.data.split("_")
    sub = data[2]
    s_bot_id = int(data[3])
    bet = int(data[4])
    sender = get_user_data("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id, "Это не ваша операция", show_alert=True)
        return
    if sender[2] < bet:
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return
    bot.answer_callback_query(call.id)
    mention = f'<a href="https://telegram.me/{sender[1]}">#{s_bot_id}</a>'
    if sub == "main":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton(text="🎲", callback_data=f"g_menu_cubes_{s_bot_id}_{bet}", style="primary"), InlineKeyboardButton(text="💣", callback_data=f"g_menu_mines_{s_bot_id}_{bet}", style="primary"))
        bot.edit_message_text(f"{mention}, выбери игру.\n💰Ставка: {bet}Ж", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif sub == "cubes":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton(text="Больше", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_big"), InlineKeyboardButton(text="Меньше", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_small"))
        markup.row(InlineKeyboardButton(text="Чётное", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_even"), InlineKeyboardButton(text="Нечётное", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_odd"))
        markup.row(InlineKeyboardButton(text="1", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_1"), InlineKeyboardButton(text="2", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_2"), InlineKeyboardButton(text="3", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_3"))
        markup.row(InlineKeyboardButton(text="4", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_4"), InlineKeyboardButton(text="5", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_5"), InlineKeyboardButton(text="6", callback_data=f"g_play_cubes_{s_bot_id}_{bet}_6"))
        markup.row(InlineKeyboardButton(text="Назад", callback_data=f"g_menu_main_{s_bot_id}_{bet}", style="danger"))
        bot.edit_message_text(f"{mention}, выбери исход.\n🔖Игра: кубы\n💰Ставка: {bet}Ж", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
    elif sub == "mines":
        mine_indexes = random.sample(range(25), 5)
        mine_str = ",".join(map(str, mine_indexes))
        generate_mines_field(call.message, s_bot_id, bet, mine_str, "", False)


@bot.callback_query_handler(func=lambda call: call.data.startswith("g_play_cubes_"))
def game_play_cubes_callback(call):
    data = call.data.split("_")
    s_bot_id = int(data[3])
    bet = int(data[4])
    choice = data[5]
    sender = get_user_data("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id, "Это не ваша операция", show_alert=True)
        return
    if s_bot_id not in LOCKS:
        LOCKS[s_bot_id] = threading.Lock()
    if not LOCKS[s_bot_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return
    try:
        if sender[2] < bet:
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass
            return
        bot.answer_callback_query(call.id)
        try:
            bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass
        dice_msg = bot.send_dice(chat_id=call.message.chat.id)
        dice_value = dice_msg.dice.value
        win = False
        multiplier = 0
        if choice == "big" and dice_value > 3:
            win, multiplier = True, 1
        elif choice == "small" and dice_value <= 3:
            win, multiplier = True, 1
        elif choice == "even" and dice_value % 2 == 0:
            win, multiplier = True, 1
        elif choice == "odd" and dice_value % 2 != 0:
            win, multiplier = True, 1
        elif choice.isdigit() and dice_value == int(choice):
            win, multiplier = True, 5
        mention = f'<a href="https://telegram.me/{sender[1]}">#{s_bot_id}</a>'
        res_names = {"big": "больше", "small": "меньше", "even": "чётное", "odd": "нечётное"}
        choice_text = res_names.get(choice, choice)
        if win:
            profit = bet * multiplier
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (profit, s_bot_id))
                conn.commit()
            bot.send_message(chat_id=call.message.chat.id, text=f"🌹{mention}, вы выиграли {bet + profit}Ж!\n💰Ставка: {bet}Ж\n🍀Исход: {choice_text}", parse_mode="HTML", reply_to_message_id=dice_msg.message_id)
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (bet, s_bot_id))
                conn.commit()
            bot.send_message(chat_id=call.message.chat.id, text=f"💔{mention}, вы проиграли.\n💰Ставка: {bet}Ж\n🍀Исход: {choice_text}", parse_mode="HTML", reply_to_message_id=dice_msg.message_id)
    finally:
        LOCKS[s_bot_id].release()


@bot.callback_query_handler(func=lambda call: call.data.startswith("g_play_mines_"))
def game_play_mines_callback(call):
    data = call.data.split("_")
    s_bot_id = int(data[3])
    bet = int(data[4])
    click_idx = int(data[5])
    mine_str = data[6]
    opened_str = data[7] if len(data) > 7 else ""
    sender = get_user_data("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender:
        bot.answer_callback_query(call.id, "Это не ваша операция", show_alert=True)
        return
    if sender[2] < bet:
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return
    bot.answer_callback_query(call.id)
    mine_list = list(map(int, mine_str.split(",")))
    opened_list = list(map(int, opened_str.split(","))) if opened_str else []
    if click_idx in opened_list:
        return
    if click_idx in mine_list:
        end_mines_game(call.message, s_bot_id, bet, mine_list, opened_list, False, False)
        return
    opened_list.append(click_idx)
    new_opened_str = ",".join(map(str, opened_list))
    if len(opened_list) == 20:
        end_mines_game(call.message, s_bot_id, bet, mine_list, opened_list, True, True)
        return
    generate_mines_field(call.message, s_bot_id, bet, mine_str, new_opened_str, True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("g_stop_"))
def game_stop_mines_callback(call):
    data = call.data.split("_")
    s_bot_id = int(data[2])
    bet = int(data[3])
    mine_str = data[4]
    opened_str = data[5] if len(data) > 5 else ""
    sender = get_user_data("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender:
        bot.answer_callback_query(call.id, "Это не ваша операция", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    mine_list = list(map(int, mine_str.split(",")))
    opened_list = list(map(int, opened_str.split(","))) if opened_str else []
    end_mines_game(call.message, s_bot_id, bet, mine_list, opened_list, True, False)


def generate_mines_field(message, s_bot_id, bet, mine_str, opened_str, has_started):
    sender = get_user_data("bot_id", s_bot_id)
    mention = f'<a href="https://telegram.me/{sender[1]}">#{s_bot_id}</a>'
    opened_list = list(map(int, opened_str.split(","))) if opened_str else []
    total_cells = 25
    remaining_safe = total_cells - len(opened_list)
    multiplier = total_cells / remaining_safe if len(opened_list) > 0 else 1.0
    accumulated = int(bet * (multiplier - 1.0))
    markup = InlineKeyboardMarkup()
    for row in range(5):
        row_btns = []
        for col in range(5):
            idx = row * 5 + col
            if idx in opened_list:
                row_btns.append(InlineKeyboardButton(text="⠀", callback_data="g_void"))
            else:
                row_btns.append(InlineKeyboardButton(text="⠀", callback_data=f"g_play_mines_{s_bot_id}_{bet}_{idx}_{mine_str}_{opened_str}", style="primary"))
        markup.row(*row_btns)
    if has_started:
        markup.row(InlineKeyboardButton(text="Закончить", callback_data=f"g_stop_{s_bot_id}_{bet}_{mine_str}_{opened_str}", style="danger"))
    else:
        markup.row(InlineKeyboardButton(text="Назад", callback_data=f"g_menu_main_{s_bot_id}_{bet}", style="danger"))
    bot.edit_message_text(f"{mention}, выбери игру.\n🔖Игра: минное поле\n💰Ставка: {bet}Ж\n🍀Набрано: {accumulated}Ж", chat_id=message.chat.id, message_id=message.message_id, parse_mode="HTML", reply_markup=markup)


def end_mines_game(message, s_bot_id, bet, mine_list, opened_list, is_win, max_win):
    if s_bot_id not in LOCKS:
        LOCKS[s_bot_id] = threading.Lock()
    if not LOCKS[s_bot_id].acquire(blocking=False):
        return
    try:
        sender = get_user_data("bot_id", s_bot_id)
        if not sender:
            return
        total_cells = 25
        remaining_safe = total_cells - len(opened_list)
        multiplier = total_cells / remaining_safe if len(opened_list) > 0 else 1.0
        accumulated = int(bet * (multiplier - 1.0))
        markup = InlineKeyboardMarkup()
        for row in range(5):
            row_btns = []
            for col in range(5):
                idx = row * 5 + col
                if idx in mine_list:
                    row_btns.append(InlineKeyboardButton(text="💣", callback_data="g_void"))
                elif idx in opened_list:
                    if max_win:
                        row_btns.append(InlineKeyboardButton(text="⠀", callback_data="g_void", style="access"))
                    else:
                        row_btns.append(InlineKeyboardButton(text="⠀", callback_data="g_void"))
                else:
                    if max_win:
                        row_btns.append(InlineKeyboardButton(text="⠀", callback_data="g_void", style="access"))
                    else:
                        row_btns.append(InlineKeyboardButton(text="⠀", callback_data="g_void"))
            markup.row(*row_btns)
        mention = f'<a href="https://telegram.me/{sender[1]}">#{s_bot_id}</a>'
        if not is_win:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (bet, s_bot_id))
                conn.commit()
            bot.edit_message_text(f"{mention}, вы проиграли.\n💰Ставка: {bet}Ж", chat_id=message.chat.id, message_id=message.message_id, parse_mode="HTML", reply_markup=markup)
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (accumulated, s_bot_id))
                conn.commit()
            status_text = f"{mention}, удачная игра!" if max_win else f"{mention}, игра окончена."
            bot.edit_message_text(f"{status_text}\n💰Ставка: {bet}Ж\n🍀Набрано: {accumulated}Ж", chat_id=message.chat.id, message_id=message.message_id, parse_mode="HTML", reply_markup=markup)
    finally:
        LOCKS[s_bot_id].release()


@bot.callback_query_handler(func=lambda call: call.data == "g_void")
def void_callback(call):
    bot.answer_callback_query(call.id)


if __name__ == "__main__":
    print("есть")
    bot.infinity_polling()