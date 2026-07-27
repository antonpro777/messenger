from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Прямое подключение без зависимости от переменных окружения Vercel
def get_db_connection():
    db_url = "postgresql://postgres.ваш_проект:ваш_пароль@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

app = Flask(__name__)
app.secret_key = os.environ.get('SUPABASE_DB_URL', 'super_secret_key_for_dev')

# Функция подключения к Supabase PostgreSQL
def get_db_connection():
    db_url = os.environ.get('SUPABASE_URL')
    if not db_url:
        raise ValueError("Переменная окружения SUPABASE_DB_URL не задана!")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    # Проверяем, авторизован ли пользователь
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Получаем список всех пользователей для сайдбара
    cur.execute("SELECT id, username, status FROM users WHERE id != %s", (current_user['id'],))
    users = cur.fetchall()

    active_recipient_id = request.args.get('to')
    active_recipient = None
    messages = []
    unread_counts = {}

    if active_recipient_id:
        # Получаем данные выбранного собеседника
        cur.execute("SELECT id, username, status FROM users WHERE id = %s", (active_recipient_id,))
        active_recipient = cur.fetchone()

        if active_recipient:
            # Загружаем сообщения между текущим пользователем и собеседником
            cur.execute("""
                SELECT * FROM messages 
                WHERE (sender_id = %s AND recipient_id = %s) 
                   OR (sender_id = %s AND recipient_id = %s)
                ORDER BY id ASC
            """, (current_user['id'], active_recipient_id, active_recipient_id, current_user['id']))
            messages = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        'index.html',
        current_user=current_user,
        users=users,
        active_recipient=active_recipient,
        messages=messages,
        unread_counts=unread_counts
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        
        # Обновляем статус на "В сети" при входе
        if user:
            cur.execute("UPDATE users SET status = 'В сети' WHERE id = %s", (user['id'],))
            conn.commit()

        cur.close()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            # Сохраняем полный словарь профиля в сессию
            session['user'] = {
                'id': user['id'],
                'name': user['name'],
                'username': user['username']
            }
            return redirect(url_for('index'))
        return "Неверный логин или пароль", 401

    return render_template('login.html')

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
                "INSERT INTO users (name, username, password_hash, status) VALUES (%s, %s, %s, 'В сети')",
                (name, username, password_hash)
            )
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Ошибка при регистрации: {e}", 400

    return render_template('register.html')

@app.route('/send', methods=['POST'])
def send_message():
    current_user = session.get('user')
    if not current_user:
        return "Unauthorized", 401

    recipient_id = request.form.get('recipient_id')
    content = request.form.get('content')

    if not recipient_id or not content:
        return "Bad Request", 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (sender_id, recipient_id, content) VALUES (%s, %s, %s)",
        (current_user['id'], recipient_id, content)
    )
    conn.commit()
    cur.close()
    conn.close()

    return "OK", 200

@app.route('/get_messages')
def get_messages():
    current_user = session.get('user')
    if not current_user:
        return jsonify({"error": "Unauthorized"}), 401

    recipient_id = request.args.get('to')
    messages = []

    conn = get_db_connection()
    cur = conn.cursor()

    if recipient_id:
        cur.execute("""
            SELECT * FROM messages 
            WHERE (sender_id = %s AND recipient_id = %s) 
               OR (sender_id = %s AND recipient_id = %s)
            ORDER BY id ASC
        """, (current_user['id'], recipient_id, recipient_id, current_user['id']))
        messages = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "current_user_id": current_user['id'],
        "messages": messages,
        "unread_counts": {}
    })

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    current_user = session.get('user')
    if current_user:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'В сети' WHERE id = %s", (current_user['id'],))
        conn.commit()
        cur.close()
        conn.close()
    return "", 204

@app.route('/logout')
def logout():
    current_user = session.get('user')
    if current_user:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'Не в сети' WHERE id = %s", (current_user['id'],))
        conn.commit()
        cur.close()
        conn.close()
    
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
