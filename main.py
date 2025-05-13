from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.enums import ContentType
from dotenv import load_dotenv
import asyncio
import os
import logging
from collections import defaultdict

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

CHANNEL_A_ID = os.getenv("CHANNEL_A_ID")
CHANNEL_B_ID = int(os.getenv("CHANNEL_B_ID"))

class ProductState(StatesGroup):
    waiting_for_media = State()
    waiting_for_description = State()
    waiting_for_price_a = State()
    waiting_for_price_b = State()

media_groups = defaultdict(list)

def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚀 Start")
    builder.button(text="🏁 Finish")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

@dp.message(Command("start"))
@dp.message(lambda message: message.text == "🚀 Start")
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    media_groups.pop(message.from_user.id, None)
    await state.set_data({"media": []})
    await state.set_state(ProductState.waiting_for_media)
    await message.answer(
        "📷 Отправляйте фото и видео товара в любом порядке.\n"
        "Нажмите 🏁 Finish когда закончите",
        reply_markup=main_keyboard()
    )

@dp.message(ProductState.waiting_for_media, lambda msg: msg.media_group_id)
async def handle_media_group(message: types.Message):
    try:
        if message.photo:
            media_groups[message.from_user.id].append({
                "type": "photo",
                "file_id": message.photo[-1].file_id
            })
        elif message.video:
            media_groups[message.from_user.id].append({
                "type": "video",
                "file_id": message.video.file_id
            })
    except Exception as e:
        logging.error(f"Ошибка медиагруппы: {e}")

@dp.message(Command("done"))
@dp.message(lambda message: message.text == "🏁 Finish")
async def handle_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Добавляем медиа из группы
    if message.from_user.id in media_groups:
        data["media"].extend(media_groups[message.from_user.id])
        media_groups.pop(message.from_user.id)
    
    if not data["media"]:
        await message.answer("❌ Нет медиа для публикации!", reply_markup=main_keyboard())
        return
    
    await state.update_data(data)
    await state.set_state(ProductState.waiting_for_description)
    await message.answer(
        f"✅ Загружено медиа: {len(data['media'])}\n"
        "📝 Введите общее описание для поста:",
        reply_markup=main_keyboard()
    )

@dp.message(ProductState.waiting_for_media)
async def handle_media(message: types.Message, state: FSMContext):
    try:
        media_item = None
        if message.photo:
            media_item = {
                "type": "photo", 
                "file_id": message.photo[-1].file_id
            }
        elif message.video:
            media_item = {
                "type": "video",
                "file_id": message.video.file_id
            }
        
        if media_item:
            async with state.proxy() as data:
                data["media"].append(media_item)
            await message.answer(
                f"✅ Добавлено {media_item['type']}. Всего: {len(data['media'])}",
                reply_markup=main_keyboard()
            )
        else:
            await message.answer("⚠️ Отправьте фото или видео!", reply_markup=main_keyboard())

    except Exception as e:
        logging.error(f"Ошибка обработки медиа: {e}")

@dp.message(ProductState.waiting_for_description)
async def handle_description(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Введите описание!", reply_markup=main_keyboard())
        return
    
    await state.update_data(description=message.text)
    await state.set_state(ProductState.waiting_for_price_a)
    await message.answer("💰 Введите розничную цену (сом):", reply_markup=main_keyboard())

@dp.message(ProductState.waiting_for_price_a)
async def handle_price_a(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число!", reply_markup=main_keyboard())
        return
    
    await state.update_data(price_a=message.text)
    await state.set_state(ProductState.waiting_for_price_b)
    await message.answer("💰 Введите оптовую цену (сом):", reply_markup=main_keyboard())

@dp.message(ProductState.waiting_for_price_b)
async def handle_price_b(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число!", reply_markup=main_keyboard())
        return

    try:
        data = await state.get_data()
        
        # Формируем медиа-альбомы
        def create_media_group(price, caption_suffix):
            media = []
            for i, item in enumerate(data["media"]):
                caption = f"🏷 {data['description']}\n💵 {caption_suffix}: {price} СОМ" if i == 0 else None
                
                if item["type"] == "photo":
                    media.append(types.InputMediaPhoto(
                        media=item["file_id"],
                        caption=caption
                    ))
                else:
                    media.append(types.InputMediaVideo(
                        media=item["file_id"],
                        caption=caption
                    ))
            return media

        # Для розничного канала
        retail_media = create_media_group(data["price_a"], "Цена:")
        await bot.send_media_group(CHANNEL_A_ID, media=retail_media)

        # Для оптового канала
        wholesale_media = create_media_group(message.text, "Цена:")
        await bot.send_media_group(CHANNEL_B_ID, media=wholesale_media)
        
        await message.answer("✅ Пост опубликован в оба канала!", reply_markup=main_keyboard())
    
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=main_keyboard())
    
    finally:
        await state.clear()

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))