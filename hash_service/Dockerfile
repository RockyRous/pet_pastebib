FROM python:3.12

RUN apt-get update && apt-get install -y python3-dev build-essential

RUN pip install --no-cache-dir setuptools

WORKDIR /app


COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]