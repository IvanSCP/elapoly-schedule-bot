import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReactionTypeEmoji
from aiogram.enums import ParseMode
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from aiocron import crontab

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'), # Для правильной работы логирования, файл логов указывается в обход конфига
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
with open('config.json', 'r', encoding='utf-8') as config_file:
    config = json.load(config_file)

# Инициализация бота и диспетчера
bot = Bot(token=config['bot_token']) # Замените YOUR_TOKEN_HERE в конфиге на токен вашего бота
dp = Dispatcher()

# Глобальные переменные из конфига
GROUP_ID = config['group_id'] # Укажите в конфиге ID (добавив вначале -100) группы/канала, где бот является администратором
PERMISSIONS_FILE = config['files']['permissions_file']
SCHEDULE_FILE = config['files']['schedule_file']
BLACKLIST_FILE = config['files']['blacklist_file']
ADMINS_FILE = config['files']['admins_file']

# Словарь для хранения состояния ожидания файла
waiting_for_file = {}

# Импорт модулей
from modules.permission_checker import check_user_permission, is_admin, is_banned
from modules.schedule_parser import parse_schedule_for_today, parse_schedule_for_tomorrow, months
from modules.file_handler import download_schedule

# Функция для отправки расписания в группу
async def send_schedule():
    try:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = f"{tomorrow.day} {months[tomorrow.month]}"
        schedule_text = await parse_schedule_for_tomorrow(SCHEDULE_FILE, config)

        if schedule_text:
            await bot.send_message(
                GROUP_ID,
                f"{config['messages']['good_evening']}\n<b>{config['messages']['schedule_for_tomorrow'].format(tomorrow_str=tomorrow_str)}</b>\n\n{schedule_text}",
                parse_mode=ParseMode.HTML
            )
            logger.info(config['logger_messages']['group_sended'])
        else:
            await bot.send_message(GROUP_ID, config["messages"]["schedule_not_found"])
            logger.warning(config['logger_messages']['group_no_schedule'])
    except Exception as e:
        logger.error(config['logger_messages']['send_error'].format(e=e))

# Настройка планировщика задач
if config['scheduler']['is_activated'] == True: # Если в конфиге False, то планировщик не будет работать
    @crontab(config['scheduler']['settings'])  # 00 22 * * 0,1,2,3,4,6 = 22:00 по понедельникам-пятницам и воскресеньям
    async def scheduled_task():
        await send_schedule()
    logger.info(config['logger_messages']['scheduler_started'])

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['start_received'].format(username=username, user_id=user_id))

    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [types.KeyboardButton(text=config['buttons_text']['today']),
            types.KeyboardButton(text=config['buttons_text']['tomorrow'])]
        ]
    )

    await message.answer(config["messages"]["start_message"], reply_markup=keyboard)

# Обработчик команды /fc (для админов)
@dp.message(Command("fc"))
async def handle_file_change_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_try_fc'].format(username=username, user_id=user_id))

    has_permission = await is_admin(ADMINS_FILE, user_id, config)
    if has_permission:
        waiting_for_file[user_id] = True
        await message.answer(config["messages"]["send_file_prompt"])
    else:
        await message.answer(config["messages"]["no_access"])

# Обработчик команды /up (для админов)
@dp.message(Command("up"))
async def handle_update_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_try_up'].format(username=username, user_id=user_id))

    has_permission = await is_admin(ADMINS_FILE, user_id, config)
    if has_permission:
        try:
            await message.answer(config['messages']['url_parse_started'])

            result = await download_schedule(SCHEDULE_FILE, config)

            if result:
                await message.answer(config['messages']['url_parsed'])
                logger.info(config['logger_messages']['up_successful'].format(username=username, user_id=user_id))
            else:
                await message.answer(config['messages']['url_unparsed'])
                logger.error(config['logger_messages']["up_unsuccessful"].format(username=username, user_id=user_id))

        except Exception as e:
            logger.error(config['logger_messages']["up_error"].format(e=e))
            await message.answer(config['messages']['url_parse_error'])
    else:
        await message.answer(config["messages"]["no_access"])

