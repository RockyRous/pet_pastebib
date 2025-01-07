import logging
import sys
from prometheus_client import Counter, Histogram

# Настройка логгера для FastAPI
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

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
    logger.debug(f"REQUEST: Request to {request.url} completed with status {status_code}")
