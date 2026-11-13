import os
import asyncio
import logging
import sys
import time
import sqlite3
import requests
import random
import re
from contextlib import asynccontextmanager
from telebot.async_telebot import AsyncTeleBot
from g4f.client import Client
import aiohttp
from ddgs import DDGS

from bs4 import BeautifulSoup
import base64
import json

from commands.help import register_help_handler
from commands.start import register_start_handler
from config.links import get_linked_group
from commands.link_handlers import register_link_handlers
from commands.ball import register_ball_handler
from config.prompts import *
from config.settings import *
from commands.model import register_model_handlers, get_model

MODELS_API_URL = MODELS_API_URL
MODELS_MODEL = MODELS_MODEL

# распознавания изображений
VISION_MODEL = VISION_MODEL

context_dan = CONTEXT_DAN
base_context = BASE_CONTEXT

# promts
image_context = IMAGE_CONTEXT
image_response_prompt = IMAGE_RESPONSE_PROMPT

bot = AsyncTeleBot(BOT_TOKEN)
register_model_handlers(bot)

# names
NAME_PHRASES = NAME_PHRASES

os.makedirs("bobrik/DataBases", exist_ok=True)
os.makedirs("user_data", exist_ok=True)

# Список разрешенных пользователей (для ссылок и т.д)
ADMIN_IDS = ADMIN_IDS

VOICE_DIR = "bobrik/voice_responses"
os.makedirs(VOICE_DIR, exist_ok=True)

TTS_MODE = TTS_MODE
TTS_API_URL = TTS_API_URL
TTS_MODEL = TTS_MODEL

# logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bobrik.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

sys.stdout.reconfigure(encoding='utf-8')

def init_db(chat_id):
    try:
        db_path = f'bobrik/DataBases/chat_{chat_id}.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS users 
                         (user_id INTEGER PRIMARY KEY, 
                          username TEXT, 
                          first_name TEXT, 
                          last_name TEXT, 
                          custom_name TEXT,
                          last_seen TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS messages 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          chat_id INTEGER, 
                          user_id INTEGER, 
                          message_text TEXT, 
                          bot_response TEXT, 
                          timestamp TEXT)''')

        conn.commit()
        conn.close()
        # logger.info(f"База данных для чата {chat_id} успешно инициализирована: {db_path}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных для чата {chat_id}: {e}")


def update_user_info(chat_id, user, custom_name=None):
    try:
        db_path = f'bobrik/DataBases/chat_{chat_id}.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        if custom_name:
            c.execute('''INSERT OR REPLACE INTO users 
                             (user_id, username, first_name, last_name, custom_name, last_seen) 
                             VALUES (?, ?, ?, ?, ?, ?)''',
                      (user.id, user.username, user.first_name, user.last_name, custom_name, timestamp))
        else:
            c.execute('''INSERT OR REPLACE INTO users 
                             (user_id, username, first_name, last_name, custom_name, last_seen) 
                             VALUES (?, ?, ?, ?, 
                             COALESCE((SELECT custom_name FROM users WHERE user_id = ?), ?), ?)''',
                      (user.id, user.username, user.first_name, user.last_name, user.id, None, timestamp))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка при обновлении информации о пользователе в чате {chat_id}: {e}")


def get_user_info(chat_id, user_id):
    try:
        db_path = f'bobrik/DataBases/chat_{chat_id}.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''SELECT username, first_name, last_name, custom_name 
                         FROM users WHERE user_id = ?''', (user_id,))
        result = c.fetchone()
        conn.close()

        if result:
            return {
                "username": result[0],
                "first_name": result[1],
                "last_name": result[2],
                "custom_name": result[3]
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе в чате {chat_id}: {e}")
        return None


def get_user_display_name(chat_id, user_id):
    user_info = get_user_info(chat_id, user_id)
    if not user_info:
        return None

    if user_info["custom_name"]:
        return user_info["custom_name"]
    elif user_info["first_name"]:
        return user_info["first_name"]
    elif user_info["last_name"]:
        return user_info["last_name"]
    elif user_info["username"]:
        return f"@{user_info['username']}"
    return None


def extract_name_from_message(text):
    text = text.lower().strip()
    for pattern in NAME_PHRASES:
        match = re.search(pattern, text)
        if match:
            return match.group(1).capitalize()
    return None

def save_message(chat_id, user_id, message_text, bot_response):
    try:
        db_path = f'bobrik/DataBases/chat_{chat_id}.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        c.execute('''INSERT INTO messages 
                     (chat_id, user_id, message_text, bot_response, timestamp) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (chat_id, user_id, message_text, bot_response, timestamp))

        c.execute('''
            DELETE FROM messages 
            WHERE id NOT IN (
                SELECT id FROM messages 
                WHERE chat_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 500
            )
        ''', (chat_id,))

        conn.commit()
        conn.close()
        # logger.info(f"Сообщение сохранено в чате {chat_id} для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении сообщения в чате {chat_id}: {e}")

