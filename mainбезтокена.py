import asyncio
import logging
import aiosqlite
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

# ==================== НАСТРОЙКИ ====================
TOKEN = "бебебубубу"
ADMIN_CHAT_ID = -1004407848955
DB_PATH = "bot_database.db"

# ==================== БАЗА ДАННЫХ ====================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT,
                age INTEGER,
                city TEXT,
                photo_id TEXT,
                bio TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await db.commit()

async def save_user_profile(user_id: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, username, name, age, city, photo_id, bio, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (user_id, data['username'], data['name'], data['age'], data['city'], data['photo_id'], data['bio']))
        await db.commit()

async def update_user_status(user_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        await db.commit()

async def get_random_profile(current_user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("""
            SELECT * FROM users
            WHERE status = 'approved' AND user_id != ?
            ORDER BY RANDOM() LIMIT 1
        """, (current_user_id,)) as cursor:
            return await cursor.fetchone()
async def get_user_profile(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

# Удаление по ID
async def delete_user_by_id(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.commit()

# Поиск ID по юзернейму
async def get_id_by_username(username: str):
    clean_username = username.replace("@", "")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE username LIKE ?", 
            (f"%{clean_username}%",)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# ==================== FSM ====================
class ProfileForm(StatesGroup):
    name = State()
    age = State()
    city = State()
    photo = State()
    bio = State()

# ==================== БОТ И РОУТЕР ====================

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ==================== КЛАВИАТУРЫ ======================
done_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Готово")]
    ],
    resize_keyboard=True
)

def get_search_keyboard(target_user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='❤️ Лайк', callback_data=f'like_{target_user_id}'),
            InlineKeyboardButton(text='👎 Дальше', callback_data='next_profile')
        ]
    ])
        


# ==================== ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ====================

@router.message(Command("del"))
async def admin_delete_profile(message: Message):
    if message.chat.id != ADMIN_CHAT_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Формат: <code>/del [ID]</code> или <code>/del [@username]</code>", parse_mode="HTML")
        return

    target = args[1]
    target_id = None

    if target.isdigit():
        target_id = int(target)
    else:
        target_id = await get_id_by_username(target)

    if target_id:
        await delete_user_by_id(target_id)
        
        await message.answer(f"✅ Анкета пользователя <code>{target_id}</code> удалена из базы.", parse_mode="HTML")
        
        try:
            await bot.send_message(
                target_id, 
                "⚠️ Твоя анкета была удалена администратором."
            )
        except Exception:
            pass
    else:
        await message.answer("❌ Пользователь не найден в базе.")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not message.from_user.username:
        await message.answer('Брат, у тебя @юзернейма нет. Сделай в настройках и тогда поговорим.',parse_mode='HTML')
        return
    await message.answer("Привет. Бот пока в тестовом режиме, работает не все а что работает работает с нюансами, но базовый функционал есть. Напиши имя")
    await state.set_state(ProfileForm.name)

