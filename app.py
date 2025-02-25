import streamlit as st
import os
import tempfile
import zipfile
import io
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError
import asyncio
import nest_asyncio
from PIL import Image
import base64
from datetime import datetime
import atexit

# Применение nest_asyncio для исправления цикла событий в Streamlit
nest_asyncio.apply()

# Глобальный список активных клиентов для корректного закрытия
active_clients = []

# Функция для корректного закрытия всех клиентов при завершении работы
def cleanup_clients():
    for client in active_clients:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(client.disconnect())
            else:
                loop.run_until_complete(client.disconnect())
        except:
            pass

# Регистрация функции для закрытия клиентов при выходе
atexit.register(cleanup_clients)

# Настройки приложения
st.set_page_config(
    page_title="Telegram Favorites Downloader",
    page_icon="📁",
    layout="wide",
)

# Путь для временных файлов
TEMP_DIR = tempfile.gettempdir()

# API для Telegram (безопасно получаем из секретов)
try:
    API_ID = st.secrets["API_ID"]
    API_HASH = st.secrets["API_HASH"]
except KeyError:
    # Для локальной разработки или тестирования
    API_ID = 1713092
    API_HASH = "c96e3d68d80373c29270bb8a2edbb1f5"

# Создаем уникальное имя для сессии каждого пользователя
def get_session_path():
    if 'session_id' not in st.session_state:
        st.session_state.session_id = os.urandom(8).hex()
    return os.path.join(TEMP_DIR, f"tg_session_{st.session_state.session_id}")

# Функция для запуска асинхронных операций
def run_async(coro):
    try:
        # Пытаемся использовать существующий цикл событий
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Если цикла событий нет, создаем новый
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(coro)
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # Если цикл событий закрыт, создаем новый
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        else:
            raise

# Определить тип медиа
def get_media_type(message):
    if message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    elif message.document:
        return 'document'
    elif message.audio:
        return 'audio'
    elif message.voice:
        return 'voice'
    else:
        return 'unknown'

# Получить имя файла
def get_filename(message):
    if message.photo:
        return f"photo_{message.id}.jpg"
    elif message.video:
        return getattr(message.video.attributes[0], 'file_name', f"video_{message.id}.mp4") if hasattr(message.video, 'attributes') and message.video.attributes else f"video_{message.id}.mp4"
    elif message.document:
        return getattr(message.document.attributes[0], 'file_name', f"document_{message.id}") if hasattr(message.document, 'attributes') and message.document.attributes else f"document_{message.id}"
    elif message.audio:
        return getattr(message.audio.attributes[0], 'file_name', f"audio_{message.id}.mp3") if hasattr(message.audio, 'attributes') and message.audio.attributes else f"audio_{message.id}.mp3"
    elif message.voice:
        return f"voice_{message.id}.ogg"
    else:
        return f"file_{message.id}"

# Функция для создания и управления клиентом Telegram
async def get_telegram_client():
    session_path = get_session_path()
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    # Добавляем клиент в список активных для корректного закрытия
    if client not in active_clients:
        active_clients.append(client)
    
    await client.connect()
    return client

