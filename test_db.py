import pytest
import aiosqlite
import db
import os

@pytest.mark.asyncio
async def test_db_operations():
    # Setup
    db.DB_NAME = "test_bot.db"
    if os.path.exists(db.DB_NAME):
        os.remove(db.DB_NAME)

    await db.init_db()

    # Test user creation
    user_id = 12345
    await db.create_user(user_id)
    user = await db.get_user(user_id)
    assert user is not None
    assert user[1] == user_id
    assert user[2] == 0.0 # initial balance

    # Test balance update
    await db.update_balance(user_id, 50000.0)
    user = await db.get_user(user_id)
    assert user[2] == 50000.0

    # Test server creation
    server_id = "server-uuid-1"
    await db.add_server(user_id, server_id, "VPS-Test", 1000.0)
    servers = await db.get_servers(user_id)
    assert len(servers) == 1
    assert servers[0]['os_server_id'] == server_id
    assert servers[0]['hourly_cost'] == 1000.0

    # Test server status update
    await db.update_server_status(server_id, 'deleted')
    servers = await db.get_servers(user_id)
    assert len(servers) == 0 # because get_servers only returns 'active'

    # Cleanup
    if os.path.exists(db.DB_NAME):
        os.remove(db.DB_NAME)
