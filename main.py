import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command # , CommandStart
from aiogram.types import FSInputFile, ReactionTypeEmoji, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from aiocron import crontab
# from typing import Callable, Dict, Any, Awaitable

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
PERMISSIONS_FILE = str(Path(__file__).parent / config['files']['permissions_file'])
ADMINS_FILE = str(Path(__file__).parent / config['files']['admins_file'])
BLACKLIST_FILE = str(Path(__file__).parent / config['files']['blacklist_file'])
SCHEDULE_FILE = str(Path(__file__).parent / config['files']['schedule_file'])

# Словарь для хранения состояния ожидания файла и прочих состояний
user_states = {}  # {user_id: {'state': 'waiting_for_file/file_action', 'file_type': 'permissions/admins/blacklist', 'action': 'add/remove'}}
waiting_for_file = {} 
user_messages = {}

# Импорт модулей
from modules.permission_checker import check_user_permission, manage_user_id
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
                f"{config['messages']['good_evening']}\n{config['messages']['schedule_for_tomorrow'].format(tomorrow_str=tomorrow_str)}\n\n{schedule_text}",
                parse_mode=ParseMode.HTML
            )
            logger.info(config['logger_messages']['group_sended'])
        else:
            await bot.send_message(GROUP_ID, config["messages"]["schedule_not_found"])
            logger.warning(config['logger_messages']['group_no_schedule'])
    except Exception as e:
        logger.error(config['logger_messages']['send_error'].format(e=e))

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['start_received'].format(username=username, user_id=user_id))

    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [types.KeyboardButton(text=config['buttons_text']['reply']['today']),
            types.KeyboardButton(text=config['buttons_text']['reply']['tomorrow'])]
        ]
    )

    await message.answer(
        config["messages"]["start_message"], 
        reply_markup=keyboard, 
        parse_mode=ParseMode.HTML
        )

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

    has_permission = await check_user_permission(bot, False, GROUP_ID, PERMISSIONS_FILE, BLACKLIST_FILE, user_id, config)
    if has_permission == "Banned":
        await message.react([ReactionTypeEmoji(emoji=config['reactions']['banned'])])
    else:
        if has_permission:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['parsing'])])
            schedule_text = await parse_schedule_for_today(SCHEDULE_FILE, config)
            if schedule_text:
                await message.answer(
                    f"{config['messages']['schedule_for_today'].format(today_str=today_str)}\n\n{schedule_text}", 
                    parse_mode=ParseMode.HTML
                    )
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

    has_permission = await check_user_permission(bot, False, GROUP_ID, PERMISSIONS_FILE, BLACKLIST_FILE,  user_id, config)
    if has_permission == "Banned":
        await message.react([ReactionTypeEmoji(emoji=config['reactions']['banned'])])
    else:
        if has_permission:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['parsing'])])
            schedule_text = await parse_schedule_for_tomorrow(SCHEDULE_FILE, config)
            if schedule_text:
                await message.answer(
                    f"{config['messages']['schedule_for_tomorrow'].format(tomorrow_str=tomorrow_str)}\n\n{schedule_text}", 
                    parse_mode=ParseMode.HTML
                    )
                logger.info(config['logger_messages']['tomorrow_sended'].format(tomorrow_str=tomorrow_str))
            else:
                await message.answer(config["messages"]["schedule_not_found"])
                logger.warning(config['logger_messages']['tomorrow_not_found'].format(tomorrow_str=tomorrow_str))
        else:
            await message.react([ReactionTypeEmoji(emoji=config['reactions']['no_permission'])])
            await message.answer(config["messages"]["no_permission"])

# Обработчик команды /ping
@dp.message(Command("ping"))
async def ping_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"

    logger.info(config['logger_messages']['user_ping'].format(username=username, user_id=user_id))
    
    await message.react([ReactionTypeEmoji(emoji=config['reactions']['ping'])])
    await message.answer(config["messages"]["ping_success"])

