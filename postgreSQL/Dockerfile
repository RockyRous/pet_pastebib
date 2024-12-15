FROM postgres:16-alpine

# Копируем скрипты для инициализации
COPY init.sql /docker-entrypoint-initdb.d/

# Установка дополнительных пакетов (если нужно, например, PostGIS)
RUN apk add --no-cache postgresql-contrib

# Настройка конфигурации
COPY custom-postgres.conf /etc/postgresql/postgresql.conf
RUN echo "include '/etc/postgresql/postgresql.conf'" >> /usr/share/postgresql/postgresql.conf.sample
