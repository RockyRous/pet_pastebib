import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from prometheus_client import Counter, Histogram


def config_log(level=logging.DEBUG):
    formatter = logging.Formatter(
        fmt="[%(asctime)s.%(msecs)03d] %(module)s:%(lineno)d %(levelname)7s %(message)s",
        datefmt='%d-%m-%Y %H:%M:%S'
    )

    current_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(current_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_file_path = os.path.join(logs_dir, 'application.log')

    logger = logging.getLogger("custom_logger")
    logger.setLevel(level)

    file_handler = RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(file_handler)

    return logger


logger = config_log()


# Настройка логгера для FastAPI
logger_uvicorn = logging.getLogger("uvicorn")
logger_uvicorn.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger_uvicorn.addHandler(console_handler)

# Создание метрик для Prometheus
REQUESTS = Counter("http_requests_total", "Total number of HTTP requests", ["method", "endpoint", "status_code"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "Histogram of HTTP request durations", ["method", "endpoint"])


# Логирование и сбор метрик
def log_request(request, response_time, status_code):
    """
    Функция для логирования и сбора метрик для каждого запроса.
    """
    # Собираем метрики для Prometheus
    REQUESTS.labels(method=request.method, endpoint=str(request.url), status_code=status_code).inc()
    REQUEST_DURATION.labels(method=request.method, endpoint=str(request.url)).observe(response_time)

    # Логируем информацию о запросе
    logger.debug(f"Request to {request.url} completed with status {status_code}")
    logger.info(f"Request to {request.url} completed with status {status_code}")