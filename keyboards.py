from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Купить VPN")],
            [KeyboardButton(text="📦 Мои подписки"), KeyboardButton(text="🔑 Мой ключ")],
            [KeyboardButton(text="🛟 Поддержка")],
        ],
        resize_keyboard=True
    )


def plans_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="7 дней — тест", callback_data="buy_7")],
            [InlineKeyboardButton(text="30 дней — тест", callback_data="buy_30")],
            [InlineKeyboardButton(text="90 дней — тест", callback_data="buy_90")],
        ]
    )
