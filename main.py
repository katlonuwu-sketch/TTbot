import asyncio
import random
import os
import aiohttp
import subprocess

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Вставьте сюда новый токен от @BotFather
TOKEN = "8526452808:AAE19ub3ECJMzipHozNAuvKdkDr-K4EsMe4"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# История видео для каждого пользователя
used_videos = {}  # chat_id -> set()


async def get_videos(keywords="funny"):
    url = "https://www.tikwm.com/api/feed/search"
    params = {"keywords": keywords, "count": 30}

    ssl_context = False  # Отключаем проверку SSL для TikWM

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, ssl=ssl_context, timeout=10) as resp:
                data = await resp.json()
        except Exception:
            return []

    videos = []
    for item in data.get("data", {}).get("videos", []):
        play_url = item.get("play")
        if play_url:
            videos.append(play_url)
    return videos


def get_keyboard(tags):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Дальше", callback_data=f"next:{tags}")]
    ])


@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Используй команду /tt <хештег>, чтобы получить видео.\nНапример: /tt funny cats")


@dp.message(F.text.startswith("/tt "))
async def handle_t_command(message: Message):
    tags = message.text[3:].strip().replace("#", "")
    if not tags:
        await message.answer("Пожалуйста, укажи хештеги после команды /tt")
        return
    await send_video(message.chat.id, tags)


@dp.callback_query(F.data.startswith("next:"))
async def next_video(callback: CallbackQuery):
    tags = callback.data.split(":")[1]
    await callback.answer()
    await send_video(callback.message.chat.id, tags)


async def send_video(chat_id, tags):
    videos = await get_videos(tags)

    if chat_id not in used_videos:
        used_videos[chat_id] = set()

    new_videos = [v for v in videos if v not in used_videos[chat_id]]

    if not new_videos:
        used_videos[chat_id].clear()
        new_videos = videos

    if not new_videos:
        await bot.send_message(chat_id, "Не нашёл видео 😢")
        return

    url = random.choice(new_videos)
    used_videos[chat_id].add(url)

    filename = f"video_{chat_id}_{random.randint(0,10000)}.mp4"

    try:
        # Загружаем видео через yt-dlp с проверкой ошибок
        process = await asyncio.create_subprocess_exec(
            "yt-dlp", "-o", filename, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            await bot.send_message(chat_id, f"Ошибка загрузки видео:\n{stderr.decode()}")
            return

        # Проверяем размер файла (Telegram ограничивает до 50 МБ для бота)
        if os.path.getsize(filename) > 50 * 1024 * 1024:
            await bot.send_message(chat_id, "Видео слишком большое для отправки через бота.")
            return

        # Отправляем видео
        video = FSInputFile(filename)
        await bot.send_video(chat_id, video, reply_markup=get_keyboard(tags))

    except Exception as e:
        await bot.send_message(chat_id, f"Ошибка: {e}")

    finally:
        if os.path.exists(filename):
            os.remove(filename)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())