import os
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
# Задайте секретный ключ для сессий (на Vercel подтянется из переменных окружения, либо дефолтный для локальной разработки)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-messenger-key-change-it')

# Подключение к Supabase (убедитесь, что переменные заданы в окружении или пропишите ключи напрямую)
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'ВАШ_SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'ВАШ_SUPABASE_ANON_KEY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    # Проверяем, есть ли пользователь в сессии, и достаем его имя
    username = session.get('user') # или как вы сохраняете его при логине
    
    # Получаем сообщения из базы...
    messages = [...] # ваш текущий код загрузки сообщений
    
    return render_template('index.html', username=username, messages=messages)
    
    # Загружаем сообщения (если таблица messages существует)
    messages = []
    try:
        response = supabase.table('messages').select('*').order('created_at', desc=False).execute()
        if response.data:
            messages = response.data
    except Exception as e:
        print(f"Ошибка загрузки сообщений: {e}")
        
    return render_template('index.html', username=session['user'], messages=messages)

@app.route('/send', methods=['POST'])
def send_message():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    text = request.form.get('text', '').strip()
    if text:
        try:
            supabase.table('messages').insert({
                'username': session['user'],
                'text': text
            }).execute()
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")
            
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Если уже авторизован — кидаем на главную
    if 'user' in session:
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            error = 'Пожалуйста, заполните все поля'
        else:
            try:
                response = supabase.table('users').select('*').eq('username', username).execute()
                users = response.data
                
                # Проверяем наличие пользователя и совпадение хэша пароля
                if users and 'password_hash' in users[0] and check_password_hash(users[0]['password_hash'], password):
                    session['user'] = username
                    return redirect(url_for('index'))
                else:
                    error = 'Неверное имя пользователя или пароль'
            except Exception as e:
                print(f"Ошибка входа: {e}")
                error = 'Ошибка подключения к базе данных'
                
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Если уже авторизован — кидаем на главную
    if 'user' in session:
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            error = 'Пожалуйста, заполните все поля'
        else:
            try:
                # Проверяем, занято ли имя
                existing = supabase.table('users').select('*').eq('username', username).execute()
                if existing.data:
                    error = 'Такое имя пользователя уже занято'
                else:
                    # Создаем хэш пароля и сохраняем в базу
                    hashed_password = generate_password_hash(password)
                    supabase.table('users').insert({
                        'username': username,
                        'password_hash': hashed_password
                    }).execute()
                    
                    # Сразу логиним пользователя
                    session['user'] = username
                    return redirect(url_for('index'))
            except Exception as e:
                print(f"Ошибка регистрации: {e}")
                error = 'Ошибка при регистрации. Проверьте структуру базы данных.'
                
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
