from aiogram import Bot
import os
import logging
import json

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
        logger.warning(config['logger_messages']['permissions_file_not_found'])
        return False
    with open(permissions_file, 'r') as f:
        permitted_users = [line.strip() for line in f.readlines()]
    return str(user_id) in permitted_users

async def check_user_permission(bot: Bot, group_id: int, permissions_file: str, blacklist_file: str,user_id: int, config: dict) -> bool:
    if await is_banned(blacklist_file, user_id, config):
        return "Banned"
    else:
        if await is_in_chat(bot, group_id, user_id, config):
            return True
        return await has_permission(permissions_file, user_id, config)

async def is_admin(admins_file: str, user_id: int, config: dict) -> bool:
    if not os.path.exists(admins_file):
        logger.warning(config['logger_messages']['admins_file_not_found'])
        return False
    with open(admins_file, 'r') as f:
        permitted_users = [line.strip() for line in f.readlines()]
    return str(user_id) in permitted_users