# Обработчик документов
@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"

    if waiting_for_file.get(user_id, False):
        if message.document:
            # Сохранение файла
            file = await bot.get_file(message.document.file_id)
            file_path = Path(SCHEDULE_FILE)
            await bot.download_file(file.file_path, file_path)

            await message.answer(config["messages"]["file_received"])
            logger.info(config['logger_messages']["fc_successful"].format(username=username, user_id=user_id))
            waiting_for_file[user_id] = False
        else:
            await message.answer(config["messages"]["send_file_prompt"])
            logger.warning(config['logger_messages']["fc_send_not_file"].format(username=username, user_id=user_id))
    else:
        await message.answer(config["messages"]["send_file_first"])
        logger.info(config['logger_messages']["user_send_file_only"].format(username=username, user_id=user_id))

# Обработчик команды /getfile
@dp.message(Command("getfile"))
async def get_file(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_try_getfile'].format(username=username, user_id=user_id))

    try:
        file = FSInputFile(SCHEDULE_FILE)
        await message.answer_document(file, caption=config["messages"]["file_description"])
        logger.info(config['logger_messages']['getfile_sended'].format(username=username, user_id=user_id))
    except FileNotFoundError:
        await message.answer(config['messages']['file_not_found'])
        logger.error(config['logger_messages']['getfile_not_found'])

# Обработчик команды /today
@dp.message(Command("today"))
async def today_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_try_today'].format(username=username, user_id=user_id))

    today = datetime.now()
    today_str = f"{today.day} {months[today.month]}"

    has_permission = await check_user_permission(bot, GROUP_ID, PERMISSIONS_FILE, BLACKLIST_FILE, user_id, config)
    if has_permission == "Banned":
        await message.react([ReactionTypeEmoji(emoji=config['reactions']['banned'])])
    else:
        if has_permission:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['parsing'])])
            schedule_text = await parse_schedule_for_today(SCHEDULE_FILE, config)
            if schedule_text:
                await message.answer(f"<b>{config['messages']['schedule_for_today'].format(today_str=today_str)}</b>\n\n{schedule_text}", parse_mode=ParseMode.HTML)
                logger.info(config['logger_messages']['today_sended'].format(today_str=today_str))
            else:
                await message.answer(config["messages"]["schedule_not_found"])
                logger.warning(config['logger_messages']['today_not_found'].format(today_str=today_str))
        else:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['no_permission'])])
            await message.answer(config["messages"]["no_permission"])

# Обработчик команды /tomorrow
@dp.message(Command("tomorrow"))
async def tomorrow_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_try_tomorrow'].format(username=username, user_id=user_id))

    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_str = f"{tomorrow.day} {months[tomorrow.month]}"

    has_permission = await check_user_permission(bot, GROUP_ID, PERMISSIONS_FILE, BLACKLIST_FILE,  user_id, config)
    if has_permission == "Banned":
        await message.react([ReactionTypeEmoji(emoji=config['reactions']['banned'])])
    else:
        if has_permission:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['parsing'])])
            schedule_text = await parse_schedule_for_tomorrow(SCHEDULE_FILE, config)
            if schedule_text:
                await message.answer(f"<b>{config['messages']['schedule_for_tomorrow'].format(tomorrow_str=tomorrow_str)}</b>\n\n{schedule_text}", parse_mode=ParseMode.HTML)
                logger.info(config['logger_messages']['tomorrow_sended'].format(tomorrow_str=tomorrow_str))
            else:
                await message.answer(config["messages"]["schedule_not_found"])
                logger.warning(config['logger_messages']['tomorrow_not_found'].format(tomorrow_str=tomorrow_str))
        else:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['no_permission'])])
            await message.answer(config["messages"]["no_permission"])

# Обработчик команды /ping
@dp.message(Command("ping"))
async def week_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_ping'].format(username=username, user_id=user_id))
    
    await message.react([ReactionTypeEmoji(emoji=config['reactions']['ping'])])
    await message.answer(config["messages"]["ping_success"])

# Обработчик текстовых сообщений
@dp.message(F.text)
async def handle_message(message: types.Message):
    if message.text == config['buttons_text']['today']:
        await today_command(message)
    elif message.text == config['buttons_text']['tomorrow']:
        await tomorrow_command(message)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
