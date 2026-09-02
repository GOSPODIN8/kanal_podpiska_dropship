import aiosqlite
import time
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    quiz_name TEXT,
    quiz_goal TEXT,
    quiz_pain TEXT,
    created_at INTEGER,
    is_subscribed INTEGER DEFAULT 0,
    expires_at INTEGER DEFAULT 0,
    grace_started_at INTEGER DEFAULT 0,
    reminder_stage INTEGER DEFAULT 0,
    total_paid_stars INTEGER DEFAULT 0,
    payments_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    paid_at INTEGER,
    telegram_charge_id TEXT
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def upsert_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, username, full_name, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name""",
            (user_id, username, full_name, int(time.time())),
        )
        await db.commit()


async def save_quiz_answer(user_id: int, field: str, value: str):
    assert field in ("quiz_name", "quiz_goal", "quiz_pain")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cur.fetchone()


async def register_payment(user_id: int, amount: int, expires_at: int, charge_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE users SET is_subscribed = 1, expires_at = ?, grace_started_at = 0,
               reminder_stage = 0, total_paid_stars = total_paid_stars + ?,
               payments_count = payments_count + 1 WHERE user_id = ?""",
            (expires_at, amount, user_id),
        )
        await db.execute(
            "INSERT INTO payments (user_id, amount, paid_at, telegram_charge_id) VALUES (?, ?, ?, ?)",
            (user_id, amount, int(time.time()), charge_id),
        )
        await db.commit()


async def set_grace(user_id: int, grace_started_at: int, reminder_stage: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET grace_started_at = ?, reminder_stage = ? WHERE user_id = ?",
            (grace_started_at, reminder_stage, user_id),
        )
        await db.commit()


async def mark_kicked(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_subscribed = 0, grace_started_at = 0, reminder_stage = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def get_all_subscribed():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE is_subscribed = 1")
        return await cur.fetchall()


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        stats = {}

        cur = await db.execute("SELECT COUNT(*) as c FROM users")
        stats["total_users"] = (await cur.fetchone())["c"]

        cur = await db.execute("SELECT COUNT(*) as c FROM users WHERE is_subscribed = 1")
        stats["active_subs"] = (await cur.fetchone())["c"]

        cur = await db.execute("SELECT COUNT(*) as c FROM users WHERE is_subscribed = 1 AND grace_started_at > 0")
        stats["in_grace"] = (await cur.fetchone())["c"]

        cur = await db.execute("SELECT COALESCE(SUM(total_paid_stars),0) as s FROM users")
        stats["total_revenue"] = (await cur.fetchone())["s"]

        day_ago = int(time.time()) - 86400
        cur = await db.execute("SELECT COUNT(*) as c FROM users WHERE created_at >= ?", (day_ago,))
        stats["new_today"] = (await cur.fetchone())["c"]

        week_ago = int(time.time()) - 7 * 86400
        cur = await db.execute("SELECT COUNT(*) as c FROM users WHERE created_at >= ?", (week_ago,))
        stats["new_week"] = (await cur.fetchone())["c"]

        cur = await db.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE paid_at >= ?", (week_ago,)
        )
        stats["revenue_week"] = (await cur.fetchone())["s"]

        cur = await db.execute(
            """SELECT user_id, username, expires_at FROM users
               WHERE is_subscribed = 1 ORDER BY expires_at ASC LIMIT 5"""
        )
        stats["next_renewals"] = await cur.fetchall()

        return stats
