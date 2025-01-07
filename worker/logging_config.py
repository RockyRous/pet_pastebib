import logging
import sys

# Настройка логгера для FastAPI
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Логирование запросов и метрик
def log_request(request, response_time, status_code):
    """ Функция для логирования и сбора метрик для каждого запроса. """
    pass

    # Логируем информацию о запросе
    # logger.info(f"Request to {request.url} completed with status {status_code}")



