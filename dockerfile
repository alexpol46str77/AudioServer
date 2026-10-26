# 1. Используем легкий официальный образ Python
FROM docker.io/library/python:3.12-slim

# 2. Указываем рабочую папку внутри будущего контейнера
WORKDIR /app

# 3. Копируем файл кода с твоего компьютера внутрь контейнера
COPY main.py .

# 4. Устанавливаем необходимые серверные библиотеки
RUN pip install --no-cache-dir fastapi uvicorn asyncpg -i https://yandex.ru

# 5. Открываем порт 8000 наружу
EXPOSE 8000

# 6. Команда для автоматического старта сервера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
