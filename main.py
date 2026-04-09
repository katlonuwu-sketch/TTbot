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

# История отправленного
used_media = {}  # chat_id -> set()


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
        # 📹 Видео
        if item.get("play"):
            media.append({
                "type": "video",
                "url": item["play"]
            })

        # 📸 Фото-пост (альбом)
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


def get_keyboard(tags):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Дальше", callback_data=f"next:{tags}")]
    ])


@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "Используй команду:\n"
        "/tt <хештег>\n\n"
        "Пример:\n"
        "/tt funny cats"
    )


@dp.message(F.text.startswith("/tt "))
async def handle_t_command(message: Message):
    tags = message.text[3:].strip().replace("#", "")

    if not tags:
        await message.answer("Укажи хештег 😢")
        return

    await send_media(message.chat.id, tags)


@dp.callback_query(F.data.startswith("next:"))
async def next_media(callback: CallbackQuery):
    tags = callback.data.split(":")[1]
    await callback.answer()
    await send_media(callback.message.chat.id, tags)


async def send_media(chat_id, tags):
    media_list = await get_media(tags)

    if chat_id not in used_media:
        used_media[chat_id] = set()

    # фильтр повторов
    def get_key(item):
        if item["type"] == "video":
            return item["url"]
        else:
            return tuple(item["urls"])

    new_items = [m for m in media_list if get_key(m) not in used_media[chat_id]]

    if not new_items:
        used_media[chat_id].clear()
        new_items = media_list

    if not new_items:
        await bot.send_message(chat_id, "Ничего не нашёл 😢")
        return

    item = random.choice(new_items)
    used_media[chat_id].add(get_key(item))

    # 📹 Видео
    if item["type"] == "video":
        filename = f"video_{chat_id}_{random.randint(0,10000)}.mp4"

        try:
            process = await asyncio.create_subprocess_exec(
                "yt-dlp", "-o", filename, item["url"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                await bot.send_message(chat_id, f"Ошибка загрузки:\n{stderr.decode()}")
                return

            if os.path.exists(filename):
                video = FSInputFile(filename)
                await bot.send_video(chat_id, video, reply_markup=get_keyboard(tags))

        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка: {e}")

        finally:
            if os.path.exists(filename):
                os.remove(filename)

    # 📸 Альбом (несколько фото)
    elif item["type"] == "album":
        try:
            media_group = []

            for url in item["urls"][:10]:  # максимум 10
                media_group.append(InputMediaPhoto(media=url))

            await bot.send_media_group(chat_id, media_group)

            # кнопка отдельно
            await bot.send_message(chat_id, "➡️ Дальше", reply_markup=get_keyboard(tags))

        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка альбома: {e}")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
