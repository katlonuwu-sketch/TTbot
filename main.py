import asyncio
import random
from io import BytesIO

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputFile

TOKEN = "8526452808:AAE19ub3ECJMzipHozNAuvKdkDr-K4EsMe4"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# История медиа для каждого чата
used_media = {}  # chat_id -> set()
user_mode = {}   # user_id -> "video", "photo", "all"


# -------------------- API --------------------
async def get_media(keywords="funny"):
    url = "https://www.tikwm.com/api/feed/search"
    params = {"keywords": keywords, "count": 30}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, ssl=False, timeout=10) as resp:
                data = await resp.json()
        except Exception:
            return []

    media = []

    for item in data.get("data", {}).get("videos", []):
        # Видео
        if item.get("play"):
            media.append({"type": "video", "url": item["play"]})

        # Фото
        image_urls = []
        for img in item.get("images", []):
            if isinstance(img, dict):
                url_img = img.get("url") or img.get("origin_url") or img.get("image")
            else:
                url_img = img
            if url_img:
                image_urls.append(url_img)
        for img in item.get("image_post_info", {}).get("images", []):
            if isinstance(img, dict):
                url_img = img.get("url") or img.get("origin_url") or img.get("image")
            else:
                url_img = img
            if url_img and url_img not in image_urls:
                image_urls.append(url_img)
        if image_urls:
            media.append({"type": "album", "urls": image_urls})

    return media


# -------------------- UI --------------------
def get_next_keyboard(tags):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Дальше", callback_data=f"next:{tags}")]
    ])


def get_mode_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Только видео", callback_data="mode:video")],
        [InlineKeyboardButton(text="🖼 Только фото", callback_data="mode:photo")],
        [InlineKeyboardButton(text="🔀 Всё вместе", callback_data="mode:all")]
    ])


# -------------------- COMMANDS --------------------
@dp.message(F.text == "/start")
async def start(message: types.Message):
    await message.answer(
        "Команды:\n"
        "/tt <запрос> — получить фото/видео\n"
        "/mode — выбрать режим"
    )


@dp.message(F.text == "/mode")
async def mode_command(message: types.Message):
    await message.answer("Выбери режим:", reply_markup=get_mode_keyboard())


@dp.callback_query(F.data.startswith("mode:"))
async def set_mode(callback: types.CallbackQuery):
    mode = callback.data.split(":")[1]
    user_mode[callback.from_user.id] = mode

    text = {"video": "📹 Только видео", "photo": "🖼 Только фото", "all": "🔀 Всё вместе"}
    await callback.message.answer(text.get(mode, "Ок"))
    await callback.answer()


@dp.message(F.text.startswith("/tt "))
async def handle_tt(message: types.Message):
    tags = message.text[3:].strip().replace("#", "")
    if not tags:
        await message.answer("Укажи запрос 😢")
        return
    await send_media(message.chat.id, message.from_user.id, tags)


@dp.callback_query(F.data.startswith("next:"))
async def next_media(callback: types.CallbackQuery):
    tags = callback.data.split(":")[1]
    await callback.answer()
    await send_media(callback.message.chat.id, callback.from_user.id, tags)


# -------------------- SEND --------------------
async def send_media(chat_id, user_id, tags):
    media_list = await get_media(tags)

    if chat_id not in used_media:
        used_media[chat_id] = set()

    mode = user_mode.get(user_id, "all")

    # фильтр по режиму
    if mode == "video":
        media_list = [m for m in media_list if m["type"] == "video"]
    elif mode == "photo":
        media_list = [m for m in media_list if m["type"] == "album"]

    def get_key(item):
        return item["url"] if item["type"] == "video" else tuple(item["urls"])

    new_items = [m for m in media_list if get_key(m) not in used_media[chat_id]]

    if not new_items:
        used_media[chat_id].clear()
        new_items = media_list

    if not new_items:
        await bot.send_message(chat_id, "Ничего не нашёл 😢")
        return

    item = random.choice(new_items)
    used_media[chat_id].add(get_key(item))

    # ---- Видео через поток ----
    if item["type"] == "video":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(item["url"]) as resp:
                    if resp.status == 200:
                        video_bytes = await resp.read()
                        if len(video_bytes) > 50 * 1024 * 1024:
                            await bot.send_message(chat_id, "Видео слишком большое для отправки.")
                            return
                        video_file = BytesIO(video_bytes)
                        video_file.name = "video.mp4"
                        await bot.send_video(chat_id, InputFile(video_file), reply_markup=get_next_keyboard(tags))
                    else:
                        await bot.send_message(chat_id, "Не удалось загрузить видео 😢")
        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка при загрузке видео: {e}")

    # ---- Фото (альбом) ----
    elif item["type"] == "album":
        urls = [url if isinstance(url, str) else url.get("url") for url in item["urls"]]
        urls = [u for u in urls if u]
        if not urls:
            await bot.send_message(chat_id, "Нет доступных фото 😢")
            return
        try:
            media_group = [InputMediaPhoto(media=u) for u in urls[:10]]
            await bot.send_media_group(chat_id, media_group)
            await bot.send_message(chat_id, "➡️ Дальше", reply_markup=get_next_keyboard(tags))
        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка при отправке фото: {e}")


# -------------------- RUN --------------------
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
