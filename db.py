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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            INSERT OR IGNORE INTO customers (user_id, username)
            SELECT user_id, username FROM orders
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS account_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                photo_file_id TEXT,
                status TEXT NOT NULL DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS account_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (listing_id)
                    REFERENCES account_listings(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                sender TEXT NOT NULL,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()


async def register_customer(user_id, username=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO customers (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET username = excluded.username
        """, (user_id, username))
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
        await db.execute("""
            INSERT INTO customers (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET username = excluded.username
        """, (user_id, username))

        cur = await db.execute("""
            INSERT INTO orders (
                user_id, username, tiktok_id, product_code,
                coins, stars, price, payment_method,
                receipt_file_id, payment_status, status
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'pending',
                    'pending_payment_review')
        """, (
            user_id,
            username,
            tiktok_id,
            product["code"],
            product["coins"],
            product["price"],
            payment_method,
            receipt_file_id
        ))

        await db.commit()
        return cur.lastrowid


async def update_receipt(order_id, receipt_file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE orders SET receipt_file_id = ?
            WHERE id = ?
        """, (receipt_file_id, order_id))
        await db.commit()


async def confirm_payment(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE orders
            SET payment_status = 'confirmed',
                status = 'paid_waiting_supplier'
            WHERE id = ?
        """, (order_id,))
        await db.commit()


async def reject_payment(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE orders
            SET payment_status = 'rejected',
                status = 'payment_rejected'
            WHERE id = ?
        """, (order_id,))
        await db.commit()


async def update_order_status(order_id, status):
    allowed = {
        "pending_payment_review",
        "paid_waiting_supplier",
        "processing",
        "completed",
        "payment_rejected",
        "cancelled",
    }

    if status not in allowed:
        raise ValueError("Invalid order status")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )
        await db.commit()


async def get_dashboard_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(
                    CASE WHEN payment_status = 'confirmed'
                    THEN price ELSE 0 END
                ), 0),
                COALESCE(SUM(
                    CASE WHEN payment_status = 'pending'
                    THEN 1 ELSE 0 END
                ), 0),
                COALESCE(SUM(
                    CASE WHEN payment_status = 'confirmed'
                    THEN 1 ELSE 0 END
                ), 0),
                COALESCE(SUM(
                    CASE WHEN payment_status = 'rejected'
                    THEN 1 ELSE 0 END
                ), 0),
                COALESCE(SUM(
                    CASE WHEN status = 'completed'
                    THEN 1 ELSE 0 END
                ), 0)
            FROM orders
        """)

        orders = await cur.fetchone()

        cur = await db.execute("SELECT COUNT(*) FROM customers")
        customers = (await cur.fetchone())[0]

        cur = await db.execute("SELECT COUNT(*) FROM account_listings")
        accounts = (await cur.fetchone())[0]

        return {
            "orders": orders[0] or 0,
            "revenue": orders[1] or 0,
            "pending": orders[2] or 0,
            "paid": orders[3] or 0,
            "rejected": orders[4] or 0,
            "completed": orders[5] or 0,
            "customers": customers or 0,
            "accounts": accounts or 0,
        }


async def get_orders(limit=20, status=None):
    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT id, user_id, username, tiktok_id,
                   coins, price, payment_method,
                   payment_status, status, created_at
            FROM orders
        """
        params = []

        if status:
            query += " WHERE payment_status = ?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cur = await db.execute(query, params)
        return await cur.fetchall()


async def get_order(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, user_id, username, tiktok_id,
                   product_code, coins, price,
                   payment_method, receipt_file_id,
                   payment_status, status, created_at
            FROM orders
            WHERE id = ?
        """, (order_id,))

        return await cur.fetchone()


async def get_customers(limit=30):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT c.user_id, c.username, COUNT(o.id),
                COALESCE(SUM(
                    CASE WHEN o.payment_status = 'confirmed'
                    THEN o.price ELSE 0 END
                ), 0)
            FROM customers c
            LEFT JOIN orders o ON c.user_id = o.user_id
            GROUP BY c.user_id
            ORDER BY c.created_at DESC
            LIMIT ?
        """, (limit,))

        return await cur.fetchall()


async def get_customer_orders(user_id, limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, coins, price, status, created_at
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))

        return await cur.fetchall()


