import os
import streamlit as st
import soundfile as sf
import requests
import time
import threading  # 🧵 Для запуска нарезки в фоновом потоке

st.set_page_config(page_title="FLAC to WAV Audiophile Player", layout="wide")
st.title("🎛️ Аудиофильский Музыкальный Центр")

# URL нашего локального бэкенда на FastAPI
BACKEND_URL = "http://127.0.0.1:8000"

# --- ИНИЦИАЛИЗАЦИЯ СЕССИИ ПОЛЬЗОВАТЕЛЯ ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

# --- ОКНО АВТОРИЗАЦИИ / РЕГИСТРАЦИИ (СТАБИЛЬНАЯ ФОРМА) ---
if not st.session_state["logged_in"]:
    st.subheader("🔐 Вход в личный кабинет аудиофила")
    
    col_auth1, col_auth2 = st.columns(2)
    with col_auth1:
        # Создаем форму для сбора данных
        with st.form(key="login_form"):
            username_input = st.text_input("👤 Логин:")
            password_input = st.text_input("🔑 Пароль:", type="password")
            
            # Делаем две удобные колонки для кнопок внутри самой формы
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                btn_login = st.form_submit_button("🚀 Войти", type="primary")
            with btn_col2:
                btn_register = st.form_submit_button("📝 Создать аккаунт")

    if btn_login:
        if username_input and password_input:
            try:
                response = requests.post(
                    f"{BACKEND_URL}/login", 
                    json={"username": username_input, "password": password_input}
                )
                if response.status_code == 200:
                    data = response.json()
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_input
                    st.session_state["user_id"] = data["user_id"]
                    st.success("🎉 Успешный вход!")
                    st.rerun()
                else:
                    st.error(f"❌ Ошибка: {response.json().get('detail', 'Неверные данные')}")
            except Exception as e:
                st.error(f"Не удалось связаться с сервером бэкенда: {e}")
        else:
            st.warning("Пожалуйста, заполните все поля!")

    if btn_register:
        if username_input and password_input:
            try:
                response = requests.post(
                    f"{BACKEND_URL}/register", 
                    json={"username": username_input, "password": password_input}
                )
                if response.status_code == 200:
                    st.success("✨ Зарегистрировано! Теперь можно войти.")
                else:
                    st.error(f"❌ {response.json().get('detail')}")
            except Exception as e:
                st.error(f"Ошибка сети: {e}")
                
    st.stop()  # Тормозим код здесь, пока юзер не авторизуется

# --- МЕНЮ ВЫХОДА В БОКОВОЙ ПАНЕЛИ ---
st.sidebar.markdown(f"👤 Пользователь: **{st.session_state['username']}** (ID: {st.session_state['user_id']})")
if st.sidebar.button("🚪 Выйти"):
    st.session_state["logged_in"] = False
    st.rerun()

# --- 📁 ДИНАМИЧЕСКИЙ ВЫБОР РАБОЧЕЙ ПАПКИ ---
st.write("---")
st.subheader("📁 Настройки рабочей директории")
custom_music_root = st.text_input("Укажите путь к папке с альбомами:", value="Music")

if not os.path.exists(custom_music_root):
    try:
        os.makedirs(custom_music_root, exist_ok=True)
        st.info(f"Создана новая пустая директория: {custom_music_root}")
    except Exception as e:
        st.error(f"❌ Не удалось создать указанную директорию: {e}")
        st.stop()

# --- СКАНИРОВАНИЕ АЛЬБОМОВ ---
try:
    albums = [d for d in os.listdir(custom_music_root) if os.path.isdir(os.path.join(custom_music_root, d))]
except Exception as e:
    st.error(f"❌ Ошибка при чтении папки: {e}")
    albums = []

if not albums:
    st.warning(f"⚠️ В папке '{custom_music_root}' пока нет альбомов. Скопируйте туда файлы.")
    st.stop()

selected_album = st.selectbox("📂 Выберите альбом из вашей коллекции:", albums)
ALBUM_DIR = os.path.join(custom_music_root, selected_album)

