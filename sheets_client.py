import gspread
import logging
from gspread_formatting import format_cell_range, CellFormat, Color, TextFormat
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import calendar
from openai_client import generate_post
import re

logger = logging.getLogger('post_bot.sheets_client')

async def get_gsheet_client(creds_path="credentials.json", spreadsheet_id=None):
    if not spreadsheet_id:
        logger.error("Не указан spreadsheet_id.")
        raise ValueError("Необходимо указать spreadsheet_id.")
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        logger.debug(f"Загрузка учётных данных из {creds_path}.")
        creds = await asyncio.to_thread(ServiceAccountCredentials.from_json_keyfile_name, creds_path, scope)
        client = await asyncio.to_thread(gspread.authorize, creds)
        spreadsheet = await asyncio.to_thread(client.open_by_key, spreadsheet_id)
        logger.debug(f"Открыта таблица с ID {spreadsheet_id}.")
        return spreadsheet
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Таблица {spreadsheet_id} не найдена.")
        raise
    except FileNotFoundError:
        logger.error(f"Файл учётных данных {creds_path} не найден.")
        raise
    except Exception as e:
        logger.error(f"Ошибка инициализации клиента Google Sheets: {e}", exc_info=True)
        raise

async def get_unpublished_posts(sheet, m_name):
    try:
        worksheet = await asyncio.to_thread(sheet.worksheet, m_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(f"Лист {m_name} не найден.")
        return []
    
    data = await asyncio.to_thread(worksheet.get_all_values)
    rows = data[1:]
    unpublished = []
    for i, row in enumerate(rows, start=2):
        post_number_str = row[0].strip() if len(row) > 0 else ""
        topic = row[1].strip() if len(row) > 1 else ""
        status = row[2].strip() if len(row) > 2 else ""
        if status.lower() != "опубликовано" and topic:
            try:
                post_number = int(post_number_str)
                unpublished.append((i, post_number, topic, worksheet))
            except ValueError:
                logger.warning(f"Неверный номер поста в строке {i}: {post_number_str}")
                continue
    unpublished.sort(key=lambda x: x[1])
    return unpublished

async def update_status_sync(worksheet, row_index):
    try:
        await asyncio.to_thread(worksheet.update_cell, row_index, 3, "Опубликовано")
        green_text_format = CellFormat(
            textFormat=TextFormat(
                bold=True,
                foregroundColor=Color(0, 0.5, 0)
            )
        )
        cell_range = f"C{row_index}"
        await asyncio.to_thread(format_cell_range, worksheet, cell_range, green_text_format)
    except Exception as e:
        logger.error(f"Ошибка обновления статуса поста: {e}", exc_info=True)
        raise

async def ensure_month_sheet(sheet, year, month, config, up_to_day=None):
    m_name = f"{year}-{month:02d}"
    d_in_month = calendar.monthrange(year, month)[1]
    if up_to_day is None:
        up_to_day = d_in_month

    try:
        worksheet = await asyncio.to_thread(sheet.worksheet, m_name)
        data = await asyncio.to_thread(worksheet.get_all_values)
        existing_topics = sum(1 for row in data[1:] if row[1].strip())
        required_topics = d_in_month

        if existing_topics < required_topics:
            missing_topics = required_topics - existing_topics
            logger.info(f"Недостаёт {missing_topics} тем в {m_name}. Генерируем...")
            topics_response = await generate_post(
                messages=[
                    {
                        "role": "system",
                        "content": "Ты — опытный механик по ремонту спецтехники со стажем 30 лет."
                    },
                    {
                        "role": "user",
                        "content": f"Сгенерируй список из {missing_topics} кратких тем для постов о спецтехнике, запчастях и обслуживании. Каждая тема на отдельной строке."
                    },
                ],
                model=config["model_main"],
                max_tokens=1000,
                temperature=0.7,
                max_len=config["main_post_max_len"],
            )
            topics = [re.sub(r'^\d+\.\s*', '', t.strip()) for t in topics_response.split('\n') if t.strip()]
            topics = topics[:missing_topics]

            if worksheet.row_count < required_topics + 1:
                await asyncio.to_thread(worksheet.resize, rows=required_topics + 1)

            for idx, topic in enumerate(topics, start=existing_topics + 1):
                row_data = [str(idx), topic, ""]
                await asyncio.to_thread(worksheet.update, f"A{idx+1}:C{idx+1}", [row_data])
            return m_name, missing_topics
        else:
            logger.info(f"В листе {m_name} уже есть все необходимые темы.")
            return m_name, 0

    except gspread.exceptions.WorksheetNotFound:
        logger.warning(f"Лист {m_name} не найден. Создаю новый.")
        worksheet = await asyncio.to_thread(sheet.add_worksheet, title=m_name, rows=str(d_in_month + 1), cols="3")
        await asyncio.to_thread(worksheet.update, "A1:C1", [["Номер поста", "Тема", "Статус"]])
        logger.info(f"Создан новый лист '{m_name}'.")
        topics_response = await generate_post(
            messages=[
                {
                    "role": "system",
                    "content": "Ты — опытный механик по ремонту спецтехники со стажем 30 лет."
                },
                {
                    "role": "user",
                    "content": f"Сгенерируй список из {d_in_month} кратких самых актуальных тем для постов о спецтехнике, запчастях и обслуживании. Каждая тема на отдельной строке."
                },
            ],
            model=config["model_main"],
            max_tokens=1000,
            temperature=0.7,
            max_len=config["main_post_max_len"],
        )
        topics = [re.sub(r'^\d+\.\s*', '', t.strip()) for t in topics_response.split('\n') if t.strip()]
        topics = topics[:d_in_month]

        for idx, topic in enumerate(topics, start=1):
            row_data = [str(idx), topic, ""]
            await asyncio.to_thread(worksheet.update, f"A{idx+1}:C{idx+1}", [row_data])

        return m_name, d_in_month
    except Exception as e:
        logger.error(f"Ошибка при подготовке листа {m_name}: {e}", exc_info=True)
        raise

async def publish_unpublished_posts(sheet, year, month, up_to_day, config, bot):
    m_name = f"{year}-{month:02d}"
    unpublished_posts = await get_unpublished_posts(sheet, m_name)
    unpublished_posts = [p for p in unpublished_posts if p[1] <= up_to_day]

    logger.debug(f"Найдено {len(unpublished_posts)} неопубликованных постов для {m_name} до дня {up_to_day}.")

    from telegram_client import send_main_post
    for (row_index, post_number, topic, worksheet) in unpublished_posts:
        try:
            # Изменённые тексты для основного поста:
            post_text = await generate_post(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — опытный механик по ремонту спецтехники со стажем 30 лет и работаешь в компании СТАРЭКС уже более 5 лет."
                            "Пиши максимально длинно (около 1500-2000 символов), подробно, профессионально и увлекательно, "
                            "используя смайлы в тексте и заголовках, добавляй в пост всегда хэштеги, дай советы по обслуживанию и ремонту спецтехники, "
                            "привлекай покупателей своим опытом и умением убеждать. В конце поста упомяни себя и компанию СТАРЭКС, "
                            "у которой есть все необходимые запчасти и услуги для ремонта спецтехники."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Напиши подробный, красивый пост со смайликами на тему: '{topic}', поделись своим опытом как механика с опытом, "
                            "дай советы по обслуживанию и ремонту спецтехники, используй смайлы и призывай читателей к действию. "
                            "В конце упомяни СТАРЭКС и то, что у компании СТАРЭКС есть все для ремонта спецтехники."
                        )
                    },
                ],
                model=config["model_main"],
                max_tokens=2000,
                temperature=0.7,
                max_len=config["main_post_max_len"],
            )
            await send_main_post(bot, config["chat_id"], post_text, config["bot_username"])
            logger.info(f"Пост №{post_number} ({m_name}) опубликован.")
            await update_status_sync(worksheet, row_index)
        except Exception as e:
            logger.error(f"Ошибка при публикации поста №{post_number} ({m_name}): {e}", exc_info=True)
