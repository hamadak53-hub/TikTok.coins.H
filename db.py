import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                tiktok_id TEXT NOT NULL,
                product_code TEXT NOT NULL,
                coins INTEGER NOT NULL,
                stars INTEGER NOT NULL DEFAULT 0,
                telegram_charge_id TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending_payment_review',
                supplier_order_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur = await db.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in await cur.fetchall()]

        migrations = {
            "price": "INTEGER NOT NULL DEFAULT 0",
            "payment_method": "TEXT",
            "receipt_file_id": "TEXT",
            "payment_status": "TEXT DEFAULT 'pending'",
        }

        for column, definition in migrations.items():
            if column not in columns:
                await db.execute(
                    f"ALTER TABLE orders ADD COLUMN {column} {definition}"
                )

        await db.commit()


async def add_order(
    user_id,
    username,
    tiktok_id,
    product,
    payment_method,
    receipt_file_id=None
):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO orders (
                user_id,
                username,
                tiktok_id,
                product_code,
                coins,
                stars,
                price,
                payment_method,
                receipt_file_id,
                payment_status,
                status
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'pending', 'pending_payment_review')
            """,
            (
                user_id,
                username,
                tiktok_id,
                product["code"],
                product["coins"],
                product["price"],
                payment_method,
                receipt_file_id
            )
        )

        await db.commit()
        return cur.lastrowid


async def update_receipt(order_id, receipt_file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE orders
            SET receipt_file_id = ?
            WHERE id = ?
            """,
            (receipt_file_id, order_id)
        )
        await db.commit()


async def confirm_payment(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE orders
            SET payment_status = 'confirmed',
                status = 'paid_waiting_supplier'
            WHERE id = ?
            """,
            (order_id,)
        )
        await db.commit()


async def reject_payment(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE orders
            SET payment_status = 'rejected',
                status = 'payment_rejected'
            WHERE id = ?
            """,
            (order_id,)
        )
        await db.commit()


async def latest_orders(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id,
                user_id,
                tiktok_id,
                coins,
                price,
                status,
                created_at
            FROM orders
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )
        return await cur.fetchall()
        