# Функция для создания клавиатуры панели управления
def get_control_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=config['buttons_text']['inline']['dummy1'], callback_data="dummy1"))
    builder.row(
        InlineKeyboardButton(text=config['buttons_text']['inline']['replace_file'], callback_data="replace_file"),
        InlineKeyboardButton(text=config['buttons_text']['inline']['update_schedule'], callback_data="update_schedule"),
    )
    builder.row(InlineKeyboardButton(text=config['buttons_text']['inline']['dummy2'], callback_data="dummy2"))
    builder.row(
        InlineKeyboardButton(text=config['buttons_text']['inline']['permissions'], callback_data="permissions"),
        InlineKeyboardButton(text=config['buttons_text']['inline']['admins'], callback_data="admins"),
        InlineKeyboardButton(text=config['buttons_text']['inline']['blacklist'], callback_data="blacklist"),
    )
    return builder.as_markup()

# Функция для создания клавиатуры работы с разрешениями
def get_permissions_keyboard(file_type: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=config['buttons_text']['inline']['add_id'], callback_data=f"add_id:{file_type}"),
        InlineKeyboardButton(text=config['buttons_text']['inline']['remove_id'], callback_data=f"remove_id:{file_type}"),
        InlineKeyboardButton(text=config['buttons_text']['inline']['list_ids'], callback_data=f"list_ids:{file_type}")
    )
    builder.row(InlineKeyboardButton(text=config['buttons_text']['inline']['back_to_control'], callback_data="back_to_control"))
    return builder.as_markup()

# Функция для создания клавиатуры отмены
def get_cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=config['buttons_text']['inline']['cancel_action'], callback_data="cancel_action"))
    return builder.as_markup()

