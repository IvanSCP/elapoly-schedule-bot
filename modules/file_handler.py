import aiohttp
from bs4 import BeautifulSoup
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

async def get_schedule_link(session: aiohttp.ClientSession, config: dict) -> Optional[str]:
    try:
        async with session.get(config['url_parser']['schedule_page_url'], ssl=False) as response:
            content = await response.read()
            soup = BeautifulSoup(content, 'html.parser')

            # Ищем ссылку с текстом, указанным в конфиге
            link = soup.find('a', string=config['url_parser']['schedule_link_text'])

            if link and link.has_attr('href'):
                full_url = config['url_parser']['base_url'] + link['href']
                logger.info(config['logger_messages']['parser_link_founded'].format(full_url=full_url))
                return full_url

            logger.warning(config['logger_messages']['parser_link_not_founded'])
            return None
    except Exception as e:
        logger.error(config['logger_messages']['parser_error'].format(e=e))
        return None

async def download_schedule(file_path, config: dict) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            # Получаем URL для скачивания
            schedule_url = await get_schedule_link(session, config)
            if not schedule_url:
                logger.error(config['logger_messages']['parser_failed'])
                return None

            # Скачиваем файл
            async with session.get(schedule_url, ssl=False) as response:
                if response.status == 200:
                    content = await response.read()

                    # Сохраняем в указанный файл (перезаписываем существующий)
                    with open(file_path, 'wb') as file:
                        file.write(content)

                    logger.info(config['logger_messages']['file_downloaded'].format(file_path=file_path))
                    return str(file_path)
                else:
                    logger.error(config['logger_messages']['file_download_failed'].format(rs=response.status))
                    return None
    except Exception as e:
        logger.error(config['logger_messages']['file_download_error'].format(e=e))
        return None
