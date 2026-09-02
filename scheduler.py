import time
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import config
import database as db
import texts
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


def stars_help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Купить звёзды дёшево", url=config.STARS_SHOP_LINK)]
        ]
    )


async def check_subscriptions(bot: Bot):
    now = int(time.time())
    users = await db.get_all_subscribed()

    for user in users:
        user_id = user["user_id"]
        expires_at = user["expires_at"]

        if now < expires_at:
            continue  # подписка ещё активна, автопродление Telegram должно сработать само

        grace_started_at = user["grace_started_at"]
        reminder_stage = user["reminder_stage"]

        if grace_started_at == 0:
            # Автопродление не прошло — начинаем льготный период
            await db.set_grace(user_id, now, 1)
            days_left = config.GRACE_PERIOD_DAYS
            await send_reminder(bot, user_id, days_left)
            continue

        days_elapsed = (now - grace_started_at) // 86400

        if days_elapsed >= config.GRACE_PERIOD_DAYS:
            await kick_user(bot, user_id)
            continue

        # Отправляем максимум одно напоминание в день
        current_day_stage = days_elapsed + 1
        if current_day_stage > reminder_stage:
            days_left = config.GRACE_PERIOD_DAYS - days_elapsed
            await db.set_grace(user_id, grace_started_at, current_day_stage)
            await send_reminder(bot, user_id, days_left)


async def send_reminder(bot: Bot, user_id: int, days_left: int):
    try:
        await bot.send_message(
            user_id,
            texts.REMINDER_LOW_BALANCE.format(channel_name=config.CHANNEL_NAME, days_left=days_left),
            reply_markup=stars_help_kb(),
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.warning(f"Не удалось отправить напоминание {user_id}: {e}")


async def kick_user(bot: Bot, user_id: int):
    try:
        await bot.ban_chat_member(config.CHANNEL_ID, user_id)
        await bot.unban_chat_member(config.CHANNEL_ID, user_id)  # чтобы мог вернуться после новой оплаты
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.warning(f"Не удалось удалить {user_id} из канала: {e}")

    await db.mark_kicked(user_id)

    try:
        await bot.send_message(user_id, texts.KICKED_MESSAGE.format(channel_name=config.CHANNEL_NAME))
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.warning(f"Не удалось уведомить {user_id} об удалении: {e}")


def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_subscriptions, "interval", hours=1, args=[bot])
    scheduler.start()
    return scheduler
