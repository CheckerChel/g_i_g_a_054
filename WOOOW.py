import os
import random
import asyncio
import time
import sqlite3
from aiogram.types import TelegramObject
from decimal import Decimal, ROUND_DOWN
from typing import Any, Awaitable, Callable, Dict
import aiosqlite
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import BaseFilter, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramRetryAfter


TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

CHATS = [-1003724538567, 7163427034]
ADMINS = [7163427034]
GAME_SESSIONS = {}
PENDING_NAME_CHANGES = set()
PENDING_TRANSFERS = set()
PENDING_DICE_CALCS = set()
DB_PATH = "data/wow.db"


EMOJIS = {
    "user": "<tg-emoji emoji-id='5879770735999717115'>👤</tg-emoji>",
    "status": "<tg-emoji emoji-id='5427168083074628963'>💎</tg-emoji>",
    "clock": "<tg-emoji emoji-id='4904882772637648609'>⏰</tg-emoji>",
    "hat": "<tg-emoji emoji-id='5118686540985271080'>💼</tg-emoji>",
    "alert": "<tg-emoji emoji-id='5274099962655816924'>❗️</tg-emoji>",
    "gift": "<tg-emoji emoji-id='5963213811597970978'>🎁</tg-emoji>",
    "success": "<tg-emoji emoji-id='5206607081334906820'>✔️</tg-emoji>",
    "win": "<tg-emoji emoji-id='5449683594425410231'>🔼</tg-emoji>",
    "loss": "<tg-emoji emoji-id='5447183459602669338'>🔽</tg-emoji>",
    "info": "<tg-emoji emoji-id='5875206779196935950'>📁</tg-emoji>",
    "line": "<tg-emoji emoji-id='4918408122868958076'>🖱️</tg-emoji>",
    "love": "<tg-emoji emoji-id='5348070436343134224'>❤️</tg-emoji>",
    "seven": "<tg-emoji emoji-id='5415767487524413966'>7️⃣</tg-emoji>",
    "lemon": "<tg-emoji emoji-id='5413346105222017145'>🍋</tg-emoji>",
    "grape": "<tg-emoji emoji-id='5413849393784730997'>🍇</tg-emoji>",
    "bar": "<tg-emoji emoji-id='5413440371164230302'>🅱️</tg-emoji>"
}


class ChatFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
        return chat_id in CHATS


class RetryRateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await handler(event, data)


class RegisterMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
                async with conn.execute("SELECT 1 FROM Users WHERE real_id = ?", (user.id,)) as cursor:
                    if not await cursor.fetchone():
                        await conn.execute(
                            "INSERT INTO Users (real_id) VALUES (?)",
                            (user.id,)
                        )
                        await conn.commit()
        return await handler(event, data)

dp.message.middleware(RegisterMiddleware())
dp.callback_query.middleware(RegisterMiddleware())
dp.message.middleware(RetryRateLimitMiddleware())
dp.callback_query.middleware(RetryRateLimitMiddleware())


