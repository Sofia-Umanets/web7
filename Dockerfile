FROM python:3.9-slim


WORKDIR /app


COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt


COPY . /app/


CMD ["python", "/app/lesson7/main.py"] CREATE DATABASE IF NOT EXISTS formdb;