# Обработчик команды /cp (панель управления)
@dp.message(Command("cp"))
async def control_panel(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    logger.info(config['logger_messages']['user_try_cp'].format(username=username, user_id=user_id))

    # Проверка, что пользователь является админом
    has_permission = await check_user_permission(bot, True, GROUP_ID, ADMINS_FILE, BLACKLIST_FILE, user_id, config)
    if has_permission == "Banned":
        await message.react([ReactionTypeEmoji(emoji=config['reactions']['banned'])])
    else:
        if has_permission: 
            # Очищаем предыдущее состояние пользователя
            if user_id in user_states:
                del user_states[user_id]

            keyboard = get_control_panel_keyboard()
            await message.answer(config['messages']['control_panel'], reply_markup=keyboard)
        else:
            await message.answer(config["messages"]["no_access"])

# Обработчик callback-запросов
@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username
    message = callback.message
    data = callback.data

    # Инициализируем хранилище для пользователя, если его нет
    if user_id not in user_messages:
        user_messages[user_id] = {'message_to_delete': None}

    # Обязательная проверка прав при нажатии кнопок
    if data:
        has_permission = await check_user_permission(bot, True, GROUP_ID, ADMINS_FILE, BLACKLIST_FILE, user_id, config)
        if has_permission == "Banned":
            logger.warning(config['logger_messages']['cp_banned'].format(username=username, user_id=user_id, action=data))
            await callback.answer(text=config['reactions']['banned'], show_alert=False)
        else:
            if has_permission: 
                # Если нажали "Отменить"
                if data == "cancel_action":
                    action_logged = "None"

                    if user_id in user_states:
                        state = user_states[user_id]
                        if 'file_type' in state:
                            # Получаем сохраненные состояния
                            action_info = "add_id" if state.get('action') == 'add' else \
                                "remove_id" if state.get('action') == 'remove' else "None"
                            permission_text = state.get('permission_text') # , 'файлом'
                            action_logged = f"{permission_text}|{action_info}"

                            # Возвращаемся к работе с разрешениями для конкретного файла
                            keyboard = get_permissions_keyboard(state['file_type'])
                            await message.edit_text(
                                config['messages']['select_action'].\
                                format(pt=permission_text), 
                                reply_markup=keyboard,
                                parse_mode=ParseMode.MARKDOWN
                                )
                            
                    elif user_id in waiting_for_file and waiting_for_file[user_id]:
                        action_logged = "replace_file"
                        # Возвращаемся к панели управления
                        keyboard = get_control_panel_keyboard()
                        await message.edit_text(config['messages']['control_panel'], reply_markup=keyboard)
                        waiting_for_file[user_id] = False

                    else:
                        # Если состояние не сохранено, возвращаемся к панели управления
                        keyboard = get_control_panel_keyboard()
                        await message.edit_text(config['messages']['control_panel'], reply_markup=keyboard)
                        waiting_for_file[user_id] = False
                        if user_id in user_messages:
                            user_messages[user_id]['message_to_delete'] = None

                    # Очищаем message_to_delete для этого пользователя
                    if user_id in user_messages:
                        user_messages[user_id]['message_to_delete'] = None

                    logger.info(config['logger_messages']['act_cancel'].format(
                        username=username,
                        user_id=user_id,
                        action=action_logged
                    ))

                    await callback.answer()
                    return

                if data in ["dummy1", "dummy2"]:
                    logger.info(config['logger_messages']['act_button'].format(username=username, user_id=user_id, button=config['buttons_text']['inline'][data]))
                    await callback.answer(config['callback_answers'][data], show_alert=True)

                # Обработка нажатий на панели управления
                if data == "replace_file":
                    logger.info(config['logger_messages']['act_rf'].format(username=username, user_id=user_id))
                    # Переходим в режим ожидания файла
                    waiting_for_file[user_id] = True
                    keyboard = get_cancel_keyboard()
                    send_message = await message.edit_text(config["messages"]["send_file_prompt"], reply_markup=keyboard)
                    send_message
                    user_messages[user_id]['message_to_delete'] = send_message.message_id

                elif data == "update_schedule":
                    logger.info(config['logger_messages']['act_upd'].format(username=username, user_id=user_id))
                    # Обновляем расписание
                    result = await download_schedule(SCHEDULE_FILE, config)
                    if result:
                        logger.info(config['logger_messages']['upd_successful'].format(username=username, user_id=user_id))
                        await callback.answer(config['callback_answers']['url_parsed'], show_alert=True)
                    else:
                        logger.warning(config['logger_messages']['upd_unsuccessful'].format(username=username, user_id=user_id))
                        await callback.answer(config['callback_answers']['url_unparsed'], show_alert=True)
                    await callback.answer()

                elif data in ["permissions", "admins", "blacklist"]: 
                    logger.info(config['logger_messages']['act_button'].format(username=username, user_id=user_id, button=config['buttons_text']['inline'][data]))
                    # Сохраняем тип файла в состоянии пользователя
                    file_type_map = {
                        "permissions": PERMISSIONS_FILE,
                        "admins": ADMINS_FILE,
                        "blacklist": BLACKLIST_FILE
                    }
                    file_type = data
                    file_path = file_type_map[file_type]

                    # Сохраняем состояние пользователя
                    user_states[user_id] = {
                        'file_type': file_type,
                        'file_path': file_path,
                        'permission_text': config['buttons_text']['inline']['permissions'] if file_type == "permissions" else
                                        config['buttons_text']['inline']['admins'] if file_type == "admins" else
                                        config['buttons_text']['inline']['blacklist']
                    }

                    keyboard = get_permissions_keyboard(file_type)
                    permission_text = user_states[user_id]['permission_text']
                    await message.edit_text(
                        config['messages']['select_action'].\
                        format(pt=permission_text), 
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                        )

                elif data.startswith(("add_id:", "remove_id:")):
                    # Разбираем данные
                    action_type, file_type = data.split(":")
                    action = "add" if action_type == "add_id" else "remove"
                    
                    # Сохраняем состояние пользователя с информацией о типе файла и тексте
                    file_path_map = {
                        "permissions": PERMISSIONS_FILE,
                        "admins": ADMINS_FILE,
                        "blacklist": BLACKLIST_FILE
                    }
                    file_path = file_path_map[file_type]

                    permission_text = config['buttons_text']['inline']['permissions'] if file_type == "permissions" else \
                    config['buttons_text']['inline']['admins'] if file_type == "admins" else \
                    config['buttons_text']['inline']['blacklist']

                    logger.info(config['logger_messages']['act_edit_permissions'].format(username=username, user_id=user_id, action=f"{permission_text}|{action_type}"))

                    user_states[user_id] = {
                        'state': 'waiting_for_id',
                        'action': action,
                        'file_type': file_type,
                        'file_path': file_path,
                        'permission_text': permission_text
                    }

                    action_text = config['messages']['adding'] if action == "add" else config['messages']['deleting']
                    keyboard = get_cancel_keyboard()
                    edit_message = await message.edit_text(
                        config['messages']['enter_id'].\
                        format(act=action_text, pt=permission_text), 
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                        )
                    edit_message
                    user_messages[user_id]['message_to_delete'] = edit_message.message_id

                elif data.startswith("list_ids:"):
                    # Показываем содержимое файла
                    file_type = data.split(":")[1]
                    file_path_map = {
                        "permissions": PERMISSIONS_FILE,
                        "admins": ADMINS_FILE,
                        "blacklist": BLACKLIST_FILE
                    }
                    file_path = file_path_map[file_type]
                    permission_text = \
                        config['buttons_text']['inline']['permissions'] if file_type == "permissions" else \
                        config['buttons_text']['inline']['admins'] if file_type == "admins" else \
                        config['buttons_text']['inline']['blacklist']
                    
                    try:
                        with open(file_path, 'r') as f:
                            content = f.read()

                        if not content:
                            content = "Файл пуст"

                        logger.info(config['logger_messages']['act_get_list_ids'].format(username=username, user_id=user_id, pt=permission_text))
                        await message.answer(
                            config['messages']['permissions_list'].format(pt=permission_text, c=content),
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except FileNotFoundError:
                        logger.error(config['logger_messages']['act_get_list_ids_error'].format(username=username, user_id=user_id, pt=permission_text, file=file_type))
                        await callback.answer(config['callback_answers']['perm_file_not_found'].format(file_type=file_type), show_alert=True)

                elif data == "back_to_control":
                    logger.info(config['logger_messages']['act_button'].format(username=username, user_id=user_id, button=config['buttons_text']['inline'][data]))
                    # Возвращаемся к панели управления
                    keyboard = get_control_panel_keyboard()
                    await message.edit_text(config['messages']['control_panel'], reply_markup=keyboard)

                    # Очищаем состояние пользователя и message_to_delete
                    if user_id in user_states:
                        del user_states[user_id]
                    if user_id in user_messages:
                        user_messages[user_id]['message_to_delete'] = None

                # Всегда отвечаем на callback, чтобы убрать "прогрузку кнопок"
                await callback.answer()

            else:
                logger.warning(config['logger_messages']['cp_no_permission'].format(username=username, user_id=user_id, action=data))
                await callback.answer(text=config['callback_answers']['no_access'], show_alert=True)

# Обработчик документов (для замены файла расписания)
@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id

    # Инициализируем хранилище для пользователя, если его нет
    if user_id not in user_messages:
        user_messages[user_id] = {'message_to_delete': None}

    if waiting_for_file.get(user_id, False):
        if message.document:
            logger.info(config['logger_messages']['rf_successful'].format(username=username, user_id=user_id))
            file = await bot.get_file(message.document.file_id)
            file_path = Path(SCHEDULE_FILE)
            await bot.download_file(file.file_path, file_path)
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            await message.answer(config["messages"]["file_received"], reply_markup=types.ReplyKeyboardRemove())

            # Возвращаем панели управления
            keyboard = get_control_panel_keyboard()
            await message.answer(config['messages']['control_panel'], reply_markup=keyboard)

            waiting_for_file[user_id] = False
            if user_id in user_states:
                del user_states[user_id]
            user_messages[user_id] = {'message_to_delete': None}

        else:
            logger.warning(config['logger_messages']['rf_not_file'].format(username=username, user_id=user_id))
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            keyboard = get_cancel_keyboard()
            send_message = await message.answer(config["messages"]["send_file_prompt"], reply_markup=keyboard)
            send_message
            user_messages[user_id]['message_to_delete'] = send_message.message_id

    else:
        logger.warning(config['logger_messages']['user_send_file_only'].format(username=username, user_id=user_id))
        has_permission = await check_user_permission(bot, True, GROUP_ID, ADMINS_FILE, BLACKLIST_FILE, user_id, config)
        if has_permission == "Banned" or not has_permission:
            pass
        else:
            await message.answer(
                config["messages"]["send_file_first"].format(replace_button=config['buttons_text']['inline']['replace_file']),
                parse_mode=ParseMode.HTML
                )

# Обработчик текстовых сообщений для добавления/удаления ID
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    username = message.from_user.username
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Инициализируем хранилище для пользователя, если его нет
    if user_id not in user_messages:
        user_messages[user_id] = {'message_to_delete': None}

    if user_id in user_states and user_states[user_id].get('state') == 'waiting_for_id':
        state = user_states[user_id]
        user_input = message.text.strip()

        # Проверяем валидность введенного ID
        if not user_input.isdigit() or len(user_input) < 9 or len(user_input) > 11:
            logger.warning(config['logger_messages']['user_send_invalid_id'].format(username=username, user_id=user_id, uid=user_input))
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            keyboard = get_cancel_keyboard()
            send_message = await message.answer(config['messages']['invalid_id'], reply_markup=keyboard)
            send_message
            user_messages[user_id]['message_to_delete'] = send_message.message_id
            return

        action = state['action']
        file_path = state['file_path']
        user_id_to_manage = int(user_input)

        logger.info(config['logger_messages']['user_send_valid_id'].format(username=username, user_id=user_id, uid=user_id_to_manage))

        # Выполняем действие с файлом
        result = await manage_user_id(file_path, user_id_to_manage, action, config)

        permission_text_map = {
            "permissions": config['buttons_text']['inline']['permissions'],
            "admins": config['buttons_text']['inline']['admins'],
            "blacklist": config['buttons_text']['inline']['blacklist']
        }
        permission_text = permission_text_map.get(state['file_type']) # , "файла"

        if result == "success":
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            action_text = config['messages']['added'] if action == "add" else config['messages']['deleted']
            logger.info(config['logger_messages']['id_success'].format(uid=user_id_to_manage, act=action_text, pt=permission_text))
            await message.answer(
                config['messages']['id_validated'].\
                format(uid=user_id_to_manage, act=action_text, pt=permission_text), 
                parse_mode=ParseMode.MARKDOWN
                )
            user_messages[user_id]['message_to_delete'] = None

            keyboard = get_permissions_keyboard(state['file_type'])
            await message.answer(
                config['messages']['select_action'].\
                format(pt=permission_text), 
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
                )
            del user_states[user_id]

        elif result == "exists":
            logger.warning(config['logger_messages']['id_exists'].format(uid=user_id_to_manage, pt=permission_text))
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            keyboard = get_cancel_keyboard()
            send_message = await message.answer(
                config['messages']['id_exists'].\
                format(uid=user_id_to_manage, pt=permission_text), 
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
                )
            send_message
            user_messages[user_id]['message_to_delete'] = send_message.message_id

        elif result == "not_found":
            logger.warning(config['logger_messages']['id_not_found'].format(uid=user_id_to_manage, pt=permission_text))
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            keyboard = get_cancel_keyboard()
            send_message = await message.answer(
                config['messages']['id_not_found'].\
                format(uid=user_id_to_manage, pt=permission_text), 
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
                )
            send_message
            user_messages[user_id]['message_to_delete'] = send_message.message_id

        else:
            await bot.delete_message(chat_id, user_messages[user_id]['message_to_delete'])
            keyboard = get_cancel_keyboard()
            send_message = await message.answer(
                config['messages']['id_validate_error'], 
                reply_markup=keyboard
                )
            send_message
            user_messages[user_id]['message_to_delete'] = send_message.message_id
            
    else:
        # Обработка обычных текстовых сообщений (Сегодня/Завтра)
        if message.text == config['buttons_text']['reply']['today']:
            await today_command(message)
        elif message.text == config['buttons_text']['reply']['tomorrow']:
            await tomorrow_command(message)

async def main():
    # Настройка планировщика задач
    if config['scheduler']['is_activated'] is True: # Если в конфиге False, то планировщик не будет работать
        @crontab(config['scheduler']['settings'])  # 00 22 * * 0,1,2,3,4,6 = 22:00 по понедельникам-пятницам и воскресеньям
        async def scheduled_task():
            await send_schedule()
        logger.info(config['logger_messages']['scheduler_started'])

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
