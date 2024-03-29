import logging
import os
import sys
import time
from http import HTTPStatus
from json.decoder import JSONDecodeError

import requests
import telegram
from dotenv import load_dotenv

from endpoints import ENDPOINT
from exceptions import (BadTokenException, NoHomeworkName, NoStatusData,
                        NotOKResponse, TimestampException)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправка сообщения в телеграм."""
    try:
        logging.debug('Начинаем отправку сообщения в телеграм')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Сообщение успешно отправлено в телеграм')
    except telegram.TelegramError:
        logging.error('Ошибка при отправке сообщения в телеграм')


def get_api_answer(timestamp):
    """Запрос к API Практикума."""
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params={
            'from_date': timestamp})
    except requests.RequestException:
        logging.error('При запросе к API возникает исключение')
    if not response.status_code == (HTTPStatus.OK or HTTPStatus.BAD_REQUEST
                                    or HTTPStatus.UNAUTHORIZED):
        logging.error('Ошибка ответа от API Практикума')
        raise NotOKResponse('Ошибка ответа от API Практикума')
    try:
        return response.json()
    except JSONDecodeError:
        logging.error('Ошибка преобразования ответа API в json')


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        logging.error('В ответе API под ключом homeworks - не словарь')
        raise TypeError
    elif response.get('code') == 'UnknownError':
        logging.error('Ошибка формата from_date')
        raise TimestampException('Ошибка формата from_date')
    elif response.get('code') == 'not_authenticated':
        logging.error('Запрос с недействительным или некорректным токеном')
        raise BadTokenException('Запрос с некорректным токеном')
    elif not isinstance(response.get('homeworks'), list):
        logging.error('В ответе API под ключом homeworks - не список')
        raise TypeError
    elif len(response.get('homeworks')) == 0:
        logging.debug('Обновлений домашки нет')
        pass
    else:
        return response.get('homeworks')[0]


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус."""
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise NoHomeworkName('В ответе API домашки нет ключа homework_name')
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    if verdict is None:
        raise NoStatusData('В ответе API домашки нет статуса')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    if not check_tokens():
        logging.critical('Отсутствуют обязательные переменные окружения')
        sys.exit()

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework is not None:
                status = parse_status(homework)
                send_message(bot, status)
            timestamp = response.get('current_date')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename='main.log',
        filemode='w',
        format='%(asctime)s, %(levelname)s, %(message)s'
    )

    main()
