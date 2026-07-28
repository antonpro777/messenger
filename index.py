from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_key_for_dev')

def get_db_connection():
    db_url = "postgresql://postgres.prelemswcdgnxyajajbs:292997746Raa@aws-0-eu-west-3.pooler.supabase.com:6543/postgres"
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Актуализируем баланс и данные текущего пользователя
    cur.execute("SELECT balance, name, bio FROM users WHERE id = %s", (current_user['id'],))
    db_user = cur.fetchone()
    if db_user:
        current_user['balance'] = db_user['balance']
        current_user['name'] = db_user['name']
        current_user['bio'] = db_user['bio']

    # Обновляем свой собственный статус на 'В сети' при открытии/обновлении главной страницы
    cur.execute("UPDATE users SET status = 'В сети', last_active = CURRENT_TIMESTAMP WHERE id = %s", (current_user['id'],))
    conn.commit()

    # Если последняя активность была больше 15 секунд назад, автоматически меняем статус пользователя на 'Не в сети' в базе
    cur.execute("""
        UPDATE users 
        SET status = 'Не в сети' 
        WHERE status = 'В сети' AND last_active < NOW() - INTERVAL '15 seconds'
    """)
    conn.commit()

    # Список чатов: только те, с кем есть переписка и кто не в блоке
    cur.execute("""
        SELECT DISTINCT u.id, u.username, u.name, u.status 
        FROM users u
        JOIN messages m ON (u.id = m.sender_id OR u.id = m.recipient_id)
        WHERE (m.sender_id = %s OR m.recipient_id = %s) AND u.id != %s
          AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = %s)
          AND %s NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = u.id)
    """, (current_user['id'], current_user['id'], current_user['id'], current_user['id'], current_user['id']))
    users = cur.fetchall()

    active_recipient_id = request.args.get('to')
    active_recipient = None
    messages = []
    is_blocked = False

    if active_recipient_id:
        cur.execute("SELECT id, username, name, status, bio FROM users WHERE id = %s", (active_recipient_id,))
        active_recipient = cur.fetchone()

        if active_recipient:
            # Проверяем, заблокирован ли пользователь
            cur.execute("SELECT * FROM blocks WHERE blocker_id = %s AND blocked_id = %s", (current_user['id'], active_recipient_id))
            if cur.fetchone():
                is_blocked = True

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
        is_blocked=is_blocked
    )

@app.route('/ping', methods=['POST'])
def ping():
    current_user = session.get('user')
    if not current_user:
        return "Unauthorized", 401

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP, status = 'В сети' WHERE id = %s", (current_user['id'],))
    conn.commit()
    cur.close()
    conn.close()
    return "OK", 200

@app.route('/offline', methods=['POST'])
def go_offline():
    current_user = session.get('user')
    if not current_user:
        return "Unauthorized", 401

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET status = 'Не в сети' WHERE id = %s", (current_user['id'],))
    conn.commit()
    cur.close()
    conn.close()
    return "OK", 200

@app.route('/search')
def search_users():
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    query = request.args.get('q', '').strip()
    users = []

    if query:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, username, name, status, bio FROM users 
            WHERE (username ILIKE %s OR name ILIKE %s) AND id != %s
        """, (f"%{query}%", f"%{query}%", current_user['id']))
        users = cur.fetchall()
        cur.close()
        conn.close()

    return render_template('search.html', current_user=current_user, users=users, query=query)

@app.route('/profile/<int:user_id>')
def view_profile(user_id):
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, name, status, bio FROM users WHERE id = %s", (user_id,))
    profile_user = cur.fetchone()

    cur.execute("SELECT * FROM blocks WHERE blocker_id = %s AND blocked_id = %s", (current_user['id'], user_id))
    is_blocked = cur.fetchone() is not None

    cur.close()
    conn.close()

    if not profile_user:
        return "Пользователь не найден", 404

    return render_template('profile.html', current_user=current_user, profile_user=profile_user, is_blocked=is_blocked)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_bio = request.form.get('bio')

        cur.execute("UPDATE users SET name = %s, bio = %s WHERE id = %s", (new_name, new_bio, current_user['id']))
        conn.commit()
        session['user']['name'] = new_name
        current_user['bio'] = new_bio

    cur.execute("SELECT name, username, bio, balance FROM users WHERE id = %s", (current_user['id'],))
    user_data = cur.fetchone()
    cur.close()
    conn.close()

    return render_template('settings.html', current_user=current_user, user_data=user_data)

@app.route('/block/<int:user_id>', methods=['POST'])
def toggle_block(user_id):
    current_user = session.get('user')
    if not current_user:
        return "Unauthorized", 401

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM blocks WHERE blocker_id = %s AND blocked_id = %s", (current_user['id'], user_id))
    if cur.fetchone():
        cur.execute("DELETE FROM blocks WHERE blocker_id = %s AND blocked_id = %s", (current_user['id'], user_id))
    else:
        cur.execute("INSERT INTO blocks (blocker_id, blocked_id) VALUES (%s, %s)", (current_user['id'], user_id))
    
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('view_profile', user_id=user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        
        if user:
            cur.execute("UPDATE users SET status = 'В сети', last_active = CURRENT_TIMESTAMP WHERE id = %s", (user['id'],))
            conn.commit()

        cur.close()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user'] = {
                'id': user['id'],
                'name': user['name'],
                'username': user['username'],
                'balance': user.get('balance', 0)
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

        if not re.match("^[A-Za-z0-9_]+$", username):
            return "Ошибка: Юзернейм должен содержать только латинские буквы, цифры и знак подчеркивания.", 400

        password_hash = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, username, password_hash, status, balance, bio, last_active) VALUES (%s, %s, %s, 'В сети', 0, '', CURRENT_TIMESTAMP)",
                (name, username, password_hash)
            )
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Ошибка при регистрации (возможно, такой юзернейм уже занят): {e}", 400

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
    
    # Проверка на блокировку
    cur.execute("SELECT * FROM blocks WHERE (blocker_id = %s AND blocked_id = %s) OR (blocker_id = %s AND blocked_id = %s)", 
                (current_user['id'], recipient_id, recipient_id, current_user['id']))
    if cur.fetchone():
        cur.close()
        conn.close()
        return "Blocked", 403

    cur.execute(
        "INSERT INTO messages (sender_id, recipient_id, content) VALUES (%s, %s, %s)",
        (current_user['id'], recipient_id, content)
    )
    conn.commit()
    cur.close()
    conn.close()

    return "OK", 200

@app.route('/earn_gon', methods=['POST'])
def earn_gon():
    current_user = session.get('user')
    if not current_user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    score = data.get('score', 0)
    earned_gon = score // 10

    if earned_gon > 0:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (earned_gon, current_user['id']))
        conn.commit()
        
        cur.execute("SELECT balance FROM users WHERE id = %s", (current_user['id'],))
        updated_user = cur.fetchone()
        
        cur.close()
        conn.close()

        session['user']['balance'] = updated_user['balance']
        return jsonify({"success": True, "earned": earned_gon, "new_balance": updated_user['balance']})

    return jsonify({"success": True, "earned": 0})

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
