import os
import telegram
import time
import requests
import logging
import sys
from dotenv import load_dotenv
from http import HTTPStatus

from exceptions import TimestampException, BadTokenException, NotOKResponse
from exceptions import NoHomeworkName, NoStatusData

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    filemode='w',
    format='%(asctime)s, %(levelname)s, %(message)s'
)


def check_tokens():
    """Проверка доступности переменных окружения."""
    if (PRACTICUM_TOKEN or TELEGRAM_TOKEN or TELEGRAM_CHAT_ID) is None:
        logging.critical('Отсутствуют обязательные переменные окружения')
        sys.exit()
    pass


def send_message(bot, message):
    """Отправка сообщения в телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Сообщение отправлено в телеграм')
    except Exception:
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
    return response.json()


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not type(response) == dict:
        logging.error('В ответе API под ключом homeworks - не словарь')
        raise TypeError
    elif response.get('code') == 'UnknownError':
        logging.error('Ошибка формата from_date')
        raise TimestampException('Ошибка формата from_date')
    elif response.get('code') == 'not_authenticated':
        logging.error('Запрос с недействительным или некорректным токеном')
        raise BadTokenException('Запрос с некорректным токеном')
    elif not type(response.get('homeworks')) == list:
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

    while True:
        try:
            check_tokens()
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework is not None:
                status = parse_status(homework)
                send_message(bot, status)
            timestamp = response.get('current_date')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
