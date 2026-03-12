import asyncio
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

from awg import provision_client, revoke_client
from db import (
    create_pool,
    create_vpn_key,
    create_vpn_key_for_user_id,
    extend_key,
    get_active_user_keys,
    get_all_keys,
    get_all_users,
    get_expired_active_keys,
    get_key_by_id,
    get_key_by_id_for_user,
    get_keys_for_tg_user,
    get_user_by_telegram_id,
    get_user_summary_by_tg,
    init_db,
    mark_key_status,
    upsert_user,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@support")
ADMIN_ID = int(os.getenv("ADMIN_ID", "238425"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env")

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def main_menu_keyboard(user_id: int):
    rows = []
    if is_admin(user_id):
        rows.append([KeyboardButton(text="👑 Админка")])

    rows.extend([
        [KeyboardButton(text="💳 Купить ключ")],
        [KeyboardButton(text="🔑 Мои ключи")],
        [KeyboardButton(text="🛟 Поддержка")],
    ])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def buy_plans_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ключ на 7 дней", callback_data="buy_7")],
            [InlineKeyboardButton(text="Ключ на 30 дней", callback_data="buy_30")],
            [InlineKeyboardButton(text="Ключ на 90 дней", callback_data="buy_90")],
        ]
    )


def my_keys_keyboard(keys):
    rows = []
    for key in keys:
        expires = key["expires_at"].strftime("%Y-%m-%d") if key["expires_at"] else "no-date"
        rows.append([
            InlineKeyboardButton(
                text=f"{key['client_name']} | {key['client_ip'] or 'no-ip'} | {expires}",
                callback_data=f"user_key_{key['id']}"
            )
        ])

    rows.append([InlineKeyboardButton(text="➕ Купить ещё ключ", callback_data="user_buy_more")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_key_actions_keyboard(key_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать конфиг", callback_data=f"download_key_{key_id}")],
            [InlineKeyboardButton(text="🔄 Продлить на 7 дней", callback_data=f"extend_key_7_{key_id}")],
            [InlineKeyboardButton(text="🔄 Продлить на 30 дней", callback_data=f"extend_key_30_{key_id}")],
            [InlineKeyboardButton(text="🔄 Продлить на 90 дней", callback_data=f"extend_key_90_{key_id}")],
        ]
    )


def admin_panel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
            [InlineKeyboardButton(text="🔑 Последние ключи", callback_data="admin_keys")],
        ]
    )


def admin_user_actions_keyboard(tg_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выдать ключ на 7 дней", callback_data=f"adm_new_7_{tg_id}")],
            [InlineKeyboardButton(text="➕ Выдать ключ на 30 дней", callback_data=f"adm_new_30_{tg_id}")],
            [InlineKeyboardButton(text="➕ Выдать ключ на 90 дней", callback_data=f"adm_new_90_{tg_id}")],
            [InlineKeyboardButton(text="🔑 Показать ключи пользователя", callback_data=f"adm_showkeys_{tg_id}")],
        ]
    )


def admin_keys_keyboard(keys):
    rows = []
    for key in keys:
        rows.append([
            InlineKeyboardButton(
                text=f"{key['client_name']} | {key['status']}",
                callback_data=f"adm_key_{key['id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_key_actions_keyboard(key_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать конфиг", callback_data=f"adm_download_{key_id}")],
            [InlineKeyboardButton(text="🔄 Продлить на 7 дней", callback_data=f"adm_extend_7_{key_id}")],
            [InlineKeyboardButton(text="🔄 Продлить на 30 дней", callback_data=f"adm_extend_30_{key_id}")],
            [InlineKeyboardButton(text="🔄 Продлить на 90 дней", callback_data=f"adm_extend_90_{key_id}")],
            [InlineKeyboardButton(text="🗑 Отозвать ключ", callback_data=f"adm_revoke_{key_id}")],
        ]
    )


async def ensure_user(pool, tg_user):
    await upsert_user(
        pool=pool,
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )


