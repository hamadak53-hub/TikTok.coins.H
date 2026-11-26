import aiosqlite
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, username TEXT, tiktok_id TEXT NOT NULL,
            product_code TEXT NOT NULL, coins INTEGER NOT NULL, stars INTEGER NOT NULL,
            telegram_charge_id TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'paid_waiting_supplier',
            supplier_order_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.commit()

async def add_order(user_id, username, tiktok_id, product, charge_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO orders
            (user_id, username, tiktok_id, product_code, coins, stars, telegram_charge_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, tiktok_id, product["code"], product["coins"], product["stars"], charge_id)
        )
        await db.commit()
        return cur.lastrowid

async def latest_orders(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,user_id,tiktok_id,coins,stars,status,created_at FROM orders ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return await cur.fetchall()
