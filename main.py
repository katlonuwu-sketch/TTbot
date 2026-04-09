import asyncio
import random
import os
import aiohttp

from collections import defaultdict

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

# ================== ДАННЫЕ ==================

used_media = defaultdict(set)
user_preferences = defaultdict(lambda: {
    "likes": defaultdict(int),
    "dislikes": defaultdict(int)
})

media_cache = {}  # media_id -> item


# ================== API ==================

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
        tags = item.get("title", "").lower().split()

        # 📹 Видео
        if item.get("play"):
            media.append({
                "type": "video",
                "url": item["play"],
                "tags": tags
            })

        # 📸 Альбом
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
                "urls": image_urls,
                "tags": tags
            })

    return media


# ================== AI РЕКОМЕНДАЦИИ ==================

def score_item(user_id, item):
    prefs = user_preferences[user_id]
    score = 0

    for tag in item["tags"]:
        score += prefs["likes"][tag] * 2
        score -= prefs["dislikes"][tag] * 3

    score += random.uniform(0, 1)
    return score


def pick_best(user_id, items):
    if not items:
        return None

    scored = [(score_item(user_id, i), i) for i in items]
    scored.sort(key=lambda x: x[0], reverse=True)

    return scored[0][1]


# ================== КНОПКИ ==================

def get_keyboard(media_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍", callback_data=f"like:{media_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"dislike:{media_id}")
        ],
        [
            InlineKeyboardButton(text="➡️ Дальше", callback_data=f"next:{media_id}")
        ]
    ])


# ================== ХЕНДЛЕРЫ ==================

@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "🔥 Умный TikTok бот\n\n"
        "/tt <запрос>\n\n"
        "Жми 👍 или 👎 чтобы я учился"
    )


@dp.message(F.text.startswith("/tt "))
async def handle_t(message: Message):
    tags = message.text[3:].strip().replace("#", "")

    if not tags:
        await message.answer("Напиши что искать 😢")
        return

    await send_media(message.chat.id, tags)


@dp.callback_query(F.data.startswith("next:"))
async def next_media(callback: CallbackQuery):
    media_id = callback.data.split(":")[1]
    item = media_cache.get(media_id)

    if not item:
        return await callback.answer("Старое сообщение")

    await callback.answer()
    await send_media(callback.message.chat.id, " ".join(item["tags"]))


@dp.callback_query(F.data.startswith("like:"))
async def like(callback: CallbackQuery):
    media_id = callback.data.split(":")[1]
    item = media_cache.get(media_id)

    if not item:
        return await callback.answer("Старое сообщение")

    user_id = callback.from_user.id

    for t in item["tags"]:
        user_preferences[user_id]["likes"][t] += 1

    await callback.answer("👍 Учту")


@dp.callback_query(F.data.startswith("dislike:"))
async def dislike(callback: CallbackQuery):
    media_id = callback.data.split(":")[1]
    item = media_cache.get(media_id)

    if not item:
        return await callback.answer("Старое сообщение")

    user_id = callback.from_user.id

    for t in item["tags"]:
        user_preferences[user_id]["dislikes"][t] += 1

    await callback.answer("👎 Понял")


# ================== ОТПРАВКА ==================

async def send_media(chat_id, tags):
    media_list = await get_media(tags)

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

    item = pick_best(chat_id, new_items)
    used_media[chat_id].add(get_key(item))

    # 🔑 создаём ID
    media_id = str(random.randint(100000, 999999))
    media_cache[media_id] = item

    # 📹 Видео
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
                await bot.send_video(
                    chat_id,
                    video,
                    reply_markup=get_keyboard(media_id)
                )

        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка: {e}")

        finally:
            if os.path.exists(filename):
                os.remove(filename)

    # 📸 Альбом
    elif item["type"] == "album":
        try:
            media_group = [
                InputMediaPhoto(media=url)
                for url in item["urls"][:10]
            ]

            await bot.send_media_group(chat_id, media_group)

            await bot.send_message(
                chat_id,
                "Оцени 👇",
                reply_markup=get_keyboard(media_id)
            )

        except Exception as e:
            await bot.send_message(chat_id, f"Ошибка: {e}")


# ================== ЗАПУСК ==================

async def main():
    # фикс конфликта
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
