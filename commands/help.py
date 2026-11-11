from config.prompts import HELP_TEXT

def register_help_handler(bot):
    from main import bot, logger
    @bot.message_handler(commands=['help'])
    async def handle_help_command(message):
        try:
            bot_username = (await bot.get_me()).username
            response = HELP_TEXT
            logger.info(f"Отправка ответа на /help в чате {message.chat.id}")
            await bot.reply_to(message, response, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка в обработчике команды /help: {e}")
            await bot.reply_to(message, "<b>Ошибка!</b> Не удалось показать помощь. Попробуй позже.", parse_mode="HTML")
