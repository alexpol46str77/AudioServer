import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import asyncpg
from dotenv import load_dotenv
import bcrypt

# 1. Загружаем переменные из файла .env
load_dotenv()

app = FastAPI(title="Audiophile Server API PRO")

# 2. Настраиваем безопасное хэширование паролей через bcrypt
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Переменная для хранения пула соединений PostgreSQL
db_pool = None

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    tariff VARCHAR(20) DEFAULT 'free'
);
CREATE TABLE IF NOT EXISTS track_actions (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    track_title VARCHAR(255) NOT NULL,
    rating INT CHECK (rating >= 1 AND rating <= 5),
    play_count INT DEFAULT 0
);
"""

class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class TrackAction(BaseModel):
    user_id: int
    track_title: str
    rating: int = None

# --- 🛠️ ОБНОВЛЕННЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С БЕЗОПАСНОСТЬЮ (ЧИСТЫЙ BCRYPT) ---
def get_password_hash(password: str) -> str:
    # bcrypt требует перевода строки в байты (encode)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')  # Возвращаем строку для записи в текстовое поле БД

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # Сверяем чистый пароль с хэшем из базы данных
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

    
# --- ⚡ СОБЫТИЯ СТАРТА И ОСТАНОВКИ СЕРВЕРА (ПУЛ СОЕДИНЕНИЙ) ---
@app.on_event("startup")
async def startup_event():
    global db_pool
    print("⏳ Инициализация пула соединений PostgreSQL...")
    try:
        # Создаем пул соединений один раз при старте приложения
        db_pool = await asyncpg.create_pool(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            min_size=5,  # Минимальное количество готовых коннектов в памяти
            max_size=20  # Максимальное количество параллельных коннектов
        )
        # Берем один коннект из пула для проверки и создания таблиц
        async with db_pool.acquire() as conn:
            await conn.execute(INIT_SQL)
        print("✅ Пул соединений успешно создан. Таблицы верифицированы!")
    except Exception as e:
        print(f"❌ Критическая ошибка при старте БД: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global db_pool
    if db_pool:
        await db_pool.close()
        print("🛑 Пул соединений с БД закрыт.")

# --- 🧩 ВНЕДРЕНИЕ ЗАВИСИМОСТЕЙ (DEPENDENCY INJECTION) ---
# Эта функция будет автоматически выдавать коннект из пула для каждого роута
async def get_db():
    if db_pool is None:
        raise HTTPException(status_code=500, detail="База данных не инициализирована")
    async with db_pool.acquire() as connection:
        yield connection  # Передает коннект роуту и возвращает его в пул после завершения запроса

# --- 🚀 ОБНОВЛЕННЫЕ МАРШРУТЫ С DEPENDS ---

@app.post("/register")
async def register_user(user: UserRegister, conn=Depends(get_db)):
    # Используем профессиональный bcrypt хэш с солью
    hashed = get_password_hash(user.password)
    try:
        await conn.execute(
            "INSERT INTO users (username, password_hash) VALUES ($1, $2)",
            user.username, hashed
        )
        return {"status": "success", "message": f"Пользователь {user.username} успешно зарегистрирован!"}
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Такой логин уже занят!")

@app.post("/login")
async def login_user(user: UserLogin, conn=Depends(get_db)):
    row = await conn.fetchrow("SELECT id, password_hash, tariff FROM users WHERE username = $1", user.username)
    if not row or not verify_password(user.password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Неверный логин или пароль!")
        
    return {
        "status": "success", 
        "message": f"Добро пожаловать, {user.username}!",
        "user_id": row["id"],
        "tariff": row["tariff"]
    }

@app.post("/track_action")
async def track_action(action: TrackAction, conn=Depends(get_db)):
    if action.rating is not None and (action.rating < 1 or action.rating > 5):
        raise HTTPException(status_code=400, detail="Рейтинг должен быть от 1 до 5 звезд!")
    
    try:
        row = await conn.fetchrow(
            "SELECT id, play_count FROM track_actions WHERE user_id = $1 AND track_title = $2",
            action.user_id, action.track_title
        )
        if row:
            new_plays = row["play_count"] + 1
            await conn.execute(
                "UPDATE track_actions SET rating = $1, play_count = $2 WHERE id = $3",
                action.rating, new_plays, row["id"]
            )
            msg = f"Статистика трека '{action.track_title}' обновлена! Прослушиваний: {new_plays}"
        else:
            await conn.execute(
                "INSERT INTO track_actions (user_id, track_title, rating, play_count) VALUES ($1, $2, $3, 1)",
                action.user_id, action.track_title, action.rating
            )
            msg = f"Трек '{action.track_title}' впервые добавлен в историю прослушиваний!"
        return {"status": "success", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка БД: {e}")