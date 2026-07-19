import aiosqlite
import logging

DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                balance REAL DEFAULT 0.0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                os_server_id TEXT UNIQUE,
                name TEXT,
                hourly_cost REAL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                pg_operator_id TEXT,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS pending_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                file_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        ''')

        await db.commit()
    logging.info("Database initialized.")

async def get_user(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def create_user(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (telegram_id) VALUES (?)", (telegram_id,))
        await db.commit()

async def update_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
        await db.commit()

async def add_server(user_id, os_server_id, name, hourly_cost):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO servers (user_id, os_server_id, name, hourly_cost) VALUES (?, ?, ?, ?)",
            (user_id, os_server_id, name, hourly_cost)
        )
        await db.commit()

async def get_servers(user_id=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            async with db.execute("SELECT * FROM servers WHERE user_id = ? AND status = 'active'", (user_id,)) as cursor:
                return await cursor.fetchall()
        else:
            async with db.execute("SELECT * FROM servers WHERE status = 'active'") as cursor:
                return await cursor.fetchall()

async def update_server_status(os_server_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE servers SET status = ? WHERE os_server_id = ?", (status, os_server_id))
        await db.commit()

async def add_transaction(user_id, amount, t_type, description):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
            (user_id, amount, t_type, description)
        )
        await db.commit()

async def add_pending_receipt(user_id, amount, file_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO pending_receipts (user_id, amount, file_id) VALUES (?, ?, ?)",
            (user_id, amount, file_id)
        )
        await db.commit()
        return cursor.lastrowid

async def get_pending_receipt(receipt_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pending_receipts WHERE id = ?", (receipt_id,)) as cursor:
            return await cursor.fetchone()

async def update_receipt_status(receipt_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE pending_receipts SET status = ? WHERE id = ?", (status, receipt_id))
        await db.commit()
