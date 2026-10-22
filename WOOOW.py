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


def adapt_decimal(d: Decimal) -> str:
    return str(d.quantize(Decimal('0.01'), rounding=ROUND_DOWN))

def convert_decimal(s: bytes) -> Decimal:
    return Decimal(s.decode('utf-8'))

aiosqlite.register_adapter(Decimal, adapt_decimal)
aiosqlite.register_converter("DECIMAL", convert_decimal)

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
    "loss": "<tg-emoji emoji-id='5447183459602669338'>🔽</tg-emoji>"
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
                            "INSERT INTO Users (real_id, bot_name) VALUES (?, ?)",
                            (user.id, "Безымянный")
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
            coins DECIMAL DEFAULT '0.00',
            time INTEGER DEFAULT 0,
            bot_name TEXT DEFAULT 'Безымянный',
            turnover DECIMAL DEFAULT '0.00'
        )
        """)
        await conn.commit()


async def get_user_data(field: str, value: Any) -> list | None:
    ALLOWED_FIELDS = {"bot_id", "real_id"}
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Недопустимое имя поля: {field}")
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        async with conn.execute(
            f"SELECT bot_id, real_id, coins, time, bot_name, turnover FROM Users WHERE {field} = ?",
            (value,)
        ) as cursor:
            row = await cursor.fetchone()
            return list(row) if row else None


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
                name_display = target_user[4]
        else:
            await message.reply("Правильный формат:\nпроф #айди")
            return
    elif message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
        if target_user:
            name_display = target_user[4]
    else:
        target_user = await get_user_data("real_id", message.from_user.id)
        if target_user:
            name_display = target_user[4]
            
    if not target_user:
        await message.reply("Пользователь не найден")
        return
        
    bot_id, real_id, coins_val, last_time, bot_name, turnover_val = target_user
    
    coins_dec = Decimal(str(coins_val or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    turnover_dec = Decimal(str(turnover_val or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    status_str = f" {EMOJIS['status']}" if turnover_dec > Decimal('10000') else ""
    
    text = (
        f"{EMOJIS['user']}<b>{name_display}{status_str}</b>\n"
        f"<b>ID:</b> {real_id}\n\n"
        f"<b>Баланс:</b> ${coins_dec}\n"
        f"<b>Оборот:</b> ${turnover_dec}"
    )
    
    current_time = int(time.time())
    cooldown = 3 * 3600
    if current_time - last_time < cooldown and last_time != 0:
        remains = cooldown - (current_time - last_time)
        hours = remains // 3600
        mins = (remains % 3600) // 60
        secs = remains % 60
        text += f"\n\n<b>След. бонус через:</b>\n{EMOJIS['clock']}{hours}ч. {mins}м. {secs}с."
        
    await message.reply(text, parse_mode="HTML");


@dp.message(ChatFilter(), lambda m: m.from_user.id in ADMINS and m.text and (m.text.startswith('+$') or m.text.startswith('-$')))
async def admin_modify_coins(message: Message):
    args = message.text.split(maxsplit=2)
    command = args[0]
    is_add = command.startswith('+$')
    
    amount_str = command[2:]
    if not amount_str:
        return
        
    try:
        if '.' in amount_str and len(amount_str.split('.')[1]) > 2:
            return
        amount = Decimal(amount_str)
    except Exception:
        return
        
    if amount <= 0:
        return

    target_user = None
    if len(args) > 1:
        t_id = args[1].replace('#', '').strip()
        if t_id.isdigit():
            target_user = await get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        target_user = await get_user_data("real_id", message.from_user.id)
        
    if not target_user:
        return
        
    bot_id, real_id, coins_val, last_time, bot_name, turnover_val = target_user
    current_coins = Decimal(str(coins_val or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    if is_add:
        new_coins = current_coins + amount
    else:
        if amount > current_coins:
            await message.reply(f"{EMOJIS['alert']}<b>Максимум:</b> ${current_coins}", parse_mode="HTML")
            return
        new_coins = current_coins - amount

    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_coins, bot_id))
        await conn.commit()
        
    if is_add:
        text = f"{EMOJIS['hat']}<b>Выдано</b> ${amount} <b>на {bot_name}</b>"
    else:
        text = f"{EMOJIS['hat']}<b>Отобрано</b> ${amount} <b>у {bot_name}</b>"
        
    await message.reply(text, parse_mode="HTML")


@dp.message(ChatFilter(), lambda m: m.from_user.id in ADMINS and m.text and m.text.lower().startswith('-кд'))
async def admin_reset_cooldown(message: Message):
    args = message.text.split()
    target_user = None
    
    if len(args) > 1:
        t_id = args[1].replace('#', '').strip()
        if t_id.isdigit():
            target_user = await get_user_data("bot_id", int(t_id))
    elif message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        target_user = await get_user_data("real_id", message.from_user.id)
        
    if not target_user:
        return
        
    bot_id, real_id, coins, last_time, bot_name, turnover = target_user
    
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute("UPDATE Users SET time = 0 WHERE bot_id = ?", (bot_id,))
        await conn.commit()
        
    await message.reply(f"{EMOJIS['clock']}<b>Бонус доступен для {bot_name}</b>", parse_mode="HTML")


@dp.message(ChatFilter(), lambda m: m.text and m.text.lower() == "бонус")
async def get_bonus(message: Message):
    user_id = message.from_user.id
    user_data = await get_user_data("real_id", user_id)
    if not user_data:
        return
        
    bot_id, real_id, coins, last_time, bot_name, turnover = user_data
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
        
    bonus_raw = random.uniform(0.05, 0.1)
    bonus = Decimal(str(bonus_raw)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    current_coins = Decimal(str(coins or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    new_coins = current_coins + bonus
    
    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute(
            "UPDATE Users SET coins = ?, time = ? WHERE real_id = ?",
            (new_coins, current_time, user_id)
        )
        await conn.commit()
        
    await message.reply(
        f"{EMOJIS['gift']}<b>Вы получили</b> ${bonus}<b>, возвращайтесь через 3 часа</b>",
        parse_mode="HTML"
    )


@dp.message(ChatFilter(), lambda m: m.text and (m.text.strip() == "+имя" or m.text.lower().startswith("+имя ")))
async def request_name_change(message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) == 1:
        await message.reply(
            f"<b>Напишите</b> «+имя [текст]» <b>чтобы изменить своё игровое имя.</b> Имя должно содержать от 3 до 12 символов. Разрешена кириллица и цифры.\n"
            f"<b>Стоимость услуги: </b> $1",
            parse_mode="HTML"
        )
        return
        
    new_name = args[1].strip()
    
    import re
    if not (3 <= len(new_name) <= 12) or not re.match(r"^[а-яА-ЯёЁ0-9]+$", new_name):
        await message.reply(f"{EMOJIS['alert']}<b>Имя содержит недопустимые символы, выберите другое</b>", parse_mode="HTML")
        return
        
    user_data = await get_user_data("real_id", message.from_user.id)
    if not user_data:
        return
        
    coins_dec = Decimal(str(user_data[2] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    if coins_dec < Decimal('1.00'):
        await message.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
        return
        
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅Подтвердить", 
        callback_data=f"setname_{user_data[0]}_{new_name}",
        style="success"
    ))
    
    await message.reply(
        f"<b>Вы уверены, что хотите изменить своё имя за</b> $1<b>?</b>", 
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("setname_"))
async def confirm_name_change(call: CallbackQuery):
    _, b_id_str, target_name = call.data.split("_", 2)
    bot_id = int(b_id_str)
    
    user_data = await get_user_data("bot_id", bot_id)
    if not user_data or call.from_user.id != user_data[1]:
        await call.answer()
        return
        
    if bot_id in PENDING_NAME_CHANGES:
        await call.answer()
        return
        
    PENDING_NAME_CHANGES.add(bot_id)
    
    try:
        async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
            async with conn.execute("SELECT coins FROM Users WHERE bot_id = ?", (bot_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await call.answer()
                    return
                current_coins = Decimal(str(row[0] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                
            if current_coins < Decimal('1.00'):
                await call.answer()
                try:
                    await call.message.edit_text(f"{EMOJIS['alert']}Недостаточно средств", reply_markup=None, parse_mode="HTML")
                except Exception:
                    pass
                return
                
            await call.answer()
            new_coins = current_coins - Decimal('1.00')
            
            await conn.execute("UPDATE Users SET coins = ?, bot_name = ? WHERE bot_id = ?", (new_coins, target_name, bot_id))
            await conn.commit()
            
        try:
            await call.message.edit_text(f"{EMOJIS['success']}<b>Имя успешно изменено на {target_name}</b>", reply_markup=None, parse_mode="HTML")
        except Exception:
            pass
            
    finally:
        PENDING_NAME_CHANGES.discard(bot_id)


@dp.message(ChatFilter(), lambda m: m.from_user.id in ADMINS and m.text and (m.text.strip() == "++имя" or m.text.lower().startswith("++имя ")))
async def admin_force_change_name(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        await message.reply("<b>Формат команды:</b> ++имя [любое имя]", parse_mode="HTML")
        return

    new_name = args[1].strip()
    target_user = None

    if message.reply_to_message:
        target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
    else:
        target_user = await get_user_data("real_id", message.from_user.id)

    if not target_user:
        await message.reply("Пользователь не найден")
        return

    bot_id, _, _, _, old_name, _ = target_user

    async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
        await conn.execute("UPDATE Users SET bot_name = ? WHERE bot_id = ?", (new_name, bot_id))
        await conn.commit()

    await message.reply(
        f"{EMOJIS['success']} <b>Имя изменено с {old_name} на {new_name}</b>",
        parse_mode="HTML"
    )


@dp.message(ChatFilter(), lambda m: m.text and (m.text.lower() == 'дать' or m.text.lower().startswith('дать ')))
async def request_transfer(message: Message):
    args = message.text.split()
    
    if len(args) < 2 or not message.reply_to_message:
        await message.reply("<b>Укажите сумму и ответьте на сообщение пользователя</b>", parse_mode="HTML")
        return
        
    amount_raw = args[1]
    try:
        if '.' in amount_raw and len(amount_raw.split('.')) > 2:
            return
        amount_dec = Decimal(amount_raw)
        amount = amount_dec.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    except Exception:
        return
        
    if amount <= 0:
        return
        
    sender = await get_user_data("real_id", message.from_user.id)
    if not sender:
        return
        
    sender_coins = Decimal(str(sender[2] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    if sender_coins < amount:
        await message.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
        return
        
    target_user = await get_user_data("real_id", message.reply_to_message.from_user.id)
    if not target_user:
        await message.reply("Пользователь не найден", parse_mode="HTML")
        return
        
    if sender[0] == target_user[0]:
        return
        
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅Подтвердить", 
        callback_data=f"pay_{sender[0]}_{target_user[0]}_{amount}",
        style="success"
    ))
    
    await message.reply(
        f"<b>Вы уверены, что хотите передать</b> ${amount} <b>пользователю {target_user[4]}?</b>", 
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("pay_"))
async def confirm_transfer(call: CallbackQuery):
    _, s_bot_id_str, t_bot_id_str, amount_str = call.data.split("_")
    s_bot_id, t_bot_id = int(s_bot_id_str), int(t_bot_id_str)
    amount = Decimal(amount_str).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    sender = await get_user_data("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
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
                sender_coins = Decimal(str(row[0] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                
            if sender_coins < amount:
                await call.answer()
                try:
                    await call.message.edit_text(f"{EMOJIS['alert']}Недостаточно средств", reply_markup=None, parse_mode="HTML")
                except Exception:
                    pass
                return
                
            await call.answer()
            
            async with conn.execute("SELECT coins, bot_name FROM Users WHERE bot_id = ?", (t_bot_id,)) as cursor:
                t_row = await cursor.fetchone()
                if not t_row:
                    return
                target_coins = Decimal(str(t_row[0] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                target_name = t_row[1]
                
            new_sender_coins = sender_coins - amount
            new_target_coins = target_coins + amount
            
            await conn.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_sender_coins, s_bot_id))
            await conn.execute("UPDATE Users SET coins = ? WHERE bot_id = ?", (new_target_coins, t_bot_id))
            await conn.commit()
            
        try:
            await call.message.edit_text(
                f"{EMOJIS['success']}<b>Вы успешно передали</b> ${amount} <b>на {target_name}</b>", 
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


def get_game_keyboard(amount: Decimal, selected_main: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    b1_style = "primary" if selected_main == "1" else None
    b2_style = "primary" if selected_main == "2" else None
    
    builder.row(
        InlineKeyboardButton(text="1 бросок", callback_data=f"dice_menu_1_{amount}", style=b1_style),
        InlineKeyboardButton(text="2 броска", callback_data=f"dice_menu_2_{amount}", style=b2_style)
    )
    
    if selected_main == "1":
        builder.row(
            InlineKeyboardButton(text="Больше (х2)", callback_data=f"dice_play_1_big_{amount}"),
            InlineKeyboardButton(text="Меньше (х2)", callback_data=f"dice_play_1_small_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="Чёт (х2)", callback_data=f"dice_play_1_even_{amount}"),
            InlineKeyboardButton(text="Нечёт (х2)", callback_data=f"dice_play_1_odd_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="1 (х6)", callback_data=f"dice_play_1_num1_{amount}"),
            InlineKeyboardButton(text="2 (х6)", callback_data=f"dice_play_1_num2_{amount}"),
            InlineKeyboardButton(text="3 (х6)", callback_data=f"dice_play_1_num3_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="4 (х6)", callback_data=f"dice_play_1_num4_{amount}"),
            InlineKeyboardButton(text="5 (х6)", callback_data=f"dice_play_1_num5_{amount}"),
            InlineKeyboardButton(text="6 (х6)", callback_data=f"dice_play_1_num6_{amount}")
        )
        
    elif selected_main == "2":
        builder.row(
            InlineKeyboardButton(text="Оба больше (х4)", callback_data=f"dice_play_2_bothbig_{amount}"),
            InlineKeyboardButton(text="Оба меньше (х4)", callback_data=f"dice_play_2_bothsmall_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="Оба чётные (х4)", callback_data=f"dice_play_2_botheven_{amount}"),
            InlineKeyboardButton(text="Оба нечёт (х4)", callback_data=f"dice_play_2_bothodd_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="1 (х36)", callback_data=f"dice_play_2_num1_{amount}"),
            InlineKeyboardButton(text="2 (х36)", callback_data=f"dice_play_2_num2_{amount}"),
            InlineKeyboardButton(text="3 (х36)", callback_data=f"dice_play_2_num3_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="4 (х36)", callback_data=f"dice_play_2_num4_{amount}"),
            InlineKeyboardButton(text="5 (х36)", callback_data=f"dice_play_2_num5_{amount}"),
            InlineKeyboardButton(text="6 (х36)", callback_data=f"dice_play_2_num6_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="Лесенка вверх (х2.4)", callback_data=f"dice_play_2_ladderup_{amount}"),
            InlineKeyboardButton(text="Лесенка вниз (х2.4)", callback_data=f"dice_play_2_ladderdown_{amount}")
        )
        builder.row(
            InlineKeyboardButton(text="Любая лесенка (х1.2)", callback_data=f"dice_play_2_anyladder_{amount}"),
            InlineKeyboardButton(text="Любой дубль (х6)", callback_data=f"dice_play_2_anydouble_{amount}")
        )

    builder.row(InlineKeyboardButton(text="Отказаться", callback_data=f"dice_cancel_{amount}", style="danger"))
    return builder.as_markup()


def get_continue_keyboard(amount: Decimal) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Продолжить", callback_data=f"dice_continue_{amount}", style="success"),
        InlineKeyboardButton(text="Отказаться", callback_data=f"dice_cancel_{amount}", style="danger")
    )
    return builder.as_markup()


@dp.message(ChatFilter(), lambda m: m.text and (
    m.text.strip().startswith('$') or 
    m.text.strip().endswith('$') or 
    m.text.lower().startswith('бет ') or 
    m.text.lower().startswith('бэт ')
))
async def init_game_dice(message: Message):
    text = message.text.strip()
    amount_str = ""
    
    if text.startswith('$'):
        amount_str = text[1:].strip()
    elif text.endswith('$'):
        amount_str = text[:-1].strip()
    elif text.lower().startswith('бет '):
        amount_str = text[4:].strip()
    elif text.lower().startswith('бэт '):
        amount_str = text[4:].strip()
        
    try:
        if ' ' in amount_str or amount_str.startswith("-"):
            return
        amount_dec = Decimal(amount_str)
        if amount_dec.as_tuple().exponent < -2:
            return
        amount = amount_dec.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    except Exception:
        return
        
    if amount <= 0:
        return
        
    user_data = await get_user_data("real_id", message.from_user.id)
    if not user_data:
        return
        
    bot_id, real_id, coins_val, _, bot_name, _ = user_data
    current_coins = Decimal(str(coins_val or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    if current_coins < amount:
        await message.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
        return
        
    markup = get_game_keyboard(amount=amount, selected_main="none")
    sent_msg = await message.reply(
        f"<b>{bot_name}, выберите исход.</b>\n\n"
        f"<b>Ставка:</b> ${amount}\n"
        f"<b>Баланс:</b> ${current_coins}",
        reply_markup=markup,
        parse_mode="HTML"
    )
    
    GAME_SESSIONS[sent_msg.message_id] = message.from_user.id


@dp.callback_query(lambda c: c.data and c.data.startswith("dice_"))
async def handle_game_clicks(call: CallbackQuery):
    msg_id = call.message.message_id
    data_parts = call.data.split("_")
    action = data_parts[1]
    amount = Decimal(data_parts[-1]).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    user_data = await get_user_data("real_id", call.from_user.id)
    if not user_data:
        await call.answer()
        return
        
    bot_id, real_id, coins_val, _, bot_name, turnover_val = user_data
    current_coins = Decimal(str(coins_val or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    
    if msg_id in GAME_SESSIONS and call.from_user.id != GAME_SESSIONS[msg_id]:
        await call.answer()
        return
    elif msg_id not in GAME_SESSIONS and action != "continue":
        await call.answer()
        return

    if action == "cancel":
        await call.answer()
        GAME_SESSIONS.pop(msg_id, None)
        try:
            await call.message.edit_text(f"<b>{bot_name}</b> отказался от игры", reply_markup=None, parse_mode="HTML")
        except Exception:
            pass
        return
        
    if action == "continue":
        await call.answer()
        if current_coins < amount:
            await call.message.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
            return
            
        markup = get_game_keyboard(amount=amount, selected_main="none")
        try:
            await call.message.edit_text(
                f"<b>{bot_name}, выберите исход.</b>\n\n"
                f"<b>Ставка:</b> ${amount}\n"
                f"<b>Баланс:</b> ${current_coins}",
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception:
            pass
            
        GAME_SESSIONS[msg_id] = call.from_user.id
        return

    if action == "menu":
        await call.answer()
        selected = data_parts[2]
        markup = get_game_keyboard(amount=amount, selected_main=selected)
        try:
            await call.message.edit_reply_markup(reply_markup=markup)
        except Exception:
            pass
        return

    if action == "play":
        await call.answer()
        
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
            
        dice_count = int(data_parts[2])
        choice_type = data_parts[3]
        
        rolls = []
        last_dice_msg = None
        for _ in range(dice_count):
            last_dice_msg = await call.message.answer_dice(emoji="🎲")
            rolls.append(last_dice_msg.dice.value)
            await asyncio.sleep(0.3)
            
        await asyncio.sleep(1.8)
        
        is_win = False
        coef = Decimal('0')
        
        if dice_count == 1:
            r1 = rolls[0]
            if choice_type == "big":
                is_win = (r1 > 3)
                coef = Decimal('2')
            elif choice_type == "small":
                is_win = (r1 < 4)
                coef = Decimal('2')
            elif choice_type == "even":
                is_win = (r1 % 2 == 0)
                coef = Decimal('2')
            elif choice_type == "odd":
                is_win = (r1 % 2 != 0)
                coef = Decimal('2')
            elif choice_type.startswith("num"):
                target = int(choice_type[3:])
                is_win = (r1 == target)
                coef = Decimal('6')
                
        elif dice_count == 2:
            r1, r2 = rolls[0], rolls[1]
            if choice_type == "bothbig":
                is_win = (r1 > 3 and r2 > 3)
                coef = Decimal('4')
            elif choice_type == "bothsmall":
                is_win = (r1 < 4 and r2 < 4)
                coef = Decimal('4')
            elif choice_type == "botheven":
                is_win = (r1 % 2 == 0 and r2 % 2 == 0)
                coef = Decimal('4')
            elif choice_type == "bothodd":
                is_win = (r1 % 2 != 0 and r2 % 2 != 0)
                coef = Decimal('4')
            elif choice_type.startswith("num"):
                target = int(choice_type[3:])
                is_win = (r1 == target or r2 == target)
                coef = Decimal('36')
            elif choice_type == "ladderup":
                is_win = (r1 < r2)
                coef = Decimal('2.4')
            elif choice_type == "ladderdown":
                is_win = (r1 > r2)
                coef = Decimal('2.4')
            elif choice_type == "anyladder":
                is_win = (r1 != r2)
                coef = Decimal('1.2')
            elif choice_type == "anydouble":
                is_win = (r1 == r2)
                coef = Decimal('6')

        async with aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
            async with conn.execute("SELECT coins, turnover FROM Users WHERE bot_id = ?", (bot_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    PENDING_DICE_CALCS.discard(bot_id)
                    return
                fresh_coins = Decimal(str(row[0] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                fresh_turnover = Decimal(str(row[1] or '0.00')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                
            new_turnover = fresh_turnover + amount
            
            if is_win:
                if fresh_coins < amount:
                    await last_dice_msg.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
                    PENDING_DICE_CALCS.discard(bot_id)
                    return
                net_profit = (amount * coef - amount).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                final_coins = fresh_coins + net_profit
                
                await conn.execute("UPDATE Users SET coins = ?, turnover = ? WHERE bot_id = ?", (final_coins, new_turnover, bot_id))
                await conn.commit()
                
                markup = get_continue_keyboard(amount=amount)
                await last_dice_msg.reply(
                    f"{EMOJIS['win']}<b>{bot_name} угадал и получил</b> ${net_profit}<b>!</b>\n"
                    f"<b>Продолжим?</b>\n\n"
                    f"<b>Ставка:</b> ${amount}\n"
                    f"<b>Баланс:</b> ${final_coins}",
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            else:
                if fresh_coins < amount:
                    await last_dice_msg.reply(f"{EMOJIS['alert']}Недостаточно средств", parse_mode="HTML")
                    PENDING_DICE_CALCS.discard(bot_id)
                    return
                final_coins = fresh_coins - amount
                
                await conn.execute("UPDATE Users SET coins = ?, turnover = ? WHERE bot_id = ?", (final_coins, new_turnover, bot_id))
                await conn.commit()
                
                if final_coins >= amount:
                    markup = get_continue_keyboard(amount=amount)
                    await last_dice_msg.reply(
                        f"{EMOJIS['loss']}<b>{bot_name} не угадал и проиграл</b> ${amount}.\n"
                        f"<b>Продолжим?</b>\n\n"
                        f"<b>Ставка:</b> ${amount}\n"
                        f"<b>Баланс:</b> ${final_coins}",
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                else:
                    await last_dice_msg.reply(
                        f"<b>{bot_name} не угадал и проиграл</b> ${amount}.\n\n"
                        f"<b>Ставка:</b> ${amount}\n"
                        f"<b>Баланс:</b> ${final_coins}",
                        parse_mode="HTML"
                    )
                    
        PENDING_DICE_CALCS.discard(bot_id)


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())