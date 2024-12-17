import logging
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger('post_bot.telegram_client')

MAX_RETRIES = 3
RETRY_DELAY = 5

async def safe_send_message(bot: Bot, **kwargs):
    for attempt in range(1, MAX_RETRIES +1):
        try:
            res = await bot.send_message(**kwargs)
            await asyncio.sleep(1)
            return res
        except RetryAfter as e:
            logger.warning(f"Flood control. Ждём {e.retry_after} сек. Попытка {attempt}/{MAX_RETRIES}.")
            await asyncio.sleep(e.retry_after + 1)
        except TelegramError as ex:
            logger.error(f"Ошибка при отправке сообщения: {ex}", exc_info=True)
            if attempt < MAX_RETRIES:
                logger.info(f"Повтор через {RETRY_DELAY} секунд.")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.critical("Превышено кол-во попыток отправить сообщение.")
                raise

async def safe_send_photo(bot: Bot, **kwargs):
    for attempt in range(1, MAX_RETRIES +1):
        try:
            res = await bot.send_photo(**kwargs)
            await asyncio.sleep(1)
            return res
        except RetryAfter as e:
            logger.warning(f"Flood control при отправке фото. Ждём {e.retry_after} сек.")
            await asyncio.sleep(e.retry_after + 1)
        except TelegramError as ex:
            logger.error(f"Ошибка при отправке фото: {ex}", exc_info=True)
            if attempt < MAX_RETRIES:
                logger.info(f"Повтор через {RETRY_DELAY} сек.")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.critical("Превышено кол-во попыток отправить фото.")
                raise

async def send_main_post(bot, chat_id, text, bot_username):
    button = InlineKeyboardButton("Отправить заявку", url=f"https://t.me/{bot_username}?start=from_post")
    markup = InlineKeyboardMarkup([[button]])
    try:
        await safe_send_message(bot, chat_id=chat_id, text=text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка при отправке основного поста: {e}", exc_info=True)

async def send_second_post(bot, chat_id, image_url, text, bot_username):
    button = InlineKeyboardButton("Отправить заявку", url=f"https://t.me/{bot_username}?start=from_post")
    markup = InlineKeyboardMarkup([[button]])
    try:
        await safe_send_photo(bot, chat_id=chat_id, photo=image_url, caption=text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка при отправке второго поста: {e}", exc_info=True)