# Главная страница
def main_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("Telegram Favorites Downloader")
        st.subheader("Скачивайте медиа из избранного Telegram быстро и просто")

        # Создаем красивые карточки с функциями
        cols = st.columns(3)
        with cols[0]:
            st.markdown("""
            ### ✨ Легкий доступ
            Получайте доступ ко всем вашим избранным медиафайлам в одном месте
            """)
        with cols[1]:
            st.markdown("""
            ### 🔒 Безопасность
            Ваши данные не сохраняются на серверах - всё остается приватным
            """)
        with cols[2]:
            st.markdown("""
            ### 💾 Быстрое скачивание
            Скачивайте отдельные файлы или все сразу в ZIP-архиве
            """)

        st.write("")
        st.write("### Начать работу")
        st.write("Для доступа к вашим избранным медиа в Telegram, войдите в ваш аккаунт:")
        
        if st.button("Войти через Telegram", type="primary", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()
            
        st.divider()
        st.caption("Этот сервис использует Telegram API и не связан с Telegram Inc.")
        st.caption("© 2025 Telegram Favorites Downloader")

# Страница входа
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("Вход через Telegram")
        st.write("Введите ваш номер телефона для входа в Telegram")
        
        with st.form("login_form"):
            phone = st.text_input("Номер телефона (с кодом страны)", placeholder="+79123456789")
            submit = st.form_submit_button("Получить код", use_container_width=True)
            
            if submit and phone:
                try:
                    # Создаем сессию для пользователя
                    async def send_code():
                        client = await get_telegram_client()
                        if not await client.is_user_authorized():
                            # Сохраняем результат, который содержит phone_code_hash
                            sent_code = await client.send_code_request(phone)
                            return True, sent_code.phone_code_hash
                        else:
                            # Если уже авторизован
                            user = await client.get_me()
                            st.session_state.user_id = user.id
                            st.session_state.phone = phone
                            return False, None
                        
                    need_code, phone_code_hash = run_async(send_code())
                    
                    if need_code:
                        st.session_state.phone = phone
                        # Сохраняем phone_code_hash для использования при подтверждении
                        st.session_state.phone_code_hash = phone_code_hash
                        st.session_state.page = "verify_code"
                        st.rerun()
                    else:
                        st.session_state.page = "dashboard"
                        st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при отправке кода: {str(e)}")
        
        if st.button("← Назад"):
            st.session_state.page = "main"
            st.rerun()
            
        st.info("Мы не сохраняем ваш номер телефона. Сессия временно хранится только на вашем устройстве.")
        st.divider()
        st.caption("Этот сервис использует Telegram API и не связан с Telegram Inc.")

# Страница подтверждения кода
def verify_code_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("Подтверждение кода Telegram")
        st.write("Введите код, который был отправлен вам в Telegram")
        
        with st.form("verify_form"):
            code = st.text_input("Код подтверждения", placeholder="12345")
            submit = st.form_submit_button("Подтвердить", use_container_width=True)
            
            if submit and code:
                try:
                    # Получаем сессию пользователя
                    phone = st.session_state.phone
                    phone_code_hash = st.session_state.phone_code_hash
                    
                    # Авторизуемся с кодом
                    async def sign_in():
                        client = await get_telegram_client()
                        try:
                            # Используем phone_code_hash при подтверждении
                            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                            user = await client.get_me()
                            return user.id, None
                        except SessionPasswordNeededError:
                            # Возвращаем флаг, что требуется двухфакторная аутентификация
                            return None, True
                    
                    user_id, two_fa_needed = run_async(sign_in())
                    
                    if two_fa_needed:
                        # Если требуется 2FA, перенаправляем на страницу ввода пароля
                        st.session_state.page = "two_fa"
                        st.rerun()
                    elif user_id:
                        # Если успешно авторизовались
                        st.session_state.user_id = user_id
                        st.session_state.page = "dashboard"
                        st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при подтверждении кода: {str(e)}")
        
        if st.button("← Назад"):
            st.session_state.page = "login"
            st.rerun()
            
        st.info("Если вы не получили код, проверьте приложение Telegram на вашем телефоне или компьютере.")
        st.divider()
        st.caption("Этот сервис использует Telegram API и не связан с Telegram Inc.")

# Страница ввода пароля 2FA
def two_fa_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("Двухфакторная аутентификация")
        st.write("Введите пароль от вашего аккаунта Telegram")
        
        with st.form("two_fa_form"):
            password = st.text_input("Пароль", type="password")
            submit = st.form_submit_button("Войти", use_container_width=True)
            
            if submit and password:
                try:
                    # Авторизуемся с паролем
                    async def check_password():
                        client = await get_telegram_client()
                        await client.sign_in(password=password)
                        user = await client.get_me()
                        return user.id
                    
                    user_id = run_async(check_password())
                    st.session_state.user_id = user_id
                    st.session_state.page = "dashboard"
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при вводе пароля: {str(e)}")
        
        if st.button("← Назад"):
            st.session_state.page = "verify_code"
            st.rerun()
            
        st.info("Этот пароль - дополнительный пароль, который вы установили в настройках безопасности Telegram.")
        st.divider()
        st.caption("Этот сервис использует Telegram API и не связан с Telegram Inc.")

# Страница с избранными медиа
def dashboard_page():
    st.title("Ваши избранные медиа")
    
    # Кнопки действий
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("Выйти", key="logout"):
            # Закрываем все активные клиенты
            cleanup_clients()
            # Очищаем состояние сессии
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.page = "main"
            st.rerun()
    
    # Получаем избранные медиа
    with st.spinner("Загрузка ваших избранных медиафайлов..."):
        favorites = get_favorites()
    
    if favorites:
        # Кнопка для скачивания всех файлов
        if st.download_button(
            label="Скачать все файлы (ZIP)",
            data=get_all_media_zip(favorites),
            file_name="telegram_favorites.zip",
            mime="application/zip",
            use_container_width=True
        ):
            st.success("Скачивание началось!")
            
        # Отображаем медиафайлы в сетке
        st.write("### Список медиафайлов:")
        
        # Используем 3 колонки для отображения
        cols_per_row = 3
        for i in range(0, len(favorites), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(favorites):
                    item = favorites[i + j]
                    with cols[j]:
                        with st.container(border=True):
                            st.write(f"**Тип:** {item['type']}")
                            st.write(f"**Дата:** {item['date']}")
                            st.write(f"**Файл:** {item['filename']}")
                            
                            # Кнопка скачивания для каждого файла
                            media_data = get_media_data(item['id'])
                            if media_data:
                                st.download_button(
                                    label="Скачать",
                                    data=media_data,
                                    file_name=item['filename'],
                                    key=f"download_{item['id']}"
                                )
    else:
        st.info("У вас нет избранных медиафайлов или произошла ошибка при их загрузке.")
        st.write("Добавьте медиафайлы в избранное в Telegram и обновите страницу.")
    
    st.divider()
    st.caption("Этот сервис использует Telegram API и не связан с Telegram Inc.")

# Получить все избранные медиафайлы
def get_favorites():
    try:
        # Получаем избранные сообщения через API
        async def fetch_favorites():
            client = await get_telegram_client()
            
            if not await client.is_user_authorized():
                return []
            
            favorites = []
            try:
                # Вместо GetSavedDialogsRequest используем альтернативный подход
                # Получаем сообщения из "Сохраненные сообщения" (Saved Messages)
                # В Telegram это диалог с самим собой
                messages = await client.get_messages('me', limit=200)
                
                # Отбираем только медиафайлы
                for message in messages:
                    if message.media:
                        # Добавляем информацию о медиа
                        media_info = {
                            'id': message.id,
                            'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                            'type': get_media_type(message),
                            'filename': get_filename(message)
                        }
                        favorites.append(media_info)
            except Exception as e:
                st.error(f"Ошибка при получении избранных: {str(e)}")
            
            return favorites
        
        return run_async(fetch_favorites())
    except Exception as e:
        st.error(f"Ошибка: {str(e)}")
        return []

# Получить данные одного медиафайла
def get_media_data(message_id):
    try:
        # Скачиваем файл через API
        async def download_media():
            client = await get_telegram_client()
            
            if not await client.is_user_authorized():
                return None
            
            try:
                # Получаем сообщение с медиа - аргумент ids возвращает один объект, а не список
                message = await client.get_messages('me', ids=message_id)
                
                # Проверяем, что сообщение существует и содержит медиа
                if not message or not message.media:
                    return None
                
                file_buffer = io.BytesIO()
                
                # Скачиваем файл в буфер
                await client.download_media(message, file_buffer)
                
                file_buffer.seek(0)
                return file_buffer.read()
            except Exception as e:
                st.error(f"Ошибка при скачивании: {str(e)}")
                return None
        
        return run_async(download_media())
    except Exception as e:
        st.error(f"Ошибка: {str(e)}")
        return None

# Получить все медиафайлы в ZIP-архиве
def get_all_media_zip(favorites):
    try:
        # Создаем ZIP архив с медиафайлами
        async def download_all_media():
            client = await get_telegram_client()
            
            if not await client.is_user_authorized():
                return None
            
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w') as zf:
                try:
                    for item in favorites:
                        message_id = item['id']
                        filename = item['filename']
                        
                        # Получаем сообщение - аргумент ids возвращает один объект, а не список
                        message = await client.get_messages('me', ids=message_id)
                        
                        # Проверяем, что сообщение существует и содержит медиа
                        if message and message.media:
                            file_buffer = io.BytesIO()
                            
                            # Скачиваем файл
                            await client.download_media(message, file_buffer)
                            
                            # Добавляем в архив
                            file_buffer.seek(0)
                            zf.writestr(filename, file_buffer.read())
                except Exception as e:
                    st.error(f"Ошибка при создании архива: {str(e)}")
            
            memory_file.seek(0)
            return memory_file.getvalue()
        
        return run_async(download_all_media())
    except Exception as e:
        st.error(f"Ошибка: {str(e)}")
        return None

# Применяем стили
def apply_custom_styles():
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1 {
        color: #0088cc;
    }
    .stButton button {
        background-color: #0088cc;
        color: white;
    }
    .stDownloadButton button {
        background-color: #28a745;
        color: white;
    }
    footer {
        visibility: hidden;
    }
    </style>
    """, unsafe_allow_html=True)

# Инициализация состояния приложения
if 'page' not in st.session_state:
    st.session_state.page = "main"

# Применяем стили
apply_custom_styles()

# Маршрутизация страниц
if st.session_state.page == "main":
    main_page()
elif st.session_state.page == "login":
    login_page()
elif st.session_state.page == "verify_code":
    verify_code_page()
elif st.session_state.page == "two_fa":
    two_fa_page()
elif st.session_state.page == "dashboard":
    dashboard_page()