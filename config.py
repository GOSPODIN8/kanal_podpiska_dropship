import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002432900064"))

CHANNEL_NAME = "Клуб Единомышленников"

SUBSCRIPTION_PRICE_STARS = 1111
SUBSCRIPTION_OLD_PRICE_STARS = 1999
SUBSCRIPTION_PERIOD_SECONDS = 30 * 24 * 60 * 60  # 30 дней (требование Telegram: 2592000)

STARS_SHOP_LINK = "https://t.me/suastarsbot?start=user-6147195726"

# Сколько дней длится льготный период после неудачного автопродления,
# прежде чем пользователя удаляют из канала
GRACE_PERIOD_DAYS = 3

DB_PATH = os.getenv("DB_PATH", "subscriptions.db")