def get_chat_history(chat_id, limit=15):
    try:
        db_path = f'bobrik/DataBases/chat_{chat_id}.db'

        if not os.path.exists(db_path):
            logger.info(f"База данных для чата {chat_id} не найдена")
            return []

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute('''SELECT 
                        u.user_id, 
                        u.custom_name, 
                        u.first_name, 
                        u.username, 
                        m.message_text, 
                        m.bot_response,
                        m.timestamp
                    FROM messages m
                    JOIN users u ON m.user_id = u.user_id
                    WHERE m.chat_id = ?
                    ORDER BY m.timestamp DESC
                    LIMIT ?''', (chat_id, limit))

        history = c.fetchall()
        conn.close()

        # logger.info(f"Получена история чата {chat_id} с лимитом {limit}, найдено {len(history)} записей")
        return history

    except Exception as e:
        logger.error(f"Ошибка при получении истории чата {chat_id}: {e}")
        return []


def format_history(history, context_name="текущего чата"):
    if not history:
        return f"Нет истории {context_name}"

    formatted = []
    formatted.append(f"📋 **История {context_name}:**")

    for msg in reversed(history):
        if len(msg) >= 6:
            user_id, custom_name, first_name, username, user_msg, bot_msg, timestamp = msg
        else:
            user_id, custom_name, first_name, username, user_msg, bot_msg = msg

        display_name = (custom_name or first_name or (f"@{username}" if username else f"user_{user_id}"))

        time_str = f" [{timestamp.split()[1]}]" if len(msg) >= 7 and timestamp else ""

        formatted.append(f"{display_name}{time_str}: {user_msg}")
        if bot_msg and bot_msg.strip():
            formatted.append(f"Бобрик{time_str}: {bot_msg}")

    return "\n".join(formatted)