# --- НАДЕЖНЫЙ ПОИСК ФАЙЛОВ С ОБРАБОТКОЙ ОШИБОК ---
try:
    flac_files = [f for f in os.listdir(ALBUM_DIR) if f.lower().endswith('.flac')]
    cue_files = [f for f in os.listdir(ALBUM_DIR) if f.lower().endswith('.cue')]
except Exception as e:
    st.error(f"❌ Не удалось прочитать файлы альбома: {e}")
    st.stop()

if not flac_files or not cue_files:
    st.error(f"❌ Критическая ошибка: В папке альбома должен быть один файл .flac и один .cue!")
    st.stop()

TEST_FILE = os.path.join(ALBUM_DIR, flac_files[0])
CUE_FILE = os.path.join(ALBUM_DIR, cue_files[0])
OUTPUT_DIR = os.path.join(ALBUM_DIR, "Tracks_WAV")
PREVIEW_DIR = os.path.join(ALBUM_DIR, ".preview")

def cue_time_to_seconds(time_str):
    parts = time_str.split(':')
    return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 75.0

def parse_cue(cue_path):
    tracks = []
    current_track = {}
    if not os.path.exists(cue_path): return []
    with open(cue_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("TRACK"):
                if current_track: tracks.append(current_track)
                current_track = {"number": line.split()[1]}
            elif line.startswith("TITLE") and current_track: current_track["title"] = line.split('"')[1]
            elif line.startswith("PERFORMER") and current_track: current_track["performer"] = line.split('"')[1]
            elif line.startswith("INDEX 01") and current_track: current_track["start_time"] = cue_time_to_seconds(line.split()[2])
        if current_track: tracks.append(current_track)
    return tracks

# --- ИНТЕРФЕЙС ПЛЕЕРА ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ Обложка")
    cover_found = False
    for path in [ALBUM_DIR, os.path.join(ALBUM_DIR, "Art")]:
        if os.path.exists(path):
            for file in os.listdir(path):
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    st.image(os.path.join(path, file), width=300)
                    cover_found = True
                    break
        if cover_found: break
    if not cover_found: st.info("Обложка не найдена")

with col2:
    st.subheader("📊 Структура CUE-листа")
    tracks = parse_cue(CUE_FILE)
    if tracks:
        track_data = [{"№": t.get("number"), "Исполнитель": t.get("performer", "Неизвестно"), "Название трека": t.get("title", "Неизвестно")} for t in tracks]
        st.dataframe(track_data, use_container_width=True, hide_index=True)

# --- 🧵 ФУНКЦИЯ ДЛЯ ФОНОВОЙ НАРЕЗКИ ---
def background_splitting_task(tracks, samplerate, data, total_samples):
    import subprocess
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        total_tracks = len(tracks)
        
        for idx, track in enumerate(tracks):
            start_sample = int(track["start_time"] * samplerate)
            end_sample = int(tracks[idx + 1]["start_time"] * samplerate) if idx < len(tracks) - 1 else total_samples
            track_data = data[start_sample:end_sample]
            
            clean_title = "".join([c for c in track.get("title", "Track") if c.isalpha() or c.isdigit() or c==' ']).strip()
            wav_path = os.path.join(OUTPUT_DIR, f"{track['number']} - {clean_title}.wav")
            mp3_path = os.path.join(PREVIEW_DIR, f"{track['number']} - {clean_title}.mp3")
            
            sf.write(wav_path, track_data, samplerate, subtype='PCM_16')
            
            subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                            "-metadata", f"title={track.get('title')}", "-metadata", f"artist={track.get('performer')}", mp3_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
            
            st.session_state["split_progress"] = float((idx + 1) / total_tracks)
            st.session_state["split_status_text"] = f"Обработан трек {idx + 1} из {total_tracks}: {clean_title}"
            
        st.session_state["split_complete"] = True
    except Exception as error:
        st.session_state["split_error"] = str(error)

# Инициализация переменных прогресс-бара
if "split_progress" not in st.session_state: st.session_state["split_progress"] = 0.0
if "split_status_text" not in st.session_state: st.session_state["split_status_text"] = ""
if "split_complete" not in st.session_state: st.session_state["split_complete"] = False
if "split_error" not in st.session_state: st.session_state["split_error"] = None
if "is_splitting" not in st.session_state: st.session_state["is_splitting"] = False

if st.button("📀 Нарезать этот альбом на WAV + MP3-превью", type="primary", disabled=st.session_state["is_splitting"]):
    try:
        st.session_state["is_splitting"] = True
        st.session_state["split_complete"] = False
        st.session_state["split_error"] = None
        
        data, samplerate = sf.read(TEST_FILE)
        total_samples = len(data)
        tracks = parse_cue(CUE_FILE)
        
        threading.Thread(target=background_splitting_task, args=(tracks, samplerate, data, total_samples)).start()
        st.rerun()
    except Exception as e:
        st.error(f"❌ Критическая ошибка при чтении аудиофайла: {e}")
        st.session_state["is_splitting"] = False

if st.session_state["is_splitting"] and not st.session_state["split_complete"]:
    if st.session_state["split_error"]:
        st.error(f"❌ Ошибка при нарезке: {st.session_state['split_error']}")
        st.session_state["is_splitting"] = False
    else:
        st.progress(st.session_state["split_progress"])
        st.caption(st.session_state["split_status_text"])
        time.sleep(0.5)
        st.rerun()

if st.session_state["split_complete"] and st.session_state["is_splitting"]:
    st.success("🎉 Фоновая нарезка успешно завершена!")
    st.session_state["is_splitting"] = False
    st.rerun()

# --- ВСТРОЕННЫЙ АУДИО-ПЛЕЕР С ИНТЕРАКТИВНЫМ РЕЙТИНГОМ ---

st.write("---")
st.subheader("Ваша медиатека (Интерактивные MP3-Превью)")
if os.path.exists(OUTPUT_DIR) and os.path.exists(PREVIEW_DIR):
    wav_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith('.wav')])
    mp3_files = sorted([f for f in os.listdir(PREVIEW_DIR) if f.lower().endswith('.mp3')])
    
    if wav_files and len(wav_files) == len(mp3_files):
        for idx, wav in enumerate(wav_files):
            mp3_path = os.path.join(PREVIEW_DIR, mp3_files[idx])
            track_name = wav.replace('.wav', '')
            
            # --- ОТРИСОВКА ПЛЕЕРА И КОЛОНОК ОЦЕНКИ ДЛЯ КАЖДОГО ТРЕКА ---
            player_col1, player_col2, player_col3 = st.columns([2, 3, 1])
            
            with player_col1:
                st.write(f"🎵 **{track_name}**")
                
            with player_col2:
                st.audio(mp3_path, format="audio/mp3")
                
            with player_col3:
                rating_key = f"rate_{st.session_state['user_id']}_{track_name}"
                selected_rating = st.selectbox(
                    "⭐ Оценка:", 
                    [None, 1, 2, 3, 4, 5], 
                    key=rating_key, 
                    label_visibility="collapsed"
                )
                
                if selected_rating:
                    try:
                        res = requests.post(
                            f"{BACKEND_URL}/track_action",
                            json={
                                "user_id": st.session_state["user_id"],
                                "track_title": track_name,
                                "rating": selected_rating
                            }
                        )
                        if res.status_code == 200:
                            st.toast(f"✅ {res.json()['message']}")
                        else:
                            st.error(f"Ошибка сервера: {res.json().get('detail')}")
                    except Exception as e:
                        st.error(f"Ошибка отправки оценки: {e}")
    else:
        st.warning("🚨 Ошибка: Количество нарезанных WAV и MP3-превью не совпадает в каталоге альбома!")
else:
    st.info("💿 Альбом еще не нарезан. Нажмите кнопку «Нарезать этот альбом» выше, чтобы сгенерировать плееры.")