@router.message(ProfileForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(ProfileForm.age)

@router.message(ProfileForm.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Цифрами введи падла")
        return
    
    await state.update_data(age=int(message.text))
    

    await state.update_data(cities=[])
    
    await message.answer(
        "Из каких ты городов/регионов? Напиши по одному.\n\n"
        "Когда введешь все — нажми кнопку «✅ Готово»",
        reply_markup=done_keyboard
    )
    await state.set_state(ProfileForm.city)


@router.message(ProfileForm.city)
async def process_city(message: Message, state: FSMContext):
    user_text = message.text.strip()
    
    data = await state.get_data()
    user_cities = data.get("cities", [])

    if user_text == "✅ Готово":
        if not user_cities:
            await message.answer("Напиши хотя бы один пж.")
            return

        formatted_cities = ", ".join(user_cities)
        await state.update_data(city=formatted_cities)
        
        await message.answer(
            f"Кайф, брат! Твои регионы: <b>{formatted_cities}</b>.\n\nЗагрузи свое фото:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )
        await state.set_state(ProfileForm.photo)
        return

    user_cities.append(user_text)
    await state.update_data(cities=user_cities)
    
    current_list_str = ", ".join(user_cities)
    
    await message.answer(
        f"Добавлен город: <b>{user_text}</b>\n"
        f"Твой список: <i>{current_list_str}</i>\n\n"
        f"Отправь еще один или нажми «✅ Готово»",
        reply_markup=done_keyboard,
        parse_mode="HTML"
    )

@router.message(ProfileForm.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await message.answer("Теперь напиши что хочешь. Кого ищешь, чем увлекаешься итд:")
    await state.set_state(ProfileForm.bio)

@router.message(ProfileForm.photo)
async def process_photo_invalid(message: Message):
    await message.answer("Картинку пж.")

@router.message(ProfileForm.bio)
async def process_bio(message: Message, state: FSMContext):
    await state.update_data(bio=message.text)
    
    username = message.from_user.username
    username_str = f"@{username}" if username else "нет юзернейма"
    await state.update_data(username=username_str)
    
    user_data = await state.get_data()
    
    await save_user_profile(message.from_user.id, user_data)
    await state.clear()
    
    await message.answer("Спасибо! Мы получили твою анкету. Надеюсь.")
    await send_to_moderation(message.from_user.id, user_data)

@router.message(Command('search'))
async def start_search(message: Message):
    profile = await get_random_profile(message.from_user.id)

    if not profile:
        await message.answer('Анкет пока нет. В другой раз брат.')
        
        return

    caption = (
        f"<b>{profile['name']}</b>, {profile['age']}\n"
        f"<b>Город:</b> {profile['city']}\n\n"
        f"<b>О себе:</b> {profile['bio']}"
    )

    await message.answer_photo(
        photo=profile['photo_id'],
        caption=caption,
        reply_markup=get_search_keyboard(profile['user_id']),
        parse_mode='HTML'
    )

@router.callback_query(F.data == 'next_profile')
async def next_profile_handler(callback: CallbackQuery):
    profile = await get_random_profile(callback.from_user.id)
    if not profile:
        await callback.answer('Анкеты кончились', show_alert=True)
        return

    caption = (
        f"<b>{profile['name']}</b>, {profile['age']}\n"
        f"<b>Город:</b> {profile['city']}\n\n"
        f"<b>О себе:</b> {profile['bio']}"
    )

    media = types.InputMediaPhoto(media=profile['photo_id'], caption=caption, parse_mode="HTML")
    
    try:
        await callback.message.edit_media(
            media=media,
            reply_markup=get_search_keyboard(profile['user_id'])
        )
    except TelegramBadRequest:
        pass
    finally:
        await callback.answer()

    
@router.callback_query(F.data.startswith("like_"))
async def like_profile_handler(callback: CallbackQuery):
    target_user_id = int(callback.data.split("_")[1])
    liker_id = callback.from_user.id                   
    
    liker_profile = await get_user_profile(liker_id)
    
    if liker_profile:
        username = liker_profile['username']
        
        caption = (
            f"💖 <b>Ты понравился этому человеку!</b>\n\n"
            f"<b>{liker_profile['name']}</b>, {liker_profile['age']}\n"
            f"<b>Город:</b> {liker_profile['city']}\n"
            f"<b>О себе:</b> {liker_profile['bio']}\n\n"
            f"👉 Связаться: {username}"
        )        
        reply_markup = None
        if username and username != "нет юзернейма":
            clean_username = username.replace("@", "")
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Написать", url=f"https://t.me/{clean_username}")]
            ])

        try:
            await bot.send_photo(
                chat_id=target_user_id,
                photo=liker_profile['photo_id'],
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить лайк пользователю {target_user_id}: {e}")

    await callback.answer("❤️ Лайк отправлен!", show_alert=True)
    
    await next_profile_handler(callback)

# ==================== МОДЕРАЦИЯ ====================

async def send_to_moderation(user_id: int, data: dict):
    caption = (
        f"<b>Имя:</b> {data['name']}\n"
        f"<b>Возраст:</b> {data['age']}\n"
        f"<b>Город:</b> {data['city']}\n"
        f"<b>О себе:</b> {data['bio']}\n"
        f"{data['username']}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user_id}")
        ]
    ])
    
    await bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=data['photo_id'],
        caption=caption,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("approve_"))
async def approve_profile(callback: CallbackQuery):
    target_user_id = int(callback.data.split("_")[1])
    await update_user_status(target_user_id, "approved")
    
    try:
        await bot.send_message(target_user_id, "Поздравляем! Твоя анкета прошла модерацию. Теперь ты можешь написать /search и смотреть другие анкеты")
    except Exception as e:
        logging.error(f"Ошибка отправки юзеру {target_user_id}: {e}")
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n<b>СТАТУС:✅ ОДОБРЕНО</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    await callback.answer("Анкета одобрена!")

@router.callback_query(F.data.startswith("reject_"))
async def reject_profile(callback: CallbackQuery):
    target_user_id = int(callback.data.split("_")[1])
    await update_user_status(target_user_id, "rejected")
    
    try:
        await bot.send_message(
            target_user_id, 
            "❌ К сожалению, твоя анкета была отклонена модератором.\nОтправь /start, чтобы заполнить заново."
        )
    except Exception as e:
        logging.error(f"Ошибка отправки юзеру {target_user_id}: {e}")
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n<b>СТАТУС: ❌ ОТКЛОНЕНО</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    await callback.answer("Анкета отклонена!")

# ==================== ЗАПУСК ====================

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
