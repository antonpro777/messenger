from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import re
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_key_for_dev')

# Инициализация клиента Supabase (убедитесь, что переменные окружения SUPABASE_URL и SUPABASE_KEY заданы, либо пропишите их напрямую)
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'ВАШ_SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'ВАШ_SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

    cur.execute("SELECT balance, name, bio, is_admin, avatar_url FROM users WHERE id = %s", (current_user['id'],))
    db_user = cur.fetchone()
    if db_user:
        current_user['balance'] = db_user['balance']
        current_user['name'] = db_user['name']
        current_user['bio'] = db_user['bio']
        current_user['is_admin'] = db_user['is_admin']
        current_user['avatar_url'] = db_user.get('avatar_url', '')

    cur.execute("UPDATE users SET status = 'В сети', last_active = CURRENT_TIMESTAMP WHERE id = %s", (current_user['id'],))
    conn.commit()

    cur.execute("""
        UPDATE users 
        SET status = 'Не в сети' 
        WHERE status = 'В сети' AND last_active < NOW() - INTERVAL '15 seconds'
    """)
    conn.commit()

    cur.execute("""
        SELECT DISTINCT u.id, u.username, u.name, u.status, u.is_admin, u.avatar_url 
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
        cur.execute("SELECT id, username, name, status, bio, is_admin, avatar_url FROM users WHERE id = %s", (active_recipient_id,))
        active_recipient = cur.fetchone()

        if active_recipient:
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

@app.route('/unread_count', methods=['GET'])
def unread_count():
    current_user = session.get('user')
    if not current_user:
        return jsonify({'count': 0})
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM messages 
        WHERE recipient_id = %s AND is_read = FALSE AND is_deleted = FALSE
    """, (current_user['id'],))
    row = cur.fetchone()
    count = row['count'] if row and 'count' in row else 0
    cur.close()
    conn.close()
    
    return jsonify({'count': count})

@app.route('/get_new_messages')
def get_new_messages():
    current_user = session.get('user')
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    recipient_id = request.args.get('recipient_id', type=int)
    last_id = request.args.get('last_id', default=0, type=int)
    current_user_id = current_user['id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, sender_id, recipient_id, content, is_deleted, is_read, file_url, file_type 
        FROM messages 
        WHERE id > %s AND ((sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s))
        ORDER BY id ASC
    """, (last_id, current_user_id, recipient_id, recipient_id, current_user_id))
    new_messages = cur.fetchall()
    cur.close()
    conn.close()
    
    messages_data = []
    for msg in new_messages:
        messages_data.append({
            'id': msg['id'],
            'sender_id': msg['sender_id'],
            'recipient_id': msg['recipient_id'],
            'content': msg['content'],
            'is_deleted': msg['is_deleted'],
            'is_read': msg['is_read'],
            'file_url': msg['file_url'],
            'file_type': msg['file_type']
        })
        
    return jsonify({'messages': messages_data})

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/mark_read', methods=['POST'])
def mark_read():
    current_user = session.get('user')
    if not current_user:
        return jsonify({'success': False}), 401
    
    data = request.get_json()
    sender_id = data.get('sender_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE messages 
        SET is_read = TRUE 
        WHERE sender_id = %s AND recipient_id = %s AND is_read = FALSE
    """, (sender_id, current_user['id']))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/delete_message', methods=['POST'])
