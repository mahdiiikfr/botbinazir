import os
import aiosqlite
import logging

DB_FILE = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # Create users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                wallet_balance INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Create vps_servers table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vps_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                openstack_server_id TEXT,
                server_name TEXT,
                flavor_id TEXT,
                image_id TEXT,
                network_id TEXT,
                hourly_cost_toman REAL,
                status TEXT DEFAULT 'ACTIVE',
                ip_address TEXT,
                root_password TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)

        # Create transactions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                payment_method TEXT,
                status TEXT DEFAULT 'PENDING',
                receipt_photo_id TEXT,
                ref_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)

        # Create resellers table (PasarGuard Operator Reseller panel)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS resellers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                operator_username TEXT,
                operator_password TEXT,
                limits INTEGER DEFAULT 50,
                price INTEGER DEFAULT 800000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)

        # Create outbounds table (PasarGuard Outbound Subscriptions)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS outbounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subscription_url TEXT,
                data_limit_gb INTEGER DEFAULT 1000,
                price INTEGER DEFAULT 800000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)

        # Insert default settings if not exists
        default_settings = {
            "card_number": "5022-2910-1234-5678",
            "card_owner": "مدیریت ربات",
            "dollar_rate_manual": "70000",
            "dollar_rate_auto": "1",  # 1 means True, 0 means False
            "profit_margin": "50",     # 50% profit margin
            "zarinpal_merchant": "7b134bb0-802c-473d-9be2-441d8e1faef0",
            "pasarguard_base_url": "https://demo.pasarguard.org", # Default / placeholder
            "pasarguard_username": "admin",
            "pasarguard_password": "admin_password",
            "reseller_limit": "50",
            "reseller_price": "800000", # 800k Tomans
            "outbound_limit_gb": "1000", # 1TB
            "outbound_price": "800000", # 800k Tomans
        }

        for k, v in default_settings.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        await db.commit()
    logging.info("Database initialized.")

# --- Users functions ---
async def get_or_create_user(telegram_id: int, username: str = None) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                if username and row["username"] != username:
                    await db.execute("UPDATE users SET username = ? WHERE telegram_id = ?", (username, telegram_id))
                    await db.commit()
                    # Fetch again
                    async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur2:
                        return dict(await cur2.fetchone())
                return dict(row)

            # Create new user (First registered user is admin)
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                count = (await c.fetchone())[0]
            is_admin = 1 if count == 0 else 0

            try:
                await db.execute("INSERT INTO users (telegram_id, username, is_admin) VALUES (?, ?, ?)", (telegram_id, username, is_admin))
                await db.commit()
            except aiosqlite.sqlite3.IntegrityError:
                pass

            async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor_new:
                row_new = await cursor_new.fetchone()
                return dict(row_new) if row_new else {}

async def get_user(telegram_id: int) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_user_balance(telegram_id: int, amount: int) -> bool:
    """Add or subtract amount from user wallet balance"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE telegram_id = ?", (amount, telegram_id))
        await db.commit()
        return True

async def set_user_admin(telegram_id: int, is_admin: int) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET is_admin = ? WHERE telegram_id = ?", (is_admin, telegram_id))
        await db.commit()
        return True

async def get_all_users() -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_all_admins() -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE is_admin = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

# --- Settings functions ---
async def get_setting(key: str, default=None) -> str:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

# --- VPS servers functions ---
async def add_vps_server(user_id: int, openstack_server_id: str, server_name: str, flavor_id: str, image_id: str, network_id: str, hourly_cost_toman: float, root_password: str, ip_address: str = None) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO vps_servers (user_id, openstack_server_id, server_name, flavor_id, image_id, network_id, hourly_cost_toman, root_password, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, openstack_server_id, server_name, flavor_id, image_id, network_id, hourly_cost_toman, root_password, ip_address))
        await db.commit()
        return cursor.lastrowid

async def get_user_vps_servers(user_id: int) -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM vps_servers WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_vps_server(server_id: int) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM vps_servers WHERE id = ?", (server_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_vps_by_openstack_id(openstack_server_id: str) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM vps_servers WHERE openstack_server_id = ?", (openstack_server_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def delete_vps_server(server_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM vps_servers WHERE id = ?", (server_id,))
        await db.commit()

async def get_all_vps_servers() -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM vps_servers") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def update_vps_ip_and_status(openstack_server_id: str, ip_address: str, status: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE vps_servers SET ip_address = ?, status = ? WHERE openstack_server_id = ?", (ip_address, status, openstack_server_id))
        await db.commit()

async def update_vps_password(openstack_server_id: str, new_password: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE vps_servers SET root_password = ? WHERE openstack_server_id = ?", (new_password, openstack_server_id))
        await db.commit()

# --- Transactions functions ---
async def create_transaction(user_id: int, amount: int, type_: str, payment_method: str, status: str = 'PENDING', receipt_photo_id: str = None, ref_id: str = None) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO transactions (user_id, amount, type, payment_method, status, receipt_photo_id, ref_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, amount, type_, payment_method, status, receipt_photo_id, ref_id))
        await db.commit()
        return cursor.lastrowid

async def get_transaction(tx_id: int) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_transaction_status(tx_id: int, status: str, ref_id: str = None):
    async with aiosqlite.connect(DB_FILE) as db:
        if ref_id:
            await db.execute("UPDATE transactions SET status = ?, ref_id = ? WHERE id = ?", (status, ref_id, tx_id))
        else:
            await db.execute("UPDATE transactions SET status = ? WHERE id = ?", (status, tx_id))
        await db.commit()

async def get_pending_card_payments() -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transactions WHERE payment_method = 'CARD_TO_CARD' AND status = 'PENDING'") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

# --- Resellers & Outbounds functions ---
async def add_reseller(user_id: int, operator_username: str, operator_password: str, limits: int, price: int) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO resellers (user_id, operator_username, operator_password, limits, price)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, operator_username, operator_password, limits, price))
        await db.commit()
        return cursor.lastrowid

async def get_user_resellers(user_id: int) -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM resellers WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def add_outbound(user_id: int, subscription_url: str, data_limit_gb: int, price: int) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            INSERT INTO outbounds (user_id, subscription_url, data_limit_gb, price)
            VALUES (?, ?, ?, ?)
        """, (user_id, subscription_url, data_limit_gb, price))
        await db.commit()
        return cursor.lastrowid

async def get_user_outbounds(user_id: int) -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM outbounds WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