async def get_customer_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM customers")
        return [row[0] for row in await cur.fetchall()]


async def latest_orders(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, user_id, tiktok_id, coins,
                   price, status, created_at
            FROM orders
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        return await cur.fetchall()


# =========================
# إدارة الحسابات المعروضة
# =========================

async def add_account(
    category,
    title,
    description,
    price,
    photo_file_id=None
):
    if category not in ("pubg", "tiktok"):
        raise ValueError("Invalid account category")

    if int(price) <= 0:
        raise ValueError("Price must be positive")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO account_listings (
                category, title, description, price, photo_file_id
            )
            VALUES (?, ?, ?, ?, ?)
        """, (category, title, description, int(price), photo_file_id))

        await db.commit()
        return cur.lastrowid


async def get_accounts(category=None, available_only=True, limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT id, category, title, description,
                   price, photo_file_id, status, created_at
            FROM account_listings
            WHERE 1=1
        """
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if available_only:
            query += " AND status = 'available'"

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cur = await db.execute(query, params)
        return await cur.fetchall()


async def get_account(account_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, category, title, description,
                   price, photo_file_id, status, created_at
            FROM account_listings
            WHERE id = ?
        """, (account_id,))

        return await cur.fetchone()


async def update_account(
    account_id,
    title=None,
    description=None,
    price=None,
    photo_file_id=None
):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT title, description, price, photo_file_id
            FROM account_listings
            WHERE id = ?
        """, (account_id,))
        old = await cur.fetchone()

        if not old:
            return False

        if price is not None and int(price) <= 0:
            raise ValueError("Price must be positive")

        await db.execute("""
            UPDATE account_listings
            SET title = ?, description = ?, price = ?, photo_file_id = ?
            WHERE id = ?
        """, (
            title if title is not None else old[0],
            description if description is not None else old[1],
            int(price) if price is not None else old[2],
            photo_file_id if photo_file_id is not None else old[3],
            account_id
        ))

        await db.commit()
        return True


async def set_account_status(account_id, status):
    if status not in ("available", "sold", "hidden"):
        raise ValueError("Invalid account status")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE account_listings
            SET status = ?
            WHERE id = ?
        """, (status, account_id))
        await db.commit()


async def delete_account(account_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM account_listings WHERE id = ?",
            (account_id,)
        )
        await db.commit()


# =========================
# طلبات شراء الحسابات
# =========================

async def request_account(listing_id, user_id, username=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT status
            FROM account_listings
            WHERE id = ?
        """, (listing_id,))
        listing = await cur.fetchone()

        if not listing or listing[0] != "available":
            return None

        await db.execute("""
            INSERT INTO customers (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET username = excluded.username
        """, (user_id, username))

        cur = await db.execute("""
            INSERT INTO account_requests (listing_id, user_id, username)
            VALUES (?, ?, ?)
        """, (listing_id, user_id, username))

        await db.commit()
        return cur.lastrowid


async def get_account_requests(limit=30, status=None):
    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT r.id, r.listing_id, r.user_id, r.username,
                   r.status, r.created_at,
                   a.category, a.title, a.price
            FROM account_requests r
            JOIN account_listings a ON a.id = r.listing_id
        """
        params = []

        if status:
            query += " WHERE r.status = ?"
            params.append(status)

        query += " ORDER BY r.id DESC LIMIT ?"
        params.append(limit)

        cur = await db.execute(query, params)
        return await cur.fetchall()


async def update_account_request(request_id, status):
    if status not in ("new", "contacted", "completed", "cancelled"):
        raise ValueError("Invalid request status")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE account_requests
            SET status = ?
            WHERE id = ?
        """, (status, request_id))
        await db.commit()


# =========================
# دعم العملاء
# =========================

async def save_support_message(
    user_id,
    message,
    sender,
    admin_id=None
):
    if sender not in ("customer", "admin"):
        raise ValueError("Invalid support message sender")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO support_messages (
                user_id, message, sender, admin_id
            )
            VALUES (?, ?, ?, ?)
        """, (user_id, message, sender, admin_id))
        await db.commit()


async def get_support_messages(user_id, limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT id, user_id, message, sender, admin_id, created_at
            FROM support_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))

        return await cur.fetchall()
        
