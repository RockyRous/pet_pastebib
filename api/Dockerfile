FROM python:3.12

# Установите необходимые пакеты для сборки
RUN apt-get update && apt-get install -y python3-dev build-essential

# Установите setuptools, чтобы включить distutils
RUN pip install --no-cache-dir setuptools

WORKDIR /app


COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы проекта
COPY . /app/

# Запускаем приложение через Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]