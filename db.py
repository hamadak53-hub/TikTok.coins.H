import aiosqlite
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            tiktok_id TEXT NOT NULL,
            product_code TEXT NOT NULL,
            coins INTEGER NOT NULL,
            price INTEGER NOT NULL,
            payment_method TEXT NOT NULL,
            receipt_file_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            photo_file_id TEXT,
            status TEXT NOT NULL DEFAULT 'available',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS account_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            admin_id INTEGER,
            message TEXT NOT NULL,
            direction TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.commit()

async def register_customer(user_id, username):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO customers(user_id, username) VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username
        """, (user_id, username))
        await db.commit()

async def add_order(user_id, username, tiktok_id, product, payment_method, receipt_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        INSERT INTO orders(user_id, username, tiktok_id, product_code, coins,
        price, payment_method, receipt_file_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, tiktok_id, product["code"], product["coins"],
              product["price"], payment_method, receipt_id))
        await db.commit()
        return cur.lastrowid

async def get_order(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        return await cur.fetchone()

async def set_order_status(order_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        await db.commit()

async def get_orders(limit=50, status=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if status:
            cur = await db.execute(
                "SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit))
        else:
            cur = await db.execute(
                "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        return await cur.fetchall()

async def latest_orders(limit=10):
    return await get_orders(limit)

async def confirm_payment(order_id):
    await set_order_status(order_id, "paid")

async def reject_payment(order_id):
    await set_order_status(order_id, "rejected")

async def get_customers(limit=5000):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, username FROM customers ORDER BY created_at DESC LIMIT ?",
            (limit,))
        return await cur.fetchall()

async def get_dashboard_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {}
        for key, query in {
            "orders": "SELECT COUNT(*) FROM orders",
            "pending": "SELECT COUNT(*) FROM orders WHERE status='pending'",
            "paid": "SELECT COUNT(*) FROM orders WHERE status='paid'",
            "customers": "SELECT COUNT(*) FROM customers",
            "accounts": "SELECT COUNT(*) FROM accounts",
        }.items():
            cur = await db.execute(query)
            stats[key] = (await cur.fetchone())[0]
        return stats

async def add_account(category, title, description, price, photo_file_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        INSERT INTO accounts(category,title,description,price,photo_file_id)
        VALUES(?,?,?,?,?)
        """, (category, title, description, price, photo_file_id))
        await db.commit()
        return cur.lastrowid

async def get_accounts(category=None, available_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        sql = "SELECT * FROM accounts"
        args = []
        clauses = []
        if category:
            clauses.append("category=?")
            args.append(category)
        if available_only:
            clauses.append("status='available'")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC"
        cur = await db.execute(sql, args)
        return await cur.fetchall()

async def get_account(account_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM accounts WHERE id=?", (account_id,))
        return await cur.fetchone()

async def set_account_status(account_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET status=? WHERE id=?", (status, account_id))
        await db.commit()

async def request_account(account_id, user_id, username):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT status FROM accounts WHERE id=?", (account_id,))
        row = await cur.fetchone()
        if not row or row[0] != "available":
            return None
        cur = await db.execute("""
        INSERT INTO account_requests(account_id,user_id,username)
        VALUES(?,?,?)
        """, (account_id, user_id, username))
        await db.commit()
        return cur.lastrowid

async def get_account_requests(limit=30):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        SELECT r.id, r.account_id, r.user_id, r.username, r.status,
               r.created_at, a.category, a.title, a.price
        FROM account_requests r JOIN accounts a ON a.id=r.account_id
        ORDER BY r.id DESC LIMIT ?
        """, (limit,))
        return await cur.fetchall()

async def save_support_message(user_id, message, direction, admin_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO support_messages(user_id,admin_id,message,direction)
        VALUES(?,?,?,?)
        """, (user_id, admin_id, message, direction))
        await db.commit()
