import openai
import logging
import asyncio

MAX_RETRIES = 3
DELAY_RETRY = 5  # секунды между попытками

logger = logging.getLogger('post_bot.openai_client')

async def generate_post(messages, model, max_tokens, temperature=0.7, max_len=4096):
    logger.debug(f"Запрос к OpenAI: модель={model}, max_tokens={max_tokens}, temperature={temperature}, max_len={max_len}")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message['content'].strip()
            logger.debug(f"Ответ OpenAI: {text[:100]}...")
            return text[:max_len]
        
        except openai.error.RateLimitError as e:
            logger.warning(f"Лимит запросов OpenAI. Ждём {DELAY_RETRY} сек. Попытка {attempt}/{MAX_RETRIES}.")
            await asyncio.sleep(DELAY_RETRY)
        except openai.error.OpenAIError as e:
            logger.error(f"OpenAI Error: {e}", exc_info=True)
            if attempt < MAX_RETRIES:
                logger.info(f"Повторная попытка через {DELAY_RETRY} секунд. Попытка {attempt+1}/{MAX_RETRIES}")
                await asyncio.sleep(DELAY_RETRY)
            else:
                logger.critical(f"Превышено кол-во попыток. Ошибка: {e}")
                raise
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}", exc_info=True)
            if attempt < MAX_RETRIES:
                logger.info(f"Повтор через {DELAY_RETRY} сек. Попытка {attempt+1}/{MAX_RETRIES}")
                await asyncio.sleep(DELAY_RETRY)
            else:
                logger.critical(f"Превышено кол-во попыток. Ошибка: {e}")
                raise
