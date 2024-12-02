from fastapi import FastAPI
import redis
from redis.sentinel import Sentinel
import time
import os

app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))

@app.get("/")
def read_root():
    return {"message": "API Service Running"}

@app.get("/line_redis")
def line_redis():
    """ Подключение к Redis напрямую """
    # Подключение к Redis (замените 'redis-node1' на имя или IP Master узла)
    redis_client = redis.Redis(host='redis-node1', port=6379, db=0)

    # Установка и получение значения
    redis_client.set('my_key', 'my_value')
    value = redis_client.get('my_key')
    return value.decode('utf-8')  # my_value


@app.get("/redis_sentinel")
def redis_sentinel():
    """ Использование Redis Sentinel """
    # Подключение к Sentinel
    sentinel = Sentinel([('sentinel-node1', 26379),
                         ('sentinel-node2', 26379),
                         ('sentinel-node3', 26379)],
                        socket_timeout=0.1)

    # Получить текущий master
    master = sentinel.master_for('mymaster', socket_timeout=0.1)

    # Установка значения через master
    master.set('my_key', 'my_value')

    # Получение значения
    value = master.get('my_key')
    return value.decode('utf-8')


@app.get("/cache_redis")
def cache_redis():
    """ Кеширование запросов """
    redis_client = redis.Redis(host='redis-node1', port=6379, db=0)

    def get_data_with_cache(key):
        # Попробовать получить данные из кеша
        cached_data = redis_client.get(key)
        if cached_data:
            print("Из кеша")
            return cached_data.decode('utf-8')

        # Если данных нет, получить их, например, из базы данных
        print("Получение из источника")
        data = f"Data for {key}"  # Замените на реальный запрос
        time.sleep(2)  # Симуляция задержки

        # Сохранить данные в кеш с TTL = 60 секунд
        redis_client.setex(key, 60, data)
        return data

    # Пример использования
    return get_data_with_cache('test_key')