def delete_message():
    current_user = session.get('user')
    if not current_user:
        return jsonify({'success': False}), 401
        
    data = request.get_json()
    msg_id = data.get('msg_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE messages 
        SET is_deleted = TRUE 
        WHERE id = %s AND sender_id = %s
    """, (msg_id, current_user['id']))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/transfer_gun', methods=['POST'])
def transfer_gun():
    current_user = session.get('user')
    if not current_user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json()
    recipient_id = data.get('recipient_id')
    amount = int(data.get('amount', 0))

    if amount <= 0 or not recipient_id:
        return jsonify({"success": False, "error": "Неверное количество GUN"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT balance, is_admin FROM users WHERE id = %s", (current_user['id'],))
    sender_row = cur.fetchone()
    if not sender_row or sender_row['balance'] < amount:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Недостаточно GUN на балансе!"}), 400

    cur.execute("SELECT id, is_admin FROM users WHERE id = %s", (recipient_id,))
    recipient_row = cur.fetchone()
    if not recipient_row:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Получатель не найден"}), 404

    tax_amount = int(amount * 0.5)
    net_amount = amount - tax_amount

    cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, current_user['id']))

    actual_recipient_gain = amount if recipient_row['is_admin'] else net_amount
    cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (actual_recipient_gain, recipient_id))

    if not recipient_row['is_admin'] and tax_amount > 0:
        cur.execute("SELECT id FROM users WHERE is_admin = TRUE LIMIT 1")
        admin_row = cur.fetchone()
        if admin_row:
            cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (tax_amount, admin_row['id']))

    transfer_text = f"🎁 Подарил(а) {amount} GUN 🪙 (Комиссия системы: {tax_amount})" if not recipient_row['is_admin'] else f"🎁 Подарил(а) {amount} GUN 🪙"
    cur.execute(
        "INSERT INTO messages (sender_id, recipient_id, content) VALUES (%s, %s, %s)",
        (current_user['id'], recipient_id, transfer_text)
    )

    conn.commit()

    cur.execute("SELECT balance FROM users WHERE id = %s", (current_user['id'],))
    new_balance = cur.fetchone()['balance']

    cur.close()
    conn.close()

    session['user']['balance'] = new_balance
    return jsonify({"success": True, "new_balance": new_balance})

@app.route('/admin/delete_user', methods=['POST'])
def admin_delete_user():
    current_user = session.get('user')
    if not current_user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT is_admin FROM users WHERE id = %s", (current_user['id'],))
    user_row = cur.fetchone()
    if not user_row or not user_row['is_admin']:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Доступ запрещен"}), 403

    data = request.get_json()
    target_user_id = data.get('user_id')

    if not target_user_id:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Не указан ID пользователя"}), 400

    cur.execute("DELETE FROM users WHERE id = %s", (target_user_id,))
    conn.commit()

    cur.close()
    conn.close()
    return jsonify({"success": True})

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
            SELECT id, username, name, status, bio, is_admin, avatar_url FROM users 
            WHERE (username ILIKE %s OR name ILIKE %s) AND id != %s
        """, (f"%{query}%", f"%{query}%", current_user['id']))
        users = cur.fetchall()
        cur.close()
        conn.close()

    return render_template('search.html', current_user=current_user, users=users, query=query)

SHOP_ITEMS = [
    {"emoji": "🍎", "price": 30}, {"emoji": "🍌", "price": 50}, {"emoji": "🍕", "price": 60},
    {"emoji": "🍔", "price": 70}, {"emoji": "🍩", "price": 80}, {"emoji": "🍪", "price": 90},
    {"emoji": "🍫", "price": 100}, {"emoji": "🍬", "price": 120}, {"emoji": "👑", "price": 150},
    {"emoji": "💎", "price": 200}, {"emoji": "💍", "price": 250}, {"emoji": "🚀", "price": 300},
    {"emoji": "🏎️", "price": 350}, {"emoji": "🎸", "price": 400}, {"emoji": "🏆", "price": 500},
    {"emoji": "🎯", "price": 555}, {"emoji": "🎲", "price": 600}, {"emoji": "🔥", "price": 666},
    {"emoji": "⚡", "price": 700}, {"emoji": "⭐", "price": 777}, {"emoji": "🔮", "price": 800},
    {"emoji": "🧿", "price": 888}, {"emoji": "💡", "price": 900}, {"emoji": "💻", "price": 1000},
    {"emoji": "📱", "price": 1100}, {"emoji": "⌚", "price": 1200}, {"emoji": "🛸", "price": 1337},
    {"emoji": "🛡️", "price": 1488}, {"emoji": "⚔️", "price": 1555}, {"emoji": "🧪", "price": 1600},
    {"emoji": "🧬", "price": 1700}, {"emoji": "🗿", "price": 1800}
]

