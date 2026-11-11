import logging
from telebot.async_telebot import AsyncTeleBot
from config.links import link_group, unlink_group, get_linked_group

logger = logging.getLogger(__name__)


def register_link_handlers(bot: AsyncTeleBot):
    @bot.message_handler(commands=['link'])
    async def handle_link(message):
        try:
            if message.chat.type != 'private':
                await bot.reply_to(message, "❌ Эта команда работает только в личных сообщениях!")
                return

            args = message.text.split()
            if len(args) < 2:
                await bot.reply_to(message,
                                   "❌ Укажи ID группы!\n\n"
                                   "1. Добавь бота в группу\n"
                                   "2. Напиши в группе /id\n"
                                   "3. Используй: /link <ID>")
                return

            try:
                group_id = int(args[1])
            except ValueError:
                await bot.reply_to(message, "❌ ID должен быть числом!")
                return

            existing = get_linked_group(message.from_user.id)
            if existing:
                await bot.reply_to(message,f"❌ У тебя уже привязана группа (ID: {existing[0]})\n"f"Сначала отвяжи её командой /unlink")
                return

            try:
                chat = await bot.get_chat(group_id)
                if chat.type not in ['group', 'supergroup']:
                    await bot.reply_to(message, "❌ Это не группа!")
                    return

                bot_member = await bot.get_chat_member(group_id, (await bot.get_me()).id)
                if bot_member.status not in ['administrator', 'member']:
                    await bot.reply_to(message, "❌ Бот не в этой группе!")
                    return

            except Exception:
                await bot.reply_to(message,"❌ Не удалось найти группу.\n""Убедись, что бот добавлен в группу и ID правильный")
                return

            if link_group(message.from_user.id, group_id, chat.title):
                await bot.reply_to(message,
                                   f"✅ Группа **{chat.title}** привязана!\n"
                                   f"Теперь я учитываю её историю.",
                                   parse_mode="Markdown")
            else:
                await bot.reply_to(message, "❌ Ошибка при привязке")

        except Exception as e:
            logger.error(f"Ошибка в /link: {e}")
            await bot.reply_to(message, "❌ Произошла ошибка")

    @bot.message_handler(commands=['unlink'])
    async def handle_unlink(message):
        try:
            if message.chat.type != 'private':
                await bot.reply_to(message, "❌ Эта команда только в личке!")
                return

            existing = get_linked_group(message.from_user.id)
            if not existing:
                await bot.reply_to(message, "❌ У тебя нет привязанных групп!")
                return

            if unlink_group(message.from_user.id):
                await bot.reply_to(message, "✅ Группа отвязана!")
            else:
                await bot.reply_to(message, "❌ Ошибка при отвязке")

        except Exception as e:
            logger.error(f"Ошибка в /unlink: {e}")
            await bot.reply_to(message, "❌ Ошибка")

    @bot.message_handler(commands=['linkinfo'])
    async def handle_linkinfo(message):
        try:
            if message.chat.type != 'private':
                await bot.reply_to(message, "❌ Эта команда только в личке!")
                return

            existing = get_linked_group(message.from_user.id)
            if not existing:
                await bot.reply_to(message,"📭 Нет привязанных групп\n""Используй /link <ID> чтобы привязать")
                return

            group_id, group_name = existing
            await bot.reply_to(message,
                               f"📊 **Привязанная группа:**\n\n"
                               f"• Название: **{group_name}**\n"
                               f"• ID: `{group_id}`\n"
                               f"• Статус: ✅ Активна",
                               parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Ошибка в /linkinfo: {e}")
            await bot.reply_to(message, "❌ Ошибка")

    @bot.message_handler(commands=['id'])
    async def handle_id(message):
        try:
            chat_id = message.chat.id
            chat_type = message.chat.type

            response = f"🆔 **ID:** `{chat_id}`\n"
            response += f"📋 **Тип:** {chat_type}\n"

            if chat_type in ['group', 'supergroup']:
                response += f"\n💡 Для привязки в личке:\n`/link {chat_id}`"

            await bot.reply_to(message, response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Ошибка в /id: {e}")
            await bot.reply_to(message, "❌ Ошибка")