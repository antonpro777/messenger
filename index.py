import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-it')

# Подключение к Supabase (ключи берутся из переменных окружения Vercel)
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.before_request
def load_user():
    if 'user_id' in session:
        class User:
            id = session['user_id']
            username = session['username']
            status = session.get('status', 'В сети')
        app.config['CURRENT_USER'] = User()
    else:
        app.config['CURRENT_USER'] = None

@app.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    current_user = app.config.get('CURRENT_USER')
    
    # Получаем список всех пользователей из базы Supabase
    users = []
    if supabase:
        try:
            response = supabase.table('users').select('*').execute()
            users = response.data
        except Exception as e:
            print("Ошибка загрузки пользователей:", e)

    return render_template('index.html', current_user=current_user, users=users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if username and supabase:
            try:
                # Проверяем, есть ли пользователь в базе Supabase
                existing = supabase.table('users').select('*').eq('username', username).execute()
                
                if existing.data:
                    user_data = existing.data[0]
                else:
                    # Если нет — создаем нового пользователя
                    new_user = supabase.table('users').insert({'username': username, 'status': 'В сети'}).execute()
                    user_data = new_user.data[0]
                
                session['user_id'] = user_data['id']
                session['username'] = user_data['username']
                session['status'] = user_data.get('status', 'В сети')
                return redirect(url_for('index'))
            except Exception as e:
                error = f"Ошибка базы данных: {e}"
                
    return f'''
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Вход в мессенджер</title>
        <style>
            body {{ background: #121212; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .login-box {{ background: #1e1e1e; padding: 30px; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 300px; }}
            input {{ width: 100%; padding: 10px; margin: 10px 0 20px; background: #333; border: 1px solid #444; color: #fff; border-radius: 4px; box-sizing: border-box; }}
            button {{ width: 100%; padding: 10px; background: #0088cc; color: white; border: none; border-radius: 4px; cursor: pointer; }}
            button:hover {{ background: #006699; }}
            .error {{ color: #ff4d4d; font-size: 13px; margin-bottom: 10px; }}
        </style>
    </head>
    <body>
        <div class="login-box">
            <h3>Вход в мессенджер</h3>
            {f'<div class="error">{error}</div>' if error else ''}
            <form method="POST">
                <label>Ваше имя:</label>
                <input type="text" name="username" required autocomplete="off">
                <button type="submit">Войти</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
