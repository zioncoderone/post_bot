import asyncio
import json
import logging
import openai
from scheduler import schedule_tasks
from telegram import Bot
from sheets_client import (
    ensure_month_sheet,
    publish_unpublished_posts,
    get_gsheet_client
)
from openai_client import generate_post
from telegram_client import send_second_post
import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
import os
import colorlog
from logging.handlers import RotatingFileHandler
import calendar

load_dotenv()

handler = colorlog.StreamHandler()
handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s [%(filename)s:%(lineno)d]",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )
)

logger = colorlog.getLogger('post_bot')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

file_handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s [%(filename)s:%(lineno)d]",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )
)
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

async def publish_daily_post(sheet, config, bot):
    logger.debug("Ежедневная публикация основного поста.")
    now = datetime.datetime.now(pytz.timezone(config["timezone"]))
    year, month, day = now.year, now.month, now.day

    await ensure_month_sheet(sheet, year, month, config)
    await publish_unpublished_posts(sheet, year, month, day, config, bot)

    d_in_month = calendar.monthrange(year, month)[1]
    if day == d_in_month:
        next_year = year
        next_month = month + 1
        if next_month == 13:
            next_month = 1
            next_year += 1
        logger.info(f"Последний день месяца {year}-{month:02d}. Создаём лист {next_year}-{next_month:02d} для следующего месяца.")
        await ensure_month_sheet(sheet, next_year, next_month, config)


async def publish_second_post(bot, config):
    logger.debug("Публикация дополнительного поста.")
    # Изменённые тексты для второго поста:
    second_text = await generate_post(
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — супер-маркетолог по продажам запчастей для спецтехники. Пиши ярко, убедительно и объемно (около 1500-2000 символов). "
                    "Призывай к общению в чат-боте, к заявкам, упоминай скидки и акции, используй смайлы, чтобы мотивировать читателя."
                )
            },
            {
                "role": "user",
                "content": (
                    "Напиши привлекательный, продающий пост для продаж запчастей для спецтехники. Мотивируй читателя оставить заявку в чат-боте, "
                    "предложи акции, скидки, общение, используй смайлы и сделай текст максимально заманчивым."
                )
            },
        ],
        model=config["model_second"],
        max_tokens=600,
        temperature=0.7,
        max_len=config["second_post_max_len"],
    )
    await send_second_post(bot, config["chat_id"], config["image_url"], second_text, config["bot_username"])

async def initial_check(sheet, config, bot):
    now = datetime.datetime.now(pytz.timezone(config["timezone"]))
    year, month, day = now.year, now.month, now.day

    prev_year, prev_month = year, month - 1
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    await ensure_month_sheet(sheet, prev_year, prev_month, config)
    prev_days = calendar.monthrange(prev_year, prev_month)[1]
    await publish_unpublished_posts(sheet, prev_year, prev_month, prev_days, config, bot)

    await ensure_month_sheet(sheet, year, month, config)
    nine_am_today = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now > nine_am_today:
        await publish_unpublished_posts(sheet, year, month, day, config, bot)
    else:
        if day > 1:
            await publish_unpublished_posts(sheet, year, month, day - 1, config, bot)

async def main():
    logger.debug("Запуск бота.")
    config = {
        "telegram_token": os.getenv("TELEGRAM_TOKEN"),
        "chat_id": os.getenv("CHAT_ID"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "spreadsheet_id": os.getenv("SPREADSHEET_ID"),
        "bot_username": os.getenv("BOT_USERNAME"),
        "image_url": os.getenv("IMAGE_URL"),
        "model_main": os.getenv("MODEL_MAIN"),
        "model_second": os.getenv("MODEL_SECOND"),
        "main_post_max_len": int(os.getenv("MAIN_POST_MAX_LEN", 4096)),
        "second_post_max_len": int(os.getenv("SECOND_POST_MAX_LEN", 1024)),
        "timezone": os.getenv("TIMEZONE", "Europe/Moscow"),
    }

    config["daily_post_hour"] = int(os.getenv("DAILY_POST_HOUR", 9))
    config["daily_post_minute"] = int(os.getenv("DAILY_POST_MINUTE", 0))
    config["second_post_times"] = json.loads(os.getenv("SECOND_POST_TIMES", '[{"hour":12,"minute":0},{"hour":15,"minute":0},{"hour":18,"minute":0}]'))

    openai.api_key = config["openai_api_key"]

    try:
        sheet = await get_gsheet_client("credentials.json", config["spreadsheet_id"])
        bot = Bot(token=config["telegram_token"])
    except Exception as e:
        logger.error(f"Ошибка инициализации клиентов: {e}", exc_info=True)
        return

    await initial_check(sheet, config, bot)

    scheduler = AsyncIOScheduler(timezone=config["timezone"])
    await schedule_tasks(
        scheduler,
        config["daily_post_hour"],
        config["daily_post_minute"],
        config["second_post_times"],
        publish_daily_post,
        publish_second_post,
        sheet, config, bot
    )
    scheduler.start()
    logger.info("Бот запущен и работает.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
