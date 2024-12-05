FROM python:3.12

# Устанавливаем зависимости системы
RUN apt-get update && apt-get install -y build-essential

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY .. /app/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
