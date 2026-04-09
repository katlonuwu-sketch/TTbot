import asyncio
import random
import os
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)

TOKEN = "8526452808:AAE19ub3ECJMzipHozNAuvKdkDr-K4EsMe4"

bot = Bot(token=TOKEN)
dp = Dispatcher()

used_media = {}   # история
user_mode = {}    # режим пользователя: video / photo / all


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
        # видео
        if item.get("play"):
            media.append({
                "type": "video",
                "url": item["play"]
            })

        # фото
        images = item.get("images") or item.get("image_post_info", {}).get("images", [])

        image_urls = []
        for img in images:
            if isinstance(img, dict):
                img_url = img.get("url") or img.get("image")
            else:
                img_url = img

            if img_url:
                image_urls.append(img_url)

        if image_urls:
            media.append({
                "type": "album",
                "urls": image_urls
            })

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
async def start(message: Message):
    await message.answer(
        "Команды:\n"
        "/tt <запрос>\n"
        "/mode — выбрать режим"
    )


@dp.message(F.text == "/mode")
async def mode_command(message: Message):
    await message.answer("Выбери режим:", reply_markup=get_mode_keyboard())


@dp.callback_query(F.data.startswith("mode:"))
async def set_mode(callback: CallbackQuery):
    mode = callback.data.split(":")[1]
    user_mode[callback.from_user.id] = mode

    text = {
        "video": "📹 Режим: только видео",
        "photo": "🖼 Режим: только фото",
        "all": "🔀 Режим: всё"
    }

    await callback.answer()
    await callback.message.answer(text.get(mode, "Ок"))


@dp.message(F.text.startswith("/tt "))
async def handle_t_command(message: Message):
    tags = message.text[3:].strip().replace("#", "")

    if not tags:
        await message.answer("Укажи запрос 😢")
        return

    await send_media(message.chat.id, message.from_user.id, tags)


@dp.callback_query(F.data.startswith("next:"))
async def next_media(callback: CallbackQuery):
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

    # -------- ВИДЕО --------
    if item["type"] == "video":
        filename = f"video_{chat_id}_{random.randint(0,10000)}.mp4"

        try:
            process = await asyncio.create_subprocess_exec(
                "yt-dlp", "-o", filename, item["url"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if os.path.exists(filename):
                video = FSInputFile(filename)
                await bot.send_video(chat_id, video, reply_markup=get_next_keyboard(tags))

        finally:
            if os.path.exists(filename):
                os.remove(filename)

    # -------- АЛЬБОМ --------
    elif item["type"] == "album":
        try:
            media_group = [
                InputMediaPhoto(media=url)
                for url in item["urls"][:10]
            ]

            await bot.send_media_group(chat_id, media_group)
            await bot.send_message(chat_id, "➡️ Дальше", reply_markup=get_next_keyboard(tags))

        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка: {e}")


# -------------------- RUN --------------------

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
