from telebot import types

from config.access import add_user, allowed_ids, get_key_index, remove_user, set_key_index
from config.settings import API_KEYS, DENIED_TEXT, OWNER_ID


def key_text():
    return f"Текущий ключ: {get_key_index() + 1} из {len(API_KEYS)}"


def key_markup():
    markup = types.InlineKeyboardMarkup(row_width=5)
    markup.add(*[
        types.InlineKeyboardButton(
            ("✅ " if i == get_key_index() else "") + str(i + 1),
            callback_data=f"key:{i}",
        )
        for i in range(len(API_KEYS))
    ])
    return markup


def parse_id(message):
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return None


def register_access_handlers(bot):
    def owner_only(message):
        return message.from_user is not None and message.from_user.id == OWNER_ID

    @bot.message_handler(commands=["key"], func=owner_only)
    async def key_menu(message):
        await bot.reply_to(message, key_text(), reply_markup=key_markup())

    @bot.callback_query_handler(func=lambda c: (c.data or "").startswith("key:"))
    async def key_select(call):
        if call.from_user.id != OWNER_ID:
            await bot.answer_callback_query(call.id, DENIED_TEXT, show_alert=True)
            return
        index = int(call.data.split(":")[1])
        if index >= len(API_KEYS):
            await bot.answer_callback_query(call.id, "Нет такого ключа")
            return
        set_key_index(index)
        try:
            await bot.edit_message_text(
                key_text(),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=key_markup(),
            )
        except Exception:
            pass
        await bot.answer_callback_query(call.id, f"Ключ {index + 1}")

    @bot.message_handler(commands=["adduser"], func=owner_only)
    async def adduser(message):
        user_id = parse_id(message)
        if user_id is None:
            await bot.reply_to(message, "/adduser <id>")
            return
        add_user(user_id)
        await bot.reply_to(message, f"добавлен: {user_id}")

    @bot.message_handler(commands=["deluser"], func=owner_only)
    async def deluser(message):
        user_id = parse_id(message)
        if user_id is None:
            await bot.reply_to(message, "/deluser <id>")
            return
        remove_user(user_id)
        await bot.reply_to(message, f"удалён: {user_id}")

    @bot.message_handler(commands=["users"], func=owner_only)
    async def users(message):
        lines = [f"{OWNER_ID} (owner)"] + [str(i) for i in sorted(allowed_ids)]
        await bot.reply_to(message, "\n".join(lines))
