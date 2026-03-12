import asyncio
from db import create_pool, init_db, get_expired_active_keys, mark_key_status
from awg import revoke_client

async def main():
    pool = await create_pool()
    await init_db(pool)

    expired_keys = await get_expired_active_keys(pool)

    for key in expired_keys:
        try:
            if key["wg_client_id"]:
                revoke_client(key["wg_client_id"])
        except Exception as e:
            print(f"Failed revoke key {key['id']}: {e}")

        await mark_key_status(pool, key["id"], "expired")
        print(f"Expired key #{key['id']}")

if __name__ == "__main__":
    asyncio.run(main())