async def init_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            real_id INTEGER NOT NULL,
            coins INTEGER DEFAULT 0,
            time INTEGER DEFAULT 0,
            turnover INTEGER DEFAULT 0,
            ws_max INTEGER DEFAULT 0,
            ws_i INTEGER DEFAULT 0,
            game_choice TEXT DEFAULT NULL
        )
        """)
        await conn.commit()


async def get_user_data(field: str, value: Any) -> list | None:
    ALLOWED_FIELDS = {"bot_id", "real_id"}
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Недопустимое имя поля: {field}")
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        async with conn.execute(
            f"SELECT bot_id, real_id, coins, time, turnover, ws_max, ws_i, game_choice FROM Users WHERE {field} = ?",
            (value,)
        ) as cursor:
            row = await cursor.fetchone()
            return list(row) if row else None


@dp.message(ChatFilter(), Command("info", "info@HypnoGame"), lambda m: m.text and m.text.lower() in ["/info", "/info@hypnogame"])
async def show_bot_info(message: Message):
    text = (
        f"{EMOJIS['info']}<b>Информация о боте</b>\n\n"
        "<b>Команды:</b>\n"
        f"<blockquote expandable>{EMOJIS['line']}<b>Проф</b>  —  просмотр профиля\n{EMOJIS['line']}<b>Бонус</b>  —  получение бонуса\n{EMOJIS['line']}<b>Дать [сумма]</b>  —  передать $\n{EMOJIS['line']}<b>+Имя</b>  —  смена игрового имени\n{EMOJIS['line']}<b>Бет [сумма]</b>  —  играть</blockquote>\n\n"
        "Команды <b>Проф</b> и <b>Дать</b> также работают с помощью реплая (ответа на чужое сообщение). Для особо одарённых имеется сокращение <b>$[сумма]</b> вместо <b>Бет</b>.\n"
        f"<b>По всем вопросам — к Богу</b>{EMOJIS['love']}"
    )
    await message.reply(text, parse_mode="HTML")


@dp.message(ChatFilter(), lambda m: m.text and (m.text.lower() == 'проф' or m.text.lower().startswith('проф ')))
async def show_profile(message: Message):
    args = message.text.split(maxsplit=1)
    target_user = None
    name_display = ""
    if len(args) > 1:
        if message.from_user.id not in ADMINS:
            return
        t_id = args[1].replace('#', '').strip()
        if t_id.isdigit():
            target_user = await get_user_data("bot_id", int(t_id))
            if target_user:
                try:
                    chat_member = await message.chat.get_member(target_user[1])
                    name_display = chat_member.user.full_name
                except Exception:
                    name_display = "Игрок"
        else:
            await message.reply("Правильный формат:\nпроф #айди")
            return
    elif message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
        if target_user:
            name_display = message.reply_to_message.from_user.full_name
    else:
        target_user = await get_user_data("real_id", message.from_user.id)
        if target_user:
            name_display = message.from_user.full_name
    if not target_user:
        await message.reply("Пользователь не найден")
        return
    bot_id, real_id, coins_val, last_time, turnover_val, ws_max, ws_i, game_choice = target_user
    coins_int = int(coins_val or 0)
    turnover_int = int(turnover_val or 0)
    text = (
        f"{EMOJIS['user']} <b>{name_display}</b>\n\n"
        f"Баланс: {coins_int}{EMOJIS['status']}\n"
        f"Оборот: {turnover_int}{EMOJIS['status']}\n"
        f"Лучший WS: {ws_max}"
    )
    current_time = int(time.time())
    cooldown = 3 * 3600
    if current_time - last_time < cooldown and last_time != 0:
        remains = cooldown - (current_time - last_time)
        hours = remains // 3600
        mins = (remains % 3600) // 60
        secs = remains % 60
        text += f"\n\n<b>След. бонус через:</b>\n{EMOJIS['clock']}{hours}ч. {mins}м. {secs}с."
    await message.reply(text, parse_mode="HTML")


@dp.message(ChatFilter(), lambda m: m.from_user.id in ADMINS and m.text and (m.text.startswith('++') or m.text.startswith('--')))
async def admin_modify_coins(message: Message):
    args = message.text.split(maxsplit=2)
    command = args[0]
    is_add = command.startswith('++')
    amount_str = command[2:]
    if not amount_str or not amount_str.isdigit():
        return
    amount = int(amount_str)
    if amount <= 0:
        return
    target_user = None
    name_display = ""
    if len(args) > 1:
        t_id = args[1].replace('#', '').strip()
        if t_id.isdigit():
            target_user = await get_user_data("bot_id", int(t_id))
            if target_user:
                try:
                    chat_member = await message.chat.get_member(target_user[1])
                    name_display = chat_member.user.full_name
                except Exception:
                    name_display = "Игрок"
    elif message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
        if target_user:
            name_display = message.reply_to_message.from_user.full_name
    else:
        target_user = await get_user_data("real_id", message.from_user.id)
        if target_user:
            name_display = message.from_user.full_name
    if not target_user:
        return
    bot_id, real_id, coins_val, last_time, turnover_val, ws_max, ws_i, game_choice = target_user
    current_coins = int(coins_val or 0)
    if is_add:
        new_coins = current_coins + amount
    else:
        if amount > current_coins:
            await message.reply(f"{EMOJIS['alert']}<b>Максимум:</b> {current_coins}{EMOJIS['status']}", parse_mode="HTML")
            return
        new_coins = current_coins - amount
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_coins, bot_id))
        await conn.commit()
    if is_add:
        text = f"{EMOJIS['hat']}<b>Выдано</b> {amount}{EMOJIS['status']} <b>пользователю {name_display}</b>"
    else:
        text = f"{EMOJIS['hat']}<b>Отобрано</b> {amount}{EMOJIS['status']} <b>у пользователя {name_display}</b>"
    await message.reply(text, parse_mode="HTML")


@dp.message(ChatFilter(), lambda m: m.from_user.id in ADMINS and m.text and m.text.lower().startswith('-кд'))
async def admin_reset_cooldown(message: Message):
    args = message.text.split()
    target_user = None
    name_display = ""
    if len(args) > 1:
        t_id = args[1].replace('#', '').strip()
        if t_id.isdigit():
            target_user = await get_user_data("bot_id", int(t_id))
            if target_user:
                try:
                    chat_member = await message.chat.get_member(target_user[1])
                    name_display = chat_member.user.full_name
                except Exception:
                    name_display = "Игрок"
    elif message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
        if target_user:
            name_display = message.reply_to_message.from_user.full_name
    else:
        target_user = await get_user_data("real_id", message.from_user.id)
        if target_user:
            name_display = message.from_user.full_name
    if not target_user:
        return
    bot_id = target_user[0]
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute("UPDATE Users SET time = 0 WHERE bot_id = ?", (bot_id,))
        await conn.commit()
    await message.reply(f"{EMOJIS['clock']}<b>Бонус доступен для {name_display}</b>", parse_mode="HTML")


@dp.message(ChatFilter(), lambda m: m.text and m.text.lower() == "бонус")
async def get_bonus(message: Message):
    user_id = message.from_user.id
    user_data = await get_user_data("real_id", user_id)
    if not user_data:
        return
    bot_id, real_id, coins, last_time, turnover, ws_max, ws_i, game_choice = user_data
    current_time = int(time.time())
    cooldown = 3 * 3600
    if current_time - last_time < cooldown:
        remains = cooldown - (current_time - last_time)
        hours = remains // 3600
        mins = (remains % 3600) // 60
        secs = remains % 60
        await message.reply(
            f"<b>Не торопись!</b> След. бонус будет доступен через:\n"
            f"{EMOJIS['clock']}{hours}ч. {mins}м. {secs}с.",
            parse_mode="HTML"
        )
        return
    bonus = random.randint(500, 1000)
    current_coins = int(coins or 0)
    new_coins = current_coins + bonus
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute(
            "UPDATE Users SET coins = ?, time = ? WHERE real_id = ?",
            (new_coins, current_time, user_id)
        )
        await conn.commit()
    await message.reply(
        f"{EMOJIS['gift']}<b>Вы получили</b> {bonus}{EMOJIS['status']}<b>, возвращайтесь через 3 часа</b>",
        parse_mode="HTML"
    )


@dp.message(ChatFilter(), lambda m: m.text and (m.text.lower() == 'дать' or m.text.lower().startswith('дать ')))
async def request_transfer(message: Message):
    args = message.text.split()
    if len(args) < 2 or not message.reply_to_message:
        await message.reply("<b>Укажите сумму и ответьте на сообщение пользователя</b>", parse_mode="HTML")
        return
    amount_raw = args[1]
    if not amount_raw.isdigit():
        return
    amount = int(amount_raw)
    if amount <= 0:
        return
    sender = await get_user_data("real_id", message.from_user.id)
    if not sender:
        return
    sender_coins = int(sender[2] or 0)
    if sender_coins < amount:
        await message.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
        return
    target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
    if not target_user:
        await message.reply("Пользователь не найден", parse_mode="HTML")
        return
    if sender[0] == target_user[0]:
        return
    target_name = message.reply_to_message.from_user.full_name
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅Подтвердить", 
        callback_data=f"pay_{sender[0]}_{target_user[0]}_{amount}",
        style="success"
    ))
    await message.reply(
        f"<b>Вы уверены, что хотите передать</b> {amount}{EMOJIS['status']} <b>пользователю {target_name}?</b>", 
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("pay_"))
async def confirm_transfer(call: CallbackQuery):
    _, s_bot_id_str, t_bot_id_str, amount_str = call.data.split("_")
    s_bot_id, t_bot_id = int(s_bot_id_str), int(t_bot_id_str)
    amount = int(amount_str)
    sender = await get_user_data("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender:
        await call.answer()
        return
    if s_bot_id in PENDING_TRANSFERS:
        await call.answer()
        return
    PENDING_TRANSFERS.add(s_bot_id)
    try:
        async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
            async with conn.execute("SELECT coins FROM Users WHERE bot_id = ?", (s_bot_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await call.answer()
                    return
                sender_coins = int(row or 0)
            if sender_coins < amount:
                await call.answer()
                try:
                    await call.message.edit_text(f"{EMOJIS['alert']}Недостаточно средств", reply_markup=None, parse_mode="HTML")
                except Exception:
                    pass
                return
            await call.answer()
            async with conn.execute("SELECT coins FROM Users WHERE bot_id = ?", (t_bot_id,)) as cursor:
                t_row = await cursor.fetchone()
                if not t_row:
                    return
                target_coins = int(t_row or 0)
            new_sender_coins = sender_coins - amount
            new_target_coins = target_coins + amount
            await conn.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_sender_coins, s_bot_id))
            await conn.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_target_coins, t_bot_id))
            await conn.commit()
        try:
            try:
                chat_member = await call.message.chat.get_member(target_user)
                target_name = chat_member.user.full_name
            except Exception:
                target_name = "Игрок"
            await call.message.edit_text(
                f"{EMOJIS['success']}<b>Вы успешно передали</b> {amount}{EMOJIS['status']} <b>на {target_name}</b>", 
                reply_markup=None, 
                parse_mode="HTML"
            )
        except Exception:
            pass
    finally:
        PENDING_TRANSFERS.discard(s_bot_id)


#

#

#

#

#


def get_slot_keyboard(amount: int, page: str = "main", has_choice: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if page == "main":
        builder.row(InlineKeyboardButton(text="Любая комбинация (х16)", callback_data=f"slot_play_any_{amount}"))
        builder.row(InlineKeyboardButton(text="Уникальные символы х2.66", callback_data=f"slot_play_uniq_{amount}"))
        builder.row(InlineKeyboardButton(text="Точный исход", callback_data=f"slot_page_exact_{amount}"))
    elif page == "exact":
        builder.row(InlineKeyboardButton(text="Назад", callback_data=f"slot_page_main_{amount}", style="primary"))
        symbols_config = [
            ("7️⃣", "5415767487524413966", "3"),
            ("🍋", "5413346105222017145", "2"),
            ("🍇", "5413849393784730997", "1"),
            ("🅱️", "5413440371164230302", "0")
        ]
        for text_sym, emoji_id, code in symbols_config:
            builder.row(
                InlineKeyboardButton(text=f"{text_sym} х2.37", callback_data=f"slot_play_1{code}_{amount}", icon_custom_emoji_id=emoji_id),
                InlineKeyboardButton(text=f"{text_sym}{text_sym} х7.11", callback_data=f"slot_play_2{code}_{amount}", icon_custom_emoji_id=emoji_id),
                InlineKeyboardButton(text=f"{text_sym}{text_sym}{text_sym} х64", callback_data=f"slot_play_3{code}_{amount}", icon_custom_emoji_id=emoji_id)
            )
    if has_choice:
        builder.row(InlineKeyboardButton(text="Повтор", callback_data=f"slot_play_repeat_{amount}", style="primary"))
    return builder.as_markup()


@dp.message(ChatFilter(), lambda m: m.text and m.text.isdigit())
async def init_game_slot(message: Message):
    amount = int(message.text)
    if amount < 10:
        await message.reply(f"{EMOJIS['alert']}Минимальная ставка: 10{EMOJIS['status']}", parse_mode="HTML")
        return
    user_data = await get_user_data("real_id", message.from_user.id)
    if not user_data:
        return
    bot_id, real_id, coins_val, _, turnover_val, ws_max, ws_i, game_choice = user_data
    current_coins = int(coins_val or 0)
    if current_coins < amount:
        await message.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
        return
    name_display = message.from_user.full_name
    has_choice = bool(game_choice)
    markup = get_slot_keyboard(amount=amount, page="main", has_choice=has_choice)
    sent_msg = await message.reply(
        f"{EMOJIS['user']}<b>{name_display}</b>, выберите исход.\n\n"
        f"Ставка: {amount}{EMOJIS['status']}\n"
        f"Баланс: {current_coins}{EMOJIS['status']}\n"
        f"Текущий WS: {ws_i}",
        reply_markup=markup,
        parse_mode="HTML"
    )
    GAME_SESSIONS[sent_msg.message_id] = message.from_user.id


@dp.callback_query(lambda c: c.data and c.data.startswith("slot_"))
async def handle_slot_clicks(call: CallbackQuery):
    msg_id = call.message.message_id
    data_parts = call.data.split("_")
    action = data_parts[1]
    amount = int(data_parts[-1])
    user_data = await get_user_data("real_id", call.from_user.id)
    if not user_data:
        await call.answer()
        return
    bot_id, real_id, coins_val, _, turnover_val, ws_max, ws_i, game_choice = user_data
    current_coins = int(coins_val or 0)
    if msg_id in GAME_SESSIONS and call.from_user.id != GAME_SESSIONS[msg_id]:
        await call.answer()
        return
    elif msg_id not in GAME_SESSIONS:
        await call.answer()
        return
    if action == "page":
        await call.answer()
        page_target = data_parts[2]
        has_choice = bool(game_choice)
        markup = get_slot_keyboard(amount=amount, page=page_target, has_choice=has_choice)
        try:
            await call.message.edit_reply_markup(reply_markup=markup)
        except Exception:
            pass
        return
    if action == "play":
        await call.answer()
        choice_type = data_parts[2]
        if choice_type == "repeat":
            if not game_choice:
                return
            choice_type = game_choice
        if current_coins < amount:
            try:
                await call.message.edit_text(f"{EMOJIS['alert']}Недостаточно средств", reply_markup=None, parse_mode="HTML")
            except Exception:
                pass
            GAME_SESSIONS.pop(msg_id, None)
            return
        if bot_id in PENDING_DICE_CALCS:
            return
        PENDING_DICE_CALCS.add(bot_id)
        GAME_SESSIONS.pop(msg_id, None)
        try:
            await call.message.delete()
        except Exception:
            pass
        slot_msg = await call.message.answer_dice(emoji="🎰")
        value = slot_msg.dice.value
        await asyncio.sleep(2.2)
        X = value - 1
        b1 = X % 4
        b2 = (X // 4) % 4
        b3 = (X // 16) % 4
        is_win = False
        coef = 0.0
        if choice_type == "any":
            if b1 == b2 == b3:
                is_win = True
                coef = 16.0
        elif choice_type == "uniq":
            if b1 != b2 and b1 != b3 and b2 != b3:
                is_win = True
                coef = 2.66
        else:
            target_count = int(choice_type[0])
            target_symbol = int(choice_type[1])
            actual_count = 0
            if b1 == target_symbol:
                actual_count += 1
            if b2 == target_symbol:
                actual_count += 1
            if b3 == target_symbol:
                actual_count += 1
            if actual_count == target_count:
                is_win = True
                if target_count == 1:
                    coef = 2.37
                elif target_count == 2:
                    coef = 7.11
                elif target_count == 3:
                    coef = 64.0
        names_map = {3: "семёрк", 2: "лимон", 1: "виноград", 0: "BAR"}
        endings_map = {
            3: {"семёрк": "и", "лимон": "а", "виноград": "а", "BAR": ""},
            2: {"семёрк": "и", "лимон": "а", "виноград": "а", "BAR": ""},
            1: {"семёрк": "а", "лимон": "", "виноград": "", "BAR": ""}
        }
        num_map = {3: "три", 2: "две", 1: "один" if b1 == 0 or b2 == 0 or b3 == 0 or b1 == 2 or b2 == 2 or b3 == 2 or b1 == 1 or b2 == 1 or b3 == 1 else "одна"}
        if choice_type == "any":
            outcome_text = "любая комбинация"
        elif choice_type == "uniq":
            outcome_text = "уникальные символы"
        else:
            req_count = int(choice_type[0])
            req_sym = int(choice_type[1])
            outcome_text = f"{num_map[req_count]} {names_map[req_sym]}`{endings_map[req_count][names_map[req_sym]]}"
        async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
            async with conn.execute("SELECT coins, turnover, ws_max, ws_i FROM Users WHERE bot_id = ?", (bot_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    PENDING_DICE_CALCS.discard(bot_id)
                    return
                fresh_coins = int(row[0] or 0)
                fresh_turnover = int(row[1] or 0)
                fresh_ws_max = int(row[2] or 0)
                fresh_ws_i = int(row[3] or 0)
            if fresh_coins < amount:
                await slot_msg.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
                PENDING_DICE_CALCS.discard(bot_id)
                return
            new_turnover = fresh_turnover + amount
            try:
                chat_member = await call.message.chat.get_member(real_id)
                name_display = chat_member.user.full_name
            except Exception:
                name_display = "Игрок"
            if is_win:
                net_profit = int((amount * coef) - amount)
                final_coins = fresh_coins + net_profit
                new_ws_i = fresh_ws_i + 1
                new_ws_max = new_ws_i if new_ws_i > fresh_ws_max else fresh_ws_max
                await conn.execute(
                    "UPDATE Users SET coins = ?, turnover = ?, ws_max = ?, ws_i = ?, game_choice = ? WHERE bot_id = ?",
                    (final_coins, new_turnover, new_ws_max, new_ws_i, choice_type, bot_id)
                )
                await conn.commit()
                text = (
                    f"<b>{name_display} {EMOJIS['win']} выигрывает</b> {net_profit}{EMOJIS['status']}!\n"
                    f"<b>Исход:</b> {outcome_text}\n\n"
                    f"Ставка: {amount}{EMOJIS['status']}\n"
                    f"Баланс: {final_coins}{EMOJIS['status']}\n"
                    f"Текущий WS: {new_ws_i}"
                )
            else:
                final_coins = fresh_coins - amount
                new_ws_i = 0
                await conn.execute(
                    "UPDATE Users SET coins = ?, turnover = ?, ws_i = ?, game_choice = ? WHERE bot_id = ?",
                    (final_coins, new_turnover, new_ws_i, choice_type, bot_id)
                )
                await conn.commit()
                text = (
                    f"<b>{name_display} {EMOJIS['loss']} проигрывает</b> {amount}{EMOJIS['status']}!\n"
                    f"<b>Исход:</b> {outcome_text}\n\n"
                    f"Ставка: {amount}{EMOJIS['status']}\n"
                    f"Баланс: {final_coins}{EMOJIS['status']}"
                )
            if final_coins >= amount:
                markup = get_slot_keyboard(amount=amount, page="main", has_choice=True)
                res_msg = await slot_msg.reply(text, reply_markup=markup, parse_mode="HTML")
                GAME_SESSIONS[res_msg.message_id] = real_id
            else:
                await slot_msg.reply(text, parse_mode="HTML")
        PENDING_DICE_CALCS.discard(bot_id)


async def main():
    await init_db()
    await dp.start_polling(bot)
if __name__ == "__main__":
    asyncio.run(main())