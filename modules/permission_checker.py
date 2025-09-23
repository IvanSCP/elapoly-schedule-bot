from aiogram import Bot
import os, re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def is_banned(blacklist_file: str, user_id: int, config: dict) -> bool:
    if not os.path.exists(blacklist_file):
        logger.warning(config['logger_messages']['blacklist_file_not_found'])
        return False
    with open(blacklist_file, 'r') as f:
        permitted_users = [line.strip() for line in f.readlines()]
    return str(user_id) in permitted_users

async def is_in_chat(bot: Bot, group_id: int, user_id: int, config: dict) -> bool:
    try:
        chat_member = await bot.get_chat_member(group_id, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(config['logger_messages']['permission_check_error'].format(e=e))
        return False

async def has_permission(permissions_file: str, user_id: int, config: dict) -> bool:
    if not os.path.exists(permissions_file):
        logger.warning(config['logger_messages']['permissions_file_not_found'].format(permissions_file=permissions_file))
        return False
    with open(permissions_file, 'r') as f:
        permitted_users = [line.strip() for line in f.readlines()]
    return str(user_id) in permitted_users

async def check_user_permission(bot: Bot, need_admin_rights: bool, group_id: int, permissions_file: str, blacklist_file: str, user_id: int, config: dict) -> bool:
    if await is_banned(blacklist_file, user_id, config):
        return "Banned"
    else:
        if need_admin_rights is True:
            return await has_permission(permissions_file, user_id, config)
        else: 
            if await is_in_chat(bot, group_id, user_id, config):
                return True
            return await has_permission(permissions_file, user_id, config)

async def manage_user_id(file_path: str, user_id: int, action: str, config: dict) -> str:
    """
    Управление ID пользователя в файле доступа

    Args:
        file_path: Путь к файлу доступа
        user_id: ID пользователя для добавления или удаления
        action: "add" для добавления, "remove" для удаления

    Returns:
        "success" - операция выполнена успешно
        "exists" - ID уже существует в файле (при добавлении)
        "not_found" - ID не найден в файле (при удалении)
    """
    try:
        # Создаем файл, если его нет
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                pass

        # Читаем текущее содержимое
        with open(file_path, 'r') as f:
            lines = [line.strip() for line in f.readlines()]

        user_id_str = str(user_id)

        if action == "add":
            # Проверяем, что ID еще нет в файле
            if user_id_str in lines:
                return "exists"

            # Добавляем новый ID
            with open(file_path, 'a') as f:
                f.write(f"{user_id_str}\n")
            return "success"
            

        elif action == "remove":
            # Проверяем, что ID есть в файле
            if user_id_str not in lines:
                return "not_found"

            # Удаляем ID
            with open(file_path, 'w') as f:
                for line in lines:
                    if line != user_id_str:
                        f.write(f"{line}\n")
            return "success"

    except Exception as e:
        logger.error(config['logger_messages']['manage_user_id_error'].format(user_id=user_id, file_path=file_path, e=e))
        return "error"
