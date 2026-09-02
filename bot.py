import asyncio
import logging
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import config
import database as db
import texts
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class Onboarding(StatesGroup):
    name = State()
    goal = State()
    pain = State()


def stars_help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Купить звёзды дёшево", url=config.STARS_SHOP_LINK)]
        ]
    )


def offer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Оформить подписку — {config.SUBSCRIPTION_PRICE_STARS} ⭐", callback_data="pay")],
            [InlineKeyboardButton(text="⭐ У меня нет / не хватает звёзд", callback_data="need_stars")],
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await db.upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name)
    await state.set_state(Onboarding.name)
    await message.answer(texts.WELCOME.format(channel_name=config.CHANNEL_NAME))


@dp.message(Onboarding.name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    await db.save_quiz_answer(message.from_user.id, "quiz_name", name)
    await state.update_data(name=name)
    await state.set_state(Onboarding.goal)
    await message.answer(texts.ASK_GOAL.format(name=name))


@dp.message(Onboarding.goal)
async def process_goal(message: Message, state: FSMContext):
    goal = message.text.strip()
    await db.save_quiz_answer(message.from_user.id, "quiz_goal", goal)
    await state.update_data(goal=goal)
    await state.set_state(Onboarding.pain)
    await message.answer(texts.ASK_PAIN)


@dp.message(Onboarding.pain)
async def process_pain(message: Message, state: FSMContext):
    pain = message.text.strip()
    await db.save_quiz_answer(message.from_user.id, "quiz_pain", pain)
    data = await state.get_data()
    await state.clear()
    await message.answer(
        texts.OFFER.format(
            name=data.get("name", ""),
            goal=data.get("goal", ""),
            pain=pain,
            channel_name=config.CHANNEL_NAME,
        ),
        reply_markup=offer_kb(),
    )


@dp.callback_query(F.data == "need_stars")
async def cb_need_stars(callback):
    await callback.message.answer(texts.NO_STARS_HELP, reply_markup=stars_help_kb())
    await callback.answer()


@dp.callback_query(F.data == "pay")
async def cb_pay(callback):
    await send_subscription_invoice(callback.from_user.id)
    await callback.answer()


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    await send_subscription_invoice(message.from_user.id)


async def send_subscription_invoice(user_id: int):
    await bot.send_invoice(
        chat_id=user_id,
        title=texts.PAYMENT_TITLE.format(channel_name=config.CHANNEL_NAME),
        description=texts.PAYMENT_DESCRIPTION.format(channel_name=config.CHANNEL_NAME),
        payload=f"sub_{user_id}_{int(time.time())}",
        provider_token="",  # для Telegram Stars provider_token не нужен
        currency="XTR",
        prices=[LabeledPrice(label="Подписка на 1 месяц", amount=config.SUBSCRIPTION_PRICE_STARS)],
        subscription_period=config.SUBSCRIPTION_PERIOD_SECONDS,
    )


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    amount = payment.total_amount
    charge_id = payment.telegram_payment_charge_id

    expires_at = int(time.time()) + config.SUBSCRIPTION_PERIOD_SECONDS
    await db.register_payment(user_id, amount, expires_at, charge_id)

    invite_link = await create_one_time_invite(user_id)

    expires_date = datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y")
    await message.answer(
        texts.PAYMENT_SUCCESS.format(
            channel_name=config.CHANNEL_NAME,
            invite_link=invite_link,
            expires_date=expires_date,
        )
    )


async def create_one_time_invite(user_id: int) -> str:
    link = await bot.create_chat_invite_link(
        chat_id=config.CHANNEL_ID,
        member_limit=1,
        name=f"sub_{user_id}",
    )
    return link.invite_link


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    s = await db.get_stats()

    renewals_lines = []
    for row in s["next_renewals"]:
        date_str = datetime.fromtimestamp(row["expires_at"]).strftime("%d.%m %H:%M")
        uname = f"@{row['username']}" if row["username"] else str(row["user_id"])
        renewals_lines.append(f"   • {uname} — {date_str}")
    renewals_block = "\n".join(renewals_lines) if renewals_lines else "   —"

    text = (
        f"📊 <b>Статистика «{config.CHANNEL_NAME}»</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 Всего пользователей: <b>{s['total_users']}</b>\n"
        f"✅ Активных подписок: <b>{s['active_subs']}</b>\n"
        f"⏳ В льготном периоде: <b>{s['in_grace']}</b>\n\n"
        f"🆕 Новых за 24ч: <b>{s['new_today']}</b>\n"
        f"🆕 Новых за 7 дней: <b>{s['new_week']}</b>\n\n"
        f"💰 Доход за всё время: <b>{s['total_revenue']} ⭐</b>\n"
        f"💰 Доход за 7 дней: <b>{s['revenue_week']} ⭐</b>\n\n"
        f"🔜 <b>Ближайшие продления:</b>\n{renewals_block}"
    )
    await message.answer(text)


async def main():
    await db.init_db()
    start_scheduler(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
