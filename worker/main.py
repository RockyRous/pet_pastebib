import os
import time

import pika
import json
import asyncio
import asyncpg
import logging

# Настройки из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL_TEXT")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "delayed_exchange")
credentials = pika.PlainCredentials('user', 'password') # todo: Тоже получать из енв
connection_params = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Функция для удаления данных из PostgreSQL
async def delete_from_db(hash_value: str):
    conn = None
    try:
        # Подключаемся к базе данных
        logger.info(f"Connecting to database with URL: {DATABASE_URL}")
        conn = await asyncpg.connect(DATABASE_URL)

        # Выполняем запрос на удаление данных
        await conn.execute("DELETE FROM posts WHERE hash = $1", hash_value)
        logger.info(f"Successfully deleted data with hash: {hash_value}")

    except Exception as e:
        logger.error(f"Error deleting data with hash {hash_value}: {e}")
    finally:
        if conn:
            await conn.close()
            logger.info("Database connection closed.")


# Обработчик сообщений из RabbitMQ
def process_message(ch, method, properties, body):
    try:
        message = json.loads(body)
        hash_to_delete = message.get("hash")

        if not hash_to_delete:
            logger.warning("Received message without a 'hash' field.")
            ch.basic_nack(delivery_tag=method.delivery_tag)
            return

        # Асинхронный вызов функции удаления
        asyncio.run(delete_from_db(hash_to_delete))

        # Подтверждение обработки сообщения
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f"Message with hash {hash_to_delete} processed successfully.")

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Unexpected error while processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def main():
    try:
        # Настройка RabbitMQ соединения
        logger.info(f"Connecting to RabbitMQ at {RABBITMQ_HOST}...")

        for i in range(5):
            try:
                connection = pika.BlockingConnection(connection_params)
                break
            except Exception:
                logger.warning(f"Attempt {i + 1}: RabbitMQ is not ready. Retrying in 5 seconds...")
                time.sleep(5)
        else:
            raise RuntimeError("Unable to connect to RabbitMQ")

        channel = connection.channel()

        # Объявляем обменник с типом x-delayed-message
        logger.info(f"Declaring exchange {EXCHANGE_NAME} with type x-delayed-message...")
        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type="x-delayed-message",
            arguments={"x-delayed-type": "direct"}
        )

        # Создание очереди и привязка к обменнику
        queue_name = "delete_queue"
        logger.info(f"Declaring queue {queue_name} and binding to exchange...")
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=queue_name, routing_key="delete_key")

        # Подписка на очередь
        logger.info("Starting to consume messages...")
        channel.basic_consume(queue=queue_name, on_message_callback=process_message)
        channel.start_consuming()

    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}")


if __name__ == "__main__":
    main()
