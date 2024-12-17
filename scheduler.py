from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

logger = logging.getLogger('post_bot.scheduler')

async def schedule_tasks(scheduler, daily_hour, daily_minute, second_times, publish_daily, publish_second, sheet, config, bot):
    logger.debug("Настройка расписания.")

    # Ежедневный пост в 9:00
    scheduler.add_job(
        publish_daily,
        'cron',
        hour=daily_hour,
        minute=daily_minute,
        id='daily_post',
        name='Ежедневный основной пост',
        args=[sheet, config, bot]
    )
    logger.info(f"Ежедневный пост в {daily_hour:02d}:{daily_minute:02d}.")

    # Дополнительные посты
    for idx, st in enumerate(second_times, start=1):
        scheduler.add_job(
            publish_second,
            'cron',
            hour=st["hour"],
            minute=st["minute"],
            id=f'second_post_{idx}',
            name=f'Дополнительный пост {idx}',
            args=[bot, config]
        )
        logger.info(f"Доп. пост {idx} в {st['hour']:02d}:{st['minute']:02d}.")
