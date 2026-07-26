import os
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
# Обязательно задайте надежный секретный ключ для работы сессий Flask (на Vercel возьмется из переменных окружения, либо подставится дефолтный)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-messenger-key')

# Инициализация клиента Supabase (берутся из переменных окружения Vercel или локального .env)
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def ensure_users_table_ready():
    """Проверка и страховка от падений, если структура БД в Supabase еще не до конца настроена"""
    if not supabase:
        return
    try:
        # Проверяем наличие таблицы users, делая легкий запрос
        supabase.table('users').select('id').limit(1).execute()
    except Exception as e:
        print(f"Database check warning: {e}")

# Вызываем проверку при старте
ensure_users_table_ready()


@app.route('/')
def index():
    # Если пользователь не вошел в систему — отправляем на страницу входа
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Здесь ваша логика чата / главной страницы
    return render_template('index.html', username=session['user'])


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            error = 'Пожалуйста, заполните все поля'
        elif not supabase:
            error = 'Ошибка конфигурации базы данных на сервере'
        else:
            try:
                response = supabase.table('users').select('*').eq('username', username).execute()
                users = response.data
                
                if users and 'password_hash' in users[0] and users[0]['password_hash']:
                    if check_password_hash(users[0]['password_hash'], password):
                        session['user'] = username
                        return redirect(url_for('index'))
                
                error = 'Неверное имя пользователя или пароль'
            except Exception as e:
                print(f"Login error: {e}")
                error = 'Ошибка сервера при авторизации. Проверьте структуру базы данных.'
                
    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            error = 'Пожалуйста, заполните все поля'
        elif not supabase:
            error = 'Ошибка конфигурации базы данных на сервере'
        else:
            try:
                # Проверяем, существует ли пользователь
                existing = supabase.table('users').select('*').eq('username', username).execute()
                if existing.data:
                    error = 'Такое имя пользователя уже занято'
                else:
                    # Хэшируем пароль и сохраняем в Supabase
                    hashed_password = generate_password_hash(password)
                    supabase.table('users').insert({
                        'username': username,
                        'password_hash': hashed_password
                    }).execute()
                    
                    # Сразу авторизуем нового пользователя
                    session['user'] = username
                    return redirect(url_for('index'))
            except Exception as e:
                print(f"Registration error: {e}")
                error = 'Ошибка регистрации. Убедитесь, что в таблице users добавлена колонка password_hash.'
                
    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