async def cleanup_expired_keys(pool):
    expired_keys = await get_expired_active_keys(pool)

    for key in expired_keys:
        try:
            if key["wg_client_id"]:
                revoke_client(key["wg_client_id"])
        except Exception:
            logging.exception("Failed to revoke expired key %s", key["id"])

        await mark_key_status(pool, key["id"], "expired")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    pool = dp["db_pool"]
    await ensure_user(pool, message.from_user)
    await cleanup_expired_keys(pool)

    await message.answer(
        "VPN-бот готов.\n\n"
        "1 ключ = 1 устройство.\n"
        "Вы можете покупать несколько ключей и продлевать каждый отдельно.",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@dp.message(F.text == "💳 Купить ключ")
async def buy_key(message: Message):
    pool = dp["db_pool"]
    await ensure_user(pool, message.from_user)
    await cleanup_expired_keys(pool)

    await message.answer("Выберите срок нового ключа:", reply_markup=buy_plans_keyboard())


@dp.callback_query(F.data == "user_buy_more")
async def user_buy_more(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Выберите срок нового ключа:", reply_markup=buy_plans_keyboard())


@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    pool = dp["db_pool"]
    await ensure_user(pool, callback.from_user)
    await cleanup_expired_keys(pool)

    days_map = {"buy_7": 7, "buy_30": 30, "buy_90": 90}
    plan_map = {"buy_7": "7 дней", "buy_30": "30 дней", "buy_90": "90 дней"}

    days = days_map.get(callback.data)
    plan_name = plan_map.get(callback.data)

    if not days:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    await callback.answer("Создаю ключ...")

    try:
        expires_at = datetime.now() + timedelta(days=days)
        client_name = f"tg_{callback.from_user.id}_{int(datetime.now().timestamp())}"
        result = provision_client(client_name)

        key_row = await create_vpn_key(
            pool=pool,
            telegram_id=callback.from_user.id,
            client_name=result["client_name"],
            client_ip=result["client_ip"],
            config_path=result["config_path"],
            wg_client_id=result["client_id"],
            plan_name=plan_name,
            expires_at=expires_at,
        )

        document = FSInputFile(
            result["config_path"],
            filename=f"{result['client_name']}.conf",
        )

        await callback.message.answer(
            f"Ключ создан.\n\n"
            f"ID ключа: {key_row['id']}\n"
            f"Тариф: {plan_name}\n"
            f"IP: {result['client_ip']}\n"
            f"Действует до: {expires_at.strftime('%Y-%m-%d %H:%M')}"
        )
        await callback.message.answer_document(document=document, caption="Ваш новый ключ.")
        await callback.message.answer(
            "Управление этим ключом:",
            reply_markup=user_key_actions_keyboard(key_row["id"]),
        )

    except Exception as e:
        logging.exception("Create key failed")
        await callback.message.answer(f"Не удалось создать ключ: {e}")


@dp.message(F.text == "🔑 Мои ключи")
async def my_keys(message: Message):
    pool = dp["db_pool"]
    await ensure_user(pool, message.from_user)
    await cleanup_expired_keys(pool)

    keys = await get_active_user_keys(pool, message.from_user.id)

    if not keys:
        await message.answer(
            "У вас нет активных ключей.\n\n"
            "Вы можете купить новый ключ:",
            reply_markup=buy_plans_keyboard(),
        )
        return

    await message.answer("Ваши активные ключи:", reply_markup=my_keys_keyboard(keys))


@dp.callback_query(F.data.startswith("user_key_"))
async def open_user_key(callback: CallbackQuery):
    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    key_id = int(callback.data.replace("user_key_", ""))
    row = await get_key_by_id_for_user(pool, key_id, callback.from_user.id)

    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    expires_text = row["expires_at"].strftime("%Y-%m-%d %H:%M") if row["expires_at"] else "не задано"

    await callback.answer()
    await callback.message.answer(
        f"Ключ: {row['client_name']}\n"
        f"IP: {row['client_ip'] or 'unknown'}\n"
        f"Статус: {row['status']}\n"
        f"Тариф: {row['plan_name']}\n"
        f"До: {expires_text}",
        reply_markup=user_key_actions_keyboard(row["id"]),
    )


@dp.callback_query(F.data.startswith("download_key_"))
async def download_user_key(callback: CallbackQuery):
    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    key_id = int(callback.data.replace("download_key_", ""))
    row = await get_key_by_id_for_user(pool, key_id, callback.from_user.id)

    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    if row["status"] != "active":
        await callback.answer("Ключ не активен", show_alert=True)
        return

    if not row["config_path"] or not os.path.exists(row["config_path"]):
        await callback.answer("Файл конфига не найден", show_alert=True)
        return

    document = FSInputFile(row["config_path"], filename=os.path.basename(row["config_path"]))
    await callback.answer()
    await callback.message.answer_document(document=document, caption=f"Ключ {row['client_name']}")


@dp.callback_query(F.data.startswith("extend_key_"))
async def extend_user_key(callback: CallbackQuery):
    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    parts = callback.data.split("_")
    days = int(parts[2])
    key_id = int(parts[3])

    row = await get_key_by_id_for_user(pool, key_id, callback.from_user.id)
    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    await extend_key(pool, key_id, days)
    updated = await get_key_by_id(pool, key_id)

    await callback.answer("Ключ продлён")
    await callback.message.answer(
        f"Ключ {updated['client_name']} продлён на {days} дней.\n"
        f"Новый срок: {updated['expires_at'].strftime('%Y-%m-%d %H:%M')}"
    )


@dp.message(F.text == "🛟 Поддержка")
async def support(message: Message):
    await message.answer(f"Поддержка: {SUPPORT_USERNAME}")


@dp.message(F.text == "👑 Админка")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await message.answer(
        "Админка.\n\n"
        "Открыть пользователя: /admin_user TELEGRAM_ID",
        reply_markup=admin_panel_keyboard(),
    )


@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    users = await get_all_users(pool)
    if not users:
        await callback.message.answer("Пользователей нет.")
        return

    text = "Последние пользователи:\n\n"
    for u in users[:30]:
        text += f"• tg={u['telegram_id']} | {u['first_name'] or '-'} | @{u['username'] or '-'}\n"

    text += "\nОткрыть карточку: /admin_user TELEGRAM_ID"
    await callback.answer()
    await callback.message.answer(text)


@dp.callback_query(F.data == "admin_keys")
async def admin_keys(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    keys = await get_all_keys(pool, limit=50)
    if not keys:
        await callback.message.answer("Ключей нет.")
        return

    await callback.answer()
    await callback.message.answer("Последние ключи:", reply_markup=admin_keys_keyboard(keys))


@dp.message(F.text.startswith("/admin_user "))
async def admin_user_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /admin_user TELEGRAM_ID")
        return

    target_tg = int(parts[1])
    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    user = await get_user_by_telegram_id(pool, target_tg)
    if not user:
        await message.answer("Пользователь не найден.")
        return

    summary = await get_user_summary_by_tg(pool, target_tg)

    await message.answer(
        f"Пользователь:\n"
        f"DB ID: {user['id']}\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"Имя: {user['first_name'] or '-'}\n"
        f"Username: @{user['username'] or '-'}\n"
        f"Всего ключей: {summary['keys_count'] if summary else 0}\n"
        f"Активных ключей: {summary['active_keys_count'] if summary else 0}",
        reply_markup=admin_user_actions_keyboard(target_tg),
    )


@dp.callback_query(F.data.startswith("adm_new_"))
async def admin_new_key(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    parts = callback.data.split("_")
    days = int(parts[2])
    target_tg = int(parts[3])

    user = await get_user_by_telegram_id(pool, target_tg)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await callback.answer("Создаю ключ...")

    try:
        expires_at = datetime.now() + timedelta(days=days)
        client_name = f"tg_{target_tg}_{int(datetime.now().timestamp())}"
        result = provision_client(client_name)

        key_row = await create_vpn_key_for_user_id(
            pool=pool,
            user_id=user["id"],
            client_name=result["client_name"],
            client_ip=result["client_ip"],
            config_path=result["config_path"],
            wg_client_id=result["client_id"],
            plan_name=f"{days} дней",
            expires_at=expires_at,
        )

        document = FSInputFile(
            result["config_path"],
            filename=f"{result['client_name']}.conf",
        )

        await callback.message.answer(
            f"Пользователю tg={target_tg} создан ключ.\n"
            f"ID: {key_row['id']}\n"
            f"IP: {result['client_ip']}\n"
            f"До: {expires_at.strftime('%Y-%m-%d %H:%M')}"
        )
        await callback.message.answer_document(document=document, caption="Новый ключ пользователя.")
    except Exception as e:
        logging.exception("Admin create key failed")
        await callback.message.answer(f"Не удалось создать ключ: {e}")


@dp.callback_query(F.data.startswith("adm_showkeys_"))
async def admin_show_user_keys(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    target_tg = int(callback.data.replace("adm_showkeys_", ""))
    keys = await get_keys_for_tg_user(pool, target_tg)

    if not keys:
        await callback.message.answer("У пользователя нет ключей.")
        return

    await callback.answer()
    await callback.message.answer(
        f"Ключи пользователя tg={target_tg}:",
        reply_markup=admin_keys_keyboard(keys),
    )


@dp.callback_query(F.data.startswith("adm_key_"))
async def admin_open_key(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    await cleanup_expired_keys(pool)

    key_id = int(callback.data.replace("adm_key_", ""))
    row = await get_key_by_id(pool, key_id)

    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    expires_text = row["expires_at"].strftime("%Y-%m-%d %H:%M") if row["expires_at"] else "не задано"

    await callback.answer()
    await callback.message.answer(
        f"Ключ #{row['id']}\n"
        f"Имя: {row['client_name']}\n"
        f"IP: {row['client_ip'] or 'unknown'}\n"
        f"Статус: {row['status']}\n"
        f"Тариф: {row['plan_name']}\n"
        f"До: {expires_text}",
        reply_markup=admin_key_actions_keyboard(row["id"]),
    )


@dp.callback_query(F.data.startswith("adm_download_"))
async def admin_download_key(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    key_id = int(callback.data.replace("adm_download_", ""))
    row = await get_key_by_id(pool, key_id)

    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    if not row["config_path"] or not os.path.exists(row["config_path"]):
        await callback.answer("Файл не найден", show_alert=True)
        return

    document = FSInputFile(row["config_path"], filename=os.path.basename(row["config_path"]))
    await callback.answer()
    await callback.message.answer_document(document=document, caption=f"Ключ #{row['id']}")


@dp.callback_query(F.data.startswith("adm_extend_"))
async def admin_extend_key(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    parts = callback.data.split("_")
    days = int(parts[2])
    key_id = int(parts[3])

    row = await get_key_by_id(pool, key_id)
    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    await extend_key(pool, key_id, days)
    updated = await get_key_by_id(pool, key_id)

    await callback.answer("Ключ продлён")
    await callback.message.answer(
        f"Ключ #{updated['id']} продлён на {days} дней.\n"
        f"Новый срок: {updated['expires_at'].strftime('%Y-%m-%d %H:%M')}"
    )


@dp.callback_query(F.data.startswith("adm_revoke_"))
async def admin_revoke_key(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    pool = dp["db_pool"]
    key_id = int(callback.data.replace("adm_revoke_", ""))
    row = await get_key_by_id(pool, key_id)

    if not row:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    try:
        if row["wg_client_id"] and row["status"] == "active":
            revoke_client(row["wg_client_id"])

        await mark_key_status(pool, key_id, "revoked")

        await callback.answer("Ключ отозван")
        await callback.message.answer(f"Ключ #{key_id} отозван.")
    except Exception as e:
        logging.exception("Admin revoke key failed")
        await callback.message.answer(f"Не удалось отозвать ключ: {e}")


@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Используйте кнопки меню или /start",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp["db_pool"] = await create_pool()
    await init_db(dp["db_pool"])
    await cleanup_expired_keys(dp["db_pool"])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
