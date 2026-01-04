import aiosqlite
from pathlib import Path
import time

DB_PATH = Path(__file__).resolve().parent.parent / "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            created_at INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            referred_by INTEGER,
            username TEXT
        )
        """)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 5;")
        except Exception:
            pass
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_daily_refill INTEGER;")
        except Exception:
            pass    
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_active INTEGER;")
        except Exception:
            pass    
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_active_at INTEGER;")
        except Exception:
            pass            
        await db.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            inviter_id INTEGER NOT NULL,
            invitee_id INTEGER NOT NULL UNIQUE,
            created_at INTEGER NOT NULL
        )
        """)

        # События “запросов” (для лимитов)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts INTEGER NOT NULL
        )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_usage_user_ts ON usage_events(user_id, ts)")
        await db.execute("""
        UPDATE users
        SET last_active_at = COALESCE(last_active_at, created_at),
        last_active    = COALESCE(last_active, created_at)
        WHERE last_active_at IS NULL OR last_active IS NULL
        """)
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ref_milestones (
            inviter_id INTEGER NOT NULL,
            milestone INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(inviter_id, milestone)
        )
        """)


        await db.commit()
        


async def ensure_user(user_id: int, username: str | None = None) -> bool:
    """
    Создаёт пользователя, если его нет.
    Возвращает True — если пользователь НОВЫЙ
    Возвращает False — если уже был
    """
    now = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,)
        )
        exists = await cur.fetchone()

        if not exists:
            # новый пользователь → даём стартовые 5 кредитов
            await db.execute(
                """
                INSERT INTO users(user_id, created_at, username, credits, last_active_at, last_active)
                VALUES (?, ?, ?, 5, ?, ?)
                """,
                (user_id, now, username,  now, now)   # ✅ 5 параметра под 5 знака ?
            )
            await db.commit()
            return True

        # пользователь уже есть → обновляем username (если появился)
        if username is not None:
            await db.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id)
            )
            await db.commit()

        return False





async def add_usage(user_id: int, ts: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO usage_events(user_id, ts) VALUES(?, ?)",
            (user_id, ts)
        )
        await db.commit()


async def count_usage(user_id: int, since_ts: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM usage_events WHERE user_id = ? AND ts >= ?",
            (user_id, since_ts)
        )
        (n,) = await cur.fetchone()
        return int(n)


async def oldest_usage_ts(user_id: int, since_ts: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT MIN(ts) FROM usage_events WHERE user_id = ? AND ts >= ?",
            (user_id, since_ts)
        )
        (mn,) = await cur.fetchone()
        return int(mn) if mn is not None else None

def _day_key(ts: int | None = None) -> int:
    t = time.gmtime(ts or int(time.time()))
    return t.tm_year * 10000 + t.tm_mon * 100 + t.tm_mday


async def get_credits(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0


async def spend_credit(user_id: int, amount: int = 1) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        credits = int(row[0]) if row and row[0] is not None else 0

        if credits < amount:
            return False

        await db.execute(
            "UPDATE users SET credits = credits - ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()
        return True


async def daily_refill(user_id: int, per_day: int = 2):
    today = _day_key()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT last_daily_refill FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        last = row[0] if row else None

        if last == today:
            return

        await db.execute(
            "UPDATE users SET credits = credits + ?, last_daily_refill = ? WHERE user_id = ?",
            (per_day, today, user_id)
        )
        await db.commit()

async def add_credits(user_id: int, delta: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET credits = COALESCE(credits, 0) + ? WHERE user_id = ?",
            (delta, user_id),
        )
        await db.commit()


async def apply_referral(inviter_id: int, invitee_id: int) -> bool:
    """
    Возвращает True, если рефка засчиталась впервые и можно начислять бонус.
    False — если уже засчитывали (или это некорректный кейс).
    """
    if inviter_id == invitee_id:
        return False

    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO referrals(inviter_id, invitee_id, created_at) VALUES(?, ?, ?)",
            (inviter_id, invitee_id, now),
        )
        await db.commit()

        # rowcount == 1 -> реально вставили новую запись
        return cur.rowcount == 1

async def touch_user(user_id: int):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_active = ?, last_active_at = ? WHERE user_id = ?",
            (now, now,  user_id)
        )
        await db.commit()

async def set_credits(user_id: int, value: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET credits = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

async def stats_24h() -> dict:
    now = int(time.time())
    since = now - 24 * 60 * 60
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (since,))
        (new_users,) = await cur.fetchone()

        cur = await db.execute("SELECT COUNT(*) FROM users WHERE COALESCE(last_active_at, last_active) >= ?", (since,))
        (active_users,) = await cur.fetchone()

    return {"new_users": int(new_users), "active_users": int(active_users)}

def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


async def get_user_card(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT user_id, username, credits, created_at,
                   COALESCE(last_active_at, last_active) AS last_active_ts
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None

        uid, username, credits, created_at, last_active_ts = row

        cur2 = await db.execute(
            "SELECT COUNT(*) FROM referrals WHERE inviter_id = ?",
            (user_id,)
        )
        (invited_count,) = await cur2.fetchone()

        return {
            "user_id": uid,
            "username": username,
            "credits": int(credits or 0),
            "created_at": _fmt_ts(created_at),
            "last_active": _fmt_ts(last_active_ts),
            "invited_count": int(invited_count or 0),
        }

async def count_referrals(inviter_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM referrals WHERE inviter_id = ?",
            (inviter_id,)
        )
        (n,) = await cur.fetchone()
        return int(n or 0)

async def mark_milestone(inviter_id: int, milestone: int) -> bool:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO ref_milestones(inviter_id, milestone, created_at) VALUES(?, ?, ?)",
            (inviter_id, milestone, now)
        )
        await db.commit()
        return cur.rowcount == 1  # True -> впервые, можно слать сообщение

async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows]

