FROM rabbitmq:4.0.4-management

# Скачиваем плагин rabbitmq_delayed_message_exchange версии 4.0.2
ADD https://github.com/rabbitmq/rabbitmq-delayed-message-exchange/releases/download/v4.0.2/rabbitmq_delayed_message_exchange-4.0.2.ez /plugins/

# Устанавливаем права доступа к плагину
RUN chmod 644 /plugins/rabbitmq_delayed_message_exchange-4.0.2.ez

# Активируем плагин
RUN rabbitmq-plugins enable --offline rabbitmq_delayed_message_exchange

# Запускаем RabbitMQ сервер
CMD ["rabbitmq-server"]