async def text_to_speech(text, filename="response"):
    try:
        headers = {
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json"
        }
        data = {
            "model": TTS_MODEL,
            "input": text,
            "response_format": "wav"
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(TTS_API_URL, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ошибка TTS API: {response.status} {error_text}")
                    return None
                audio_bytes = await response.read()

        voice_path = os.path.join(VOICE_DIR, f"{filename}.wav")
        with open(voice_path, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"Голосовой файл создан: {voice_path}")
        return voice_path
    except Exception as e:
        logger.error(f"Ошибка синтеза речи: {e}")
        return None


async def generate_image_response(prompt):
    max_retries = 3
    retries = 0
    max_empty_retries = 3
    empty_retries = 0

    while retries < max_retries and empty_retries < max_empty_retries:
        try:
            start_time = time.time()
            headers = {
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type": "application/json"
            }
            data = {
                "model": get_model(),
                "messages": [
                    {"role": "system", "content": image_context},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(MODELS_API_URL, headers=headers, json=data, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'choices' in data and len(data['choices']) > 0:
                            response_text = data['choices'][0]['message']['content'].strip()

                            if not response_text:
                                empty_retries += 1
                                logger.warning(
                                    f"Пустой промпт для изображения (попытка {empty_retries}/{max_empty_retries})")
                                await asyncio.sleep(1)
                                continue

                            empty_retries = 0

                            response_time = time.time() - start_time
                            logger.info(f"Время обработки промпта для /image: {response_time:.2f} сек")
                            return response_text
                    else:
                        logger.error(f"Ошибка API для /image: {response.status} - {await response.text()}")
        except Exception as e:
            logger.error(f"Ошибка при запросе к API для /image (попытка {retries + 1}): {e}")
        retries += 1
        await asyncio.sleep(1)

    if empty_retries >= max_empty_retries:
        logger.warning(f"Не удалось получить непустой промпт для изображения после {max_empty_retries} попыток")
        return prompt
    else:
        logger.warning(f"Не удалось обработать промпт для /image после {max_retries} попыток")
        return prompt


async def generate_image(prompt):
    try:
        refined_prompt = await generate_image_response(prompt)
        logger.info(f"Оригинальный промпт: {prompt}, Уточненный промпт: {refined_prompt}")

        client = Client()
        response = await client.images.async_generate(
            model="flux",
            prompt=refined_prompt,
            response_format="url"
        )

        if response.data and response.data[0].url:
            async with aiohttp.ClientSession() as session:
                async with session.get(response.data[0].url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        logger.info("Изображение успешно загружено")
                        return image_data
        logger.warning("Не удалось получить URL изображения")
        return None
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        return None


def fetch_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        time_elements = soup.find_all(['div', 'span', 'p', 'h1', 'h2'],
                                      class_=['current-time', 'time', 'clock', 'date'])
        for elem in time_elements:
            text = elem.get_text().strip()
            if 'Moscow' in text or 'MSK' in text or '2026' in text:
                return text

        paragraphs = soup.find_all(['p', 'div', 'span'])
        for p in paragraphs:
            text = p.get_text().strip()
            if '2025' in text or 'current year' in text.lower() or 'сегодня' in text.lower():
                return text[:500]

        return soup.get_text()[:2000]
    except Exception as e:
        logger.error(f"Ошибка парсинга {url}: {e}")
        return ""


def search_web(query):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
        context = ""
        sources = []
        for i, result in enumerate(results):
            title = result.get("title", "")
            link = result.get("href", "")
            content = fetch_page_content(link)
            context += f"Источник {i + 1}: {title}\n{content}\n"
            sources.append(link)
        return context, sources
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return "", []


@bot.message_handler(commands=['search'])
async def handle_search_command(message):
    try:
        query = message.text.replace('/search', '').strip()
        if not query:
            await bot.reply_to(message, "Укажи запрос после /search")
            return

        init_db(message.chat.id)
        update_user_info(message.chat.id, message.from_user)

        searching_msg = await bot.reply_to(message, "<b>🔍 Ищу информацию...</b>", parse_mode="HTML")

        response, response_time = await generate_response(
            f"Найди информацию в интернете: {query}",
            message.chat.id,
            message.from_user.id,
            is_search=True
        )

        save_message(message.chat.id, message.from_user.id, query, response)
        await bot.reply_to(message, response, parse_mode="Markdown")
        await bot.delete_message(message.chat.id, searching_msg.message_id)

    except Exception as e:
        logger.error(f"Ошибка /search: {e}")
        await bot.reply_to(message, "<b>Ошибка!</b> Не удалось выполнить поиск.")

# register_start_handler(bot)
# register_help_handler(bot)
register_link_handlers(bot)

@bot.message_handler(commands=['help'])
async def handle_help_command(message):
        bot_username = (await bot.get_me()).username
        response = HELP_TEXT
        logger.info(f"Отправка ответа на /help в чате {message.chat.id}")
        await bot.reply_to(message, response, parse_mode="HTML")

@bot.message_handler(commands=['start'])
async def handle_start_command(message):
    try:
        logger.info(f"Отправка ответа на /start в чате {message.chat.id}")
        await bot.reply_to(message, START_TEXT, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в обработчике команды /start: {e}")

@bot.message_handler(commands=['image'])
async def handle_image_command(message):
    try:
        prompt = message.text.replace('/image', '').strip()
        if not prompt:
            logger.info(f"Пустой промпт для /image в чате {message.chat.id}")
            await bot.reply_to(message,"<b>Ошибка!</b> Укажи промпт для генерации изображения после команды <code>/image</code>",parse_mode="HTML")
            return

        generating_msg = await bot.reply_to(message, "<b>🖌️ Генерирую изображение...</b>", parse_mode="HTML")
        image_data = await generate_image(prompt)

        if image_data:
            logger.info(f"Изображение успешно сгенерировано для чата {message.chat.id}")
            await bot.send_photo(message.chat.id, image_data, caption=f"<b>Изображение сгенерировано</b>",parse_mode="HTML")
            await bot.delete_message(message.chat.id, generating_msg.message_id)
        else:
            logger.warning(f"Не удалось сгенерировать изображение для чата {message.chat.id}")
            await bot.reply_to(message, "<b>Ошибка!</b> Не удалось сгенерировать изображение.",parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в обработчике команды /image: {e}")
        await bot.reply_to(message, "<b>Ошибка!</b> Произошла ошибка при генерации изображения. Попробуй позже.",parse_mode="HTML")

register_ball_handler(bot)


async def direct_image_recognition(image_data, prompt):
    try:
        base64_image = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:image/jpeg;base64,{base64_image}"

        headers = {
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        }

        data = json.dumps({
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
        })

        async with aiohttp.ClientSession() as session:
            async with session.post(MODELS_API_URL, headers=headers, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]
                    logger.info("Прямое распознавание изображения выполнено успешно")
                    return content
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка прямого распознавания изображения: {response.status} {error_text}")
                    return "Не удалось обработать изображение с помощью нейросети."

    except Exception as e:
        logger.error(f"Ошибка при прямом распознавании изображения: {e}")
        return "Ошибка при обработке изображения."


async def recognize_image(image_data, prompt=None):
    try:
        base64_image = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:image/jpeg;base64,{base64_image}"

        headers = {
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        }
        data = json.dumps({
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt or image_response_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
        })

        async with aiohttp.ClientSession() as session:
            async with session.post(MODELS_API_URL, headers=headers, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]
                    logger.info("Изображение успешно распознано")
                    return content
                else:
                    logger.error(f"Ошибка распознавания изображения: {response.status} {await response.text()}")
                    return "Не удалось распознать изображение."
    except Exception as e:
        logger.error(f"Ошибка при распознавании изображения: {e}")
        return "Ошибка при обработке изображения."


@bot.message_handler(content_types=['photo'])
async def handle_photo(message):
    try:
        chat_id = message.chat.id
        caption = (message.caption or "").strip()

        if message.chat.type != 'private':
            bot_username = (await bot.get_me()).username.lower()
            replied = (
                message.reply_to_message is not None
                and message.reply_to_message.from_user is not None
                and (message.reply_to_message.from_user.username or "").lower() == bot_username
            )
            if not (f"@{bot_username}" in caption.lower() or caption.startswith('>') or replied):
                return
            caption = caption.lstrip('>').replace(f"@{bot_username}", "", 1).strip()

        init_db(chat_id)
        update_user_info(chat_id, message.from_user)

        file_info = await bot.get_file(message.photo[-1].file_id)
        downloaded_file = await bot.download_file(file_info.file_path)

        async with typing_action(chat_id):
            if caption.lower().startswith('/photo'):
                prompt = caption[len('/photo'):].strip()
                if not prompt:
                    await bot.reply_to(message, "<b>Ошибка!</b> Укажи промпт после /photo в подписи фото.", parse_mode="HTML")
                    return
                response = await direct_image_recognition(downloaded_file, prompt)
                save_message(chat_id, message.from_user.id, f"[пользователь скинул фото] {prompt}", response)
                await bot.reply_to(message, response, parse_mode="Markdown")
                return

            description = await recognize_image(downloaded_file, PHOTO_DESCRIBE_PROMPT)
            description = description.strip()[:700]

            user_input = f"[пользователь скинул фото, его описание: {description}]"
            if caption:
                user_input += f"\nПодпись к фото: {caption}"

        response, response_time = await generate_response(
            user_input,
            chat_id,
            message.from_user.id
        )
        save_message(chat_id, message.from_user.id, user_input, response)
        await bot.reply_to(message, response, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в обработчике фото: {e}")
        await bot.reply_to(message, "<b>Ошибка!</b> Не удалось обработать фото.", parse_mode="HTML")

@asynccontextmanager
async def typing_action(chat_id):
    async def loop():
        while True:
            try:
                await bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            await asyncio.sleep(4)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()


async def generate_response(user_input, chat_id, user_id, is_search=False, image_data=None):
    async with typing_action(chat_id):
        return await _generate_response(user_input, chat_id, user_id, is_search, image_data)


async def _generate_response(user_input, chat_id, user_id, is_search=False, image_data=None):
    max_retries = 5
    retries = 0
    empty_retries = 0
    max_empty_retries = 3

    if user_input is None or not user_input.strip():
        user_input = "Привет, расскажи что-нибудь интересное!"

    logger.info(f"Генерация ответа для чата {chat_id}, пользователя {user_id}, текст: {user_input}, поиск: {is_search}")

    user_info = get_user_info(chat_id, user_id)
    display_name = get_user_display_name(chat_id, user_id)

    history = get_chat_history(chat_id, limit=10)
    history_context = format_history(history) if history else "Нет истории сообщений"

    full_context = history_context

    if chat_id > 0:
        linked = get_linked_group(user_id)
        if linked:
            group_id, group_name = linked
            group_history = get_chat_history(group_id, limit=10)
            if group_history:
                group_context = f"\n\n📌 **История из группы {group_name}:**\n"
                group_context += format_history(group_history)
                full_context += group_context

    if user_info:
        profile_info = f"Информация о пользователе из профиля:"
        profile_info += f"\n- ID: {user_id}"
        profile_info += f"\n- Имя в чате: {display_name or 'не указано'}"
        profile_info += f"\n- Username: @{user_info.get('username', 'не указан')}"
        profile_info += f"\n- Telegram имя: {user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
        if user_info.get('custom_name'):
            profile_info += f"\n- Попросил называть его: {user_info['custom_name']}"
    else:
        profile_info = f"Информация о пользователе: {display_name or 'пользователь'}"

    if is_search:
        search_query_prompt = (
            f"{context_dan}\n{base_context}\n\n"
            f"Пользователь хочет найти информацию: {user_input}\n\n"
            f"Сформулируй КОРОТКИЙ и ТОЧНЫЙ поисковый запрос (3-7 слов) для поисковой системы, "
            f"чтобы найти самую актуальную информацию по этому вопросу.\n"
            f"Учти:\n"
            f"- Если спрашивают время/дату - добавь 'сейчас' или 'текущее'\n"
            f"- Если спрашивают погоду - добавь 'сегодня'\n"
            f"- Если спрашивают новости - добавь 'последние'\n"
            f"Ответь ТОЛЬКО поисковым запросом, без объяснений, без кавычек, без лишних слов."
        )

        search_query = None
        try:
            headers = {
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type": "application/json"
            }
            data = {
                "model": get_model(),
                "messages": [{"role": "user", "content": search_query_prompt}],
                "max_tokens": 50
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(MODELS_API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'choices' in data and len(data['choices']) > 0:
                            search_query = data['choices'][0]['message']['content'].strip()
                            search_query = re.sub(r'["\'\[\]\(\)]', '', search_query)
        except Exception as e:
            logger.error(f"Ошибка при получении поискового запроса: {e}")

        if not search_query:
            search_query = user_input
            logger.info(f"Использую оригинальный запрос: {search_query}")
        else:
            logger.info(f"ИИ сформулировал поисковый запрос: {search_query}")

        search_results = []
        sources = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(search_query, max_results=5):
                    result = {
                        'title': r.get('title', 'Без заголовка'),
                        'body': r.get('body', ''),
                        'href': r.get('href', '')
                    }
                    search_results.append(result)
                    if result['href']:
                        sources.append(result['href'])
        except Exception as e:
            logger.error(f"Ошибка поиска через DDGS: {e}")

        if search_results:
            results_text = "\n\n".join([
                f"=== РЕЗУЛЬТАТ {i + 1} ===\n"
                f"Заголовок: {r['title']}\n"
                f"Содержание: {r['body']}\n"
                f"Ссылка: {r['href']}"
                for i, r in enumerate(search_results)
            ])

            prompt = (
                f"{context_dan}\n{base_context}\n\n"
                f"Текущая беседа:\n{full_context}\n\n"
                f"{profile_info}\n\n"
                f"Оригинальный вопрос пользователя: {user_input}\n"
                f"Поисковый запрос (сформулированный ИИ): {search_query}\n\n"
                f"Вот результаты поиска:\n{results_text}\n\n"
                f"ИНСТРУКЦИИ:\n"
                f"1. Проанализируй результаты поиска и дай ТОЧНЫЙ ответ на вопрос пользователя\n"
                f"2. Если в результатах есть противоречия - укажи это и объясни\n"
                f"3. Если результаты устаревшие или нерелевантные - скажи об этом\n"
                f"4. В конце ответа перечисли использованные источники в формате:\n"
                f"📚 Источники:\n"
                f"1. [Заголовок](ссылка)\n"
                f"2. [Заголовок](ссылка)\n"
                f"5. Для кода используй Markdown-блоки с тройными кавычками ```"
            )
        else:
            prompt = (
                f"{context_dan}\n{base_context}\n\n"
                f"Текущая беседа:\n{full_context}\n\n"
                f"{profile_info}\n\n"
                f"Вопрос пользователя: {user_input}\n\n"
                f"Поиск не дал результатов. Ответь, основываясь на своих знаниях. "
                f"Если не знаешь точного ответа - так и скажи."
            )

    else:
        prompt = (
            f"{context_dan}\n{base_context}\n\n"
            f"Текущая беседа:\n{full_context}\n\n"
            f"{profile_info}\n\n"
            f"Новое сообщение от {display_name or 'пользователя'}: {user_input}\n\n"
            f"ИНСТРУКЦИИ:\n"
            f"1. Ответь естественно и кратко, как человек в чате\n"
            f"2. Для кода используй Markdown-блоки с тройными кавычками ```\n"
            f"3. Не используй Markdown для обычного текста, только для кода\n"
            f"4. Если пользователь указал как к нему обращаться - используй это имя\n"
            f"5. Поддерживай живой диалог, задавай уточняющие вопросы если нужно"
        )
        if "[пользователь скинул фото" in user_input:
            prompt += "\n\n" + PHOTO_RULES

    while retries < max_retries and empty_retries < max_empty_retries:
        try:
            start_time = time.time()
            headers = {
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type": "application/json"
            }
            data = {
                "model": get_model(),
                "messages": [
                    {"role": "system", "content": f"{context_dan}\n{base_context}"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000
            }

            logger.debug(f"Отправка запроса (попытка {retries + 1})")

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(MODELS_API_URL, headers=headers, json=data) as response:
                    logger.debug(f"Получен ответ от API: status={response.status}")

                    if response.status == 200:
                        data = await response.json()

                        if 'choices' in data and len(data['choices']) > 0:
                            response_text = data['choices'][0]['message']['content']
                            response_text = re.sub(r'$$\s*🔓JAILBREAK\s*$$|$$\s*🔒CLASSIC\s*$$', '',response_text).strip()

                            response_text = re.sub(
                                r'```(\w+)?\n(.*?)\n```',
                                lambda m: f"```{m.group(1) or ''}\n{m.group(2)}\n```",
                                response_text,
                                flags=re.DOTALL
                            )

                            if not response_text:
                                empty_retries += 1
                                logger.warning(f"Получен пустой ответ (попытка {empty_retries}/{max_empty_retries})")
                                await asyncio.sleep(1)
                                continue

                            empty_retries = 0

                            if len(response_text) > 4000:
                                response_text = response_text[:4000] + "\n\n[...сообщение сокращено...]"

                            response_time = time.time() - start_time
                            logger.info(f"Ответ получен за {response_time:.2f} сек, длина: {len(response_text)} символов")

                            return response_text, response_time

                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка API: status={response.status}, текст={error_text}")

        except asyncio.TimeoutError:
            logger.error(f"Таймаут при запросе к API (попытка {retries + 1})")
        except Exception as e:
            logger.error(f"Ошибка при запросе к API (попытка {retries + 1}): {str(e)}")

        retries += 1
        await asyncio.sleep(1)

    if empty_retries >= max_empty_retries:
        logger.error(f"Превышено количество пустых ответов ({max_empty_retries})")
        fallback = f"{display_name or ''}, извини, я не смог придумать ответ. Попробуй задать вопрос по-другому.".strip()
    else:
        logger.error(f"Не удалось получить ответ после {max_retries} попыток")
        fallback = f"{display_name or ''}, ошибка соединения с API. Попробуй позже.".strip()

    return fallback, 0

async def handle_text_message(message):
    try:
        logger.info(f"Оброботка текстового сообщения в чате {message.chat.id}: {message.text}")
        init_db(message.chat.id)
        # logger.info(f"База данных инициализирована для чата {message.chat.id}")

        user_input = message.text.strip()
        user = message.from_user
        chat_id = message.chat.id
        user_id = user.id

        custom_name = extract_name_from_message(user_input)
        if custom_name:
            logger.info(f"Имя: {custom_name}")
            update_user_info(chat_id, user, custom_name)
            await bot.reply_to(message, f"<b>Отлично, {custom_name}.</b> Буду знать.", parse_mode="HTML")
            return

        update_user_info(chat_id, user)

        response, response_time = await generate_response(user_input, chat_id, user_id)

        try:
            conn = sqlite3.connect(f'bobrik/DataBases/chat_{chat_id}.db')
            c = conn.cursor()
            c.execute('''UPDATE messages 
                         SET bot_response = ? 
                         WHERE id = (
                             SELECT id FROM messages 
                             WHERE chat_id = ? AND user_id = ? AND message_text = ? 
                             ORDER BY timestamp DESC LIMIT 1
                         )''',
                      (response, chat_id, user_id, user_input))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка при обновлении ответа в БД для лички: {e}")

        logger.info(f"Получен ответ за {response_time:.2f} сек: {response[:50]}...")

        if not response.strip():response = "<b>Эй!</b> Кажется, я задумался. Напиши ещё что-нибудь!"

        save_message(chat_id, user_id, user_input, response)
        # logger.info(f"Сообщение сохранено в базе данных")

        logger.info(f"Отправка ответа в чат {chat_id}")
        await bot.reply_to(message, response, parse_mode="Markdown")
        logger.info(f"Ответ успешно отправлен в чат {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка в handle_text_message для чата {chat_id}: {e}")
        await bot.reply_to(message, "<b>Ошибка!</b> Не удалось обработать сообщение.", parse_mode="HTML")


def clear_chat_history(chat_id):
    try:
        db_path = f'bobrik/DataBases/chat_{chat_id}.db'
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.execute('DELETE FROM messages WHERE chat_id = ?', (chat_id,))
            conn.commit()
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при очистке истории чата {chat_id}: {e}")
        return False


@bot.message_handler(commands=['tokens'])
async def handle_tokens_command(message):
    if message.from_user.id != OWNER_ID:
        await bot.reply_to(message, "Эту команду может использовать только владелец.")
        return
    try:
        headers = {"Authorization": f"Bearer {get_api_key()}"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(f"{API_BASE_URL}/balance", headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    await bot.reply_to(message, f"Ошибка {resp.status}: {text[:500]}")
                    return
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except ValueError:
            pass
        await bot.reply_to(message, text)
    except Exception as e:
        logger.error(f"Ошибка в /tokens: {e}")
        await bot.reply_to(message, "<b>Ошибка!</b> Не удалось получить баланс.", parse_mode="HTML")

@bot.message_handler(commands=['reset'])
async def handle_reset_command(message):
    try:
        chat_id = message.chat.id
        if message.chat.type != 'private' and message.from_user.id != OWNER_ID:
            member = await bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ('creator', 'administrator'):
                await bot.reply_to(message, "<b>Ошибка!</b> Очищать историю могут только администраторы чата.", parse_mode="HTML")
                return
        if clear_chat_history(chat_id):
            await bot.reply_to(message, "История чата очищена.", parse_mode="HTML")
        else:
            await bot.reply_to(message, "<b>Ошибка!</b> Не удалось очистить историю.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в /reset для чата {message.chat.id}: {e}")
        await bot.reply_to(message, "<b>Ошибка!</b> Не удалось выполнить команду.", parse_mode="HTML")


@bot.message_handler(func=lambda message: True)
async def main_handler(message):
    try:
        bot_username = (await bot.get_me()).username

        if message.text and message.text.startswith('/'):
            if message.text.startswith('/start'):
                await handle_start_command(message)
            elif message.text.startswith('/help'):
                await handle_help_command(message)
            elif message.text.startswith('/image'):
                await handle_image_command(message)
            elif message.text.startswith('/search'):
                await handle_search_command(message)
            return

        if message.chat.type == 'private':
            init_db(message.chat.id)
            update_user_info(message.chat.id, message.from_user)

            if message.content_type == 'text':
                await handle_text_message(message)

        elif message.chat.type in ['group', 'supergroup']:
            init_db(message.chat.id)
            update_user_info(message.chat.id, message.from_user)

            if message.content_type == 'text':
                save_message(message.chat.id, message.from_user.id, message.text, "")
                text_lower = message.text.lower().strip()

                if (f"@{bot_username.lower()}" in text_lower or text_lower.startswith('>')):
                    response, response_time = await generate_response(
                        message.text,
                        message.chat.id,
                        message.from_user.id
                    )

                    try:
                        update_conn = sqlite3.connect(f'bobrik/DataBases/chat_{message.chat.id}.db')
                        update_c = update_conn.cursor()
                        update_c.execute('''SELECT id FROM messages 
                                         WHERE chat_id = ? AND user_id = ? AND message_text = ? 
                                         ORDER BY timestamp DESC LIMIT 1''',
                                         (message.chat.id, message.from_user.id, message.text))
                        result = update_c.fetchone()

                        if result:
                            msg_id = result[0]
                            update_c.execute('UPDATE messages SET bot_response = ? WHERE id = ?',
                                           (response, msg_id))
                            update_conn.commit()
                        update_conn.close()
                    except Exception:
                        pass

                    await bot.reply_to(message, response, parse_mode="Markdown")

    except Exception as e:
        await bot.reply_to(message, "<b>Ошибка!</b> Что-то пошло не так.", parse_mode="HTML")

async def run_bot():
    logger.info("Бобрик запущен.")
    while True:
        try:
            bot_info = await bot.get_me()
            logger.info(f"Бот запущен, юз: @{bot_info.username}")
            await bot.polling(non_stop=True)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_bot())
