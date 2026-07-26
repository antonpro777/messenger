from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_key_for_dev')

# Функция подключения к базе данных Supabase (PostgreSQL)
def get_db_connection():
    conn = psycopg2.connect(
        os.environ.get('SUPABASE_DB_URL'), # Убедитесь, что переменная окружения задана в Vercel
        cursor_factory=RealDictCursor
    )
    return conn

@app.route('/')
def index():
    # Получаем данные пользователя из сессии
    current_user = session.get('user')
    
    messages = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Загружаем сообщения (пример)
        cur.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 50;")
        messages = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

    return render_template('index.html', current_user=current_user, messages=messages)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        password = request.form.get('password')
        
        password_hash = generate_password_hash(password)
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, username, password_hash) VALUES (%s, %s, %s)",
                (name, username, password_hash)
            )
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Ошибка при регистрации: {e}"
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            # Сохраняем данные пользователя в сессию для раздельного вывода имени и ника
            session['user'] = {
                'id': user['id'],
                'name': user['name'],
                'username': user['username']
            }
            return redirect(url_for('index'))
        return "Неверный логин или пароль"
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
