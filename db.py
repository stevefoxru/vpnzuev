import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "vpnbot")
DB_USER = os.getenv("DB_USER", "vpnbot_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


async def create_pool():
    return await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=1,
        max_size=5,
    )


async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vpn_keys (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                client_name TEXT NOT NULL,
                client_ip TEXT,
                config_path TEXT,
                wg_client_id TEXT,
                plan_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                expires_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vpn_keys_user_id ON vpn_keys(user_id);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vpn_keys_status ON vpn_keys(status);
        """)


async def upsert_user(pool, telegram_id: int, username: str | None, first_name: str | None):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name;
        """, telegram_id, username, first_name)


async def get_user_by_telegram_id(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT *
            FROM users
            WHERE telegram_id = $1
        """, telegram_id)


async def create_vpn_key(
    pool,
    telegram_id: int,
    client_name: str,
    client_ip: str | None,
    config_path: str,
    wg_client_id: str | None,
    plan_name: str,
    expires_at,
):
    async with pool.acquire() as conn:
        user = await conn.fetchrow("""
            SELECT id
            FROM users
            WHERE telegram_id = $1
        """, telegram_id)

        if not user:
            raise ValueError("User not found")

        return await conn.fetchrow("""
            INSERT INTO vpn_keys (
                user_id,
                client_name,
                client_ip,
                config_path,
                wg_client_id,
                plan_name,
                status,
                expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
            RETURNING *
        """,
        user["id"], client_name, client_ip, config_path, wg_client_id, plan_name, expires_at)


async def create_vpn_key_for_user_id(
    pool,
    user_id: int,
    client_name: str,
    client_ip: str | None,
    config_path: str,
    wg_client_id: str | None,
    plan_name: str,
    expires_at,
):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            INSERT INTO vpn_keys (
                user_id,
                client_name,
                client_ip,
                config_path,
                wg_client_id,
                plan_name,
                status,
                expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
            RETURNING *
        """,
        user_id, client_name, client_ip, config_path, wg_client_id, plan_name, expires_at)


async def get_user_keys(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT
                k.*,
                u.telegram_id
            FROM vpn_keys k
            JOIN users u ON u.id = k.user_id
            WHERE u.telegram_id = $1
            ORDER BY k.created_at DESC
        """, telegram_id)


async def get_active_user_keys(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT
                k.*,
                u.telegram_id
            FROM vpn_keys k
            JOIN users u ON u.id = k.user_id
            WHERE u.telegram_id = $1
              AND k.status = 'active'
            ORDER BY k.created_at DESC
        """, telegram_id)


async def get_key_by_id(pool, key_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT *
            FROM vpn_keys
            WHERE id = $1
        """, key_id)


async def get_key_by_id_for_user(pool, key_id: int, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT k.*
            FROM vpn_keys k
            JOIN users u ON u.id = k.user_id
            WHERE k.id = $1
              AND u.telegram_id = $2
        """, key_id, telegram_id)


async def extend_key(pool, key_id: int, days: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE vpn_keys
            SET expires_at = CASE
                WHEN expires_at IS NULL OR expires_at < NOW()
                    THEN NOW() + ($1 || ' days')::interval
                ELSE expires_at + ($1 || ' days')::interval
            END
            WHERE id = $2
        """, days, key_id)


async def mark_key_status(pool, key_id: int, status: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE vpn_keys
            SET status = $1
            WHERE id = $2
        """, status, key_id)


async def get_expired_active_keys(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT *
            FROM vpn_keys
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at < NOW()
        """)


async def get_all_users(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT
                id,
                telegram_id,
                username,
                first_name,
                created_at
            FROM users
            ORDER BY created_at DESC
        """)


async def get_user_summary_by_tg(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT
                u.id,
                u.telegram_id,
                u.username,
                u.first_name,
                (
                    SELECT COUNT(*)
                    FROM vpn_keys k
                    WHERE k.user_id = u.id
                ) AS keys_count,
                (
                    SELECT COUNT(*)
                    FROM vpn_keys k
                    WHERE k.user_id = u.id
                      AND k.status = 'active'
                ) AS active_keys_count
            FROM users u
            WHERE u.telegram_id = $1
        """, telegram_id)


async def get_all_keys(pool, limit: int = 100):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT
                k.*,
                u.telegram_id,
                u.username,
                u.first_name
            FROM vpn_keys k
            JOIN users u ON u.id = k.user_id
            ORDER BY k.created_at DESC
            LIMIT $1
        """, limit)


async def get_keys_for_tg_user(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT
                k.*,
                u.telegram_id
            FROM vpn_keys k
            JOIN users u ON u.id = k.user_id
            WHERE u.telegram_id = $1
            ORDER BY k.created_at DESC
        """, telegram_id)
