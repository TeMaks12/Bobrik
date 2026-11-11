from config.prompts import START_TEXT

def register_start_handler(bot):
    from main import bot, logger
    @bot.message_handler(commands=['start'])
    async def handle_start_command(message):
        try:
            logger.info(f"Отправка ответа на /start в чате {message.chat.id}")
            await bot.reply_to(message, START_TEXT)
        except Exception as e:
            logger.error(f"Ошибка в обработчике команды /start: {e}")