@app.route('/shop')
def shop():
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT balance FROM users WHERE id = %s", (current_user['id'],))
    db_user = cur.fetchone()
    if db_user:
        current_user['balance'] = db_user['balance']

    cur.execute("SELECT item_emoji FROM inventory WHERE user_id = %s", (current_user['id'],))
    owned_items = [row['item_emoji'] for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template('shop.html', current_user=current_user, items=SHOP_ITEMS, owned_items=owned_items)

@app.route('/buy_item', methods=['POST'])
def buy_item():
    current_user = session.get('user')
    if not current_user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json()
    item_emoji = data.get('emoji')
    item_price = data.get('price')

    target_item = next((item for item in SHOP_ITEMS if item['emoji'] == item_emoji and item['price'] == item_price), None)
    if not target_item:
        return jsonify({"success": False, "error": "Неверный предмет"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT balance FROM users WHERE id = %s", (current_user['id'],))
    user_row = cur.fetchone()
    current_balance = user_row['balance'] if user_row else 0

    if current_balance < item_price:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Недостаточно GUN!"}), 400

    cur.execute("SELECT * FROM inventory WHERE user_id = %s AND item_emoji = %s", (current_user['id'], item_emoji))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Предмет уже куплен!"}), 400

    cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (item_price, current_user['id']))
    cur.execute("INSERT INTO inventory (user_id, item_emoji, item_price) VALUES (%s, %s, %s)", (current_user['id'], item_emoji, item_price))
    conn.commit()

    cur.execute("SELECT balance FROM users WHERE id = %s", (current_user['id'],))
    new_balance = cur.fetchone()['balance']

    cur.close()
    conn.close()

    session['user']['balance'] = new_balance
    return jsonify({"success": True, "new_balance": new_balance})

@app.route('/profile/<int:user_id>')
def view_profile(user_id):
    current_user = session.get('user')
    if not current_user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, name, status, bio, is_admin, avatar_url FROM users WHERE id = %s", (user_id,))
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
        avatar_file = request.files.get('avatar')

        avatar_url = current_user.get('avatar_url', '')

        if avatar_file and avatar_file.filename != '':
            filename = secure_filename(avatar_file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'png'
            unique_filename = f"avatar_{current_user['id']}_{uuid.uuid4()}.{file_ext}"
            
            file_bytes = avatar_file.read()
            try:
                supabase.storage.from_('uploads').upload(
                    path=unique_filename,
                    file=file_bytes,
                    file_options={"content-type": avatar_file.content_type}
                )
                avatar_url = supabase.storage.from_('uploads').get_public_url(unique_filename)
            except Exception as e:
                print(f"Ошибка загрузки аватарки в Supabase: {e}")

            cur.execute("UPDATE users SET name = %s, bio = %s, avatar_url = %s WHERE id = %s", 
                        (new_name, new_bio, avatar_url, current_user['id']))
            session['user']['avatar_url'] = avatar_url
        else:
            cur.execute("UPDATE users SET name = %s, bio = %s WHERE id = %s", 
                        (new_name, new_bio, current_user['id']))
            
        conn.commit()
        session['user']['name'] = new_name
        current_user['bio'] = new_bio

    cur.execute("SELECT name, username, bio, balance, is_admin, avatar_url FROM users WHERE id = %s", (current_user['id'],))
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
        
        if user and check_password_hash(user['password_hash'], password):
            cur.execute("UPDATE users SET status = 'В сети', last_active = CURRENT_TIMESTAMP WHERE id = %s", (user['id'],))
            conn.commit()
            
            session['user'] = {
                'id': user['id'],
                'name': user['name'],
                'username': user['username'],
                'balance': user.get('balance', 0),
                'is_admin': user.get('is_admin', False),
                'avatar_url': user.get('avatar_url', '')
            }
            cur.close()
            conn.close()
            return redirect(url_for('index'))
            
        cur.close()
        conn.close()
        return "Неверный логин или пароль", 401

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if 'terms_agree' not in request.form:
            return "Ошибка: Вы должны согласиться с Политикой конфиденциальности и Условиями использования.", 400

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
                "INSERT INTO users (name, username, password_hash, status, balance, bio, last_active, is_admin, avatar_url) VALUES (%s, %s, %s, 'В сети', 0, '', CURRENT_TIMESTAMP, FALSE, '')",
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
    content = request.form.get('content', '')
    file = request.files.get('file')

    if not recipient_id or (not content and not file):
        return "Bad Request", 400

    file_url = ''
    file_type = 'text'

    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        unique_filename = f"msg_{uuid.uuid4()}_{filename}"
        
        file_bytes = file.read()
        try:
            supabase.storage.from_('uploads').upload(
                path=unique_filename,
                file=file_bytes,
                file_options={"content-type": file.content_type}
            )
            file_url = supabase.storage.from_('uploads').get_public_url(unique_filename)
        except Exception as e:
            print(f"Ошибка загрузки файла в Supabase: {e}")

        if file_ext in ['png', 'jpg', 'jpeg', 'gif']:
            file_type = 'image'
        else:
            file_type = 'document'

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM blocks WHERE (blocker_id = %s AND blocked_id = %s) OR (blocker_id = %s AND blocked_id = %s)", 
                (current_user['id'], recipient_id, recipient_id, current_user['id']))
    if cur.fetchone():
        cur.close()
        conn.close()
        return "Blocked", 403

    cur.execute(
        "INSERT INTO messages (sender_id, recipient_id, content, file_url, file_type) VALUES (%s, %s, %s, %s, %s)",
        (current_user['id'], recipient_id, content, file_url, file_type)
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
