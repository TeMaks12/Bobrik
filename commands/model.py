import json

from telebot import types

from config.settings import OWNER_ID, DENIED_TEXT, MODELS_LIST, MODEL_FILE, MODELS_MODEL


def get_model():
    try:
        with open(MODEL_FILE, encoding="utf-8") as f:
            model = json.load(f).get("model")
        if model in MODELS_LIST:
            return model
    except (OSError, ValueError):
        pass
    return MODELS_MODEL


def set_model(model):
    with open(MODEL_FILE, "w", encoding="utf-8") as f:
        json.dump({"model": model}, f)


def build_markup():
    current = get_model()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for model in MODELS_LIST:
        title = f"✅ {model}" if model == current else model
        markup.add(types.InlineKeyboardButton(title, callback_data=f"model:{model}"))
    return markup


def register_model_handlers(bot):
    @bot.message_handler(commands=["model"])
    async def model_command(message):
        if message.from_user.id != OWNER_ID:
            await bot.reply_to(message, DENIED_TEXT)
            return
        await bot.reply_to(
            message,
            f"Текущая модель: <b>{get_model()}</b>",
            reply_markup=build_markup(),
            parse_mode="HTML"
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("model:"))
    async def model_callback(call):
        if call.from_user.id != OWNER_ID:
            await bot.answer_callback_query(call.id, DENIED_TEXT, show_alert=True)
            return
        model = call.data.split(":", 1)[1]
        if model not in MODELS_LIST or model == get_model():
            await bot.answer_callback_query(call.id)
            return
        set_model(model)
        await bot.edit_message_text(
            f"Текущая модель: <b>{model}</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_markup(),
            parse_mode="HTML"
        )
        await bot.answer_callback_query(call.id, f"Выбрано: {model}")
