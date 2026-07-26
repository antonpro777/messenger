from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from supabase import create_client, Client
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_messenger_key')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

def get_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None

def fetch_messages_between(db, user1_id, user2_id):
    try:
        res1 = db.table('messages').select('*').eq('sender_id', user1_id).eq('recipient_id', user2_id).execute()
        res2 = db.table('messages').select('*').eq('sender_id', user2_id).eq('recipient_id', user1_id).execute()
        
        messages = []
        if res1 and res1.data:
            messages.extend(res1.data)
        if res2 and res2.data:
            messages.extend(res2.data)
            
        messages.sort(key=lambda x: x['created_at'])
        return messages
    except Exception as e:
        print("Ошибка получения сообщений:", e)
        return []

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    if not session.get('user_id'):
        return '', 401
    
    db = get_supabase()
    if db:
        try:
            db.table('users').update({'status': 'В сети'}).eq('id', session['user_id']).execute()
        except Exception as e:
            print("Ошибка heartbeat:", e)
            
    return '', 204

@app.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    current_user_id = session['user_id']
    current_user_name = session['username']
    
    db = get_supabase()
    users = []
    messages = []
    active_recipient_id = request.args.get('to', type=int)
    active_recipient = None

    if db:
        try:
            db.table('users').update({'status': 'В сети'}).eq('id', current_user_id).execute()

            res_users = db.table('users').select('*').neq('id', current_user_id).execute()
            if res_users and res_users.data:
                users = res_users.data
                for u in users:
                    if not u.get('status'):
                        u['status'] = 'В сети'

            if active_recipient_id:
                res_rec = db.table('users').select('*').eq('id', active_recipient_id).execute()
                if res_rec and res_rec.data:
                    active_recipient = res_rec.data[0]

                messages = fetch_messages_between(db, current_user_id, active_recipient_id)
                db.table('messages').update({'is_read': True}).eq('sender_id', active_recipient_id).eq('recipient_id', current_user_id).execute()

        except Exception as e:
            print("Ошибка загрузки данных из БД:", e)

    unread_counts = {}
    if db:
        try:
            res_unread = db.table('messages').select('sender_id').eq('recipient_id', current_user_id).eq('is_read', False).execute()
            if res_unread and res_unread.data:
                for row in res_unread.data:
                    s_id = row['sender_id']
                    unread_counts[s_id] = unread_counts.get(s_id, 0) + 1
        except Exception as e:
            print("Ошибка подсчета непрочитанных:", e)

    return render_template('index.html', 
                           current_user={'id': current_user_id, 'username': current_user_name}, 
                           users=users, 
                           messages=messages, 
                           active_recipient=active_recipient,
                           unread_counts=unread_counts)

@app.route('/send', methods=['POST'])
def send_message():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    recipient_id = request.form.get('recipient_id')
    content = request.form.get('content')

    if not recipient_id or not content:
        return jsonify({'error': 'Missing fields'}), 400

    db = get_supabase()
    if db:
        try:
            db.table('messages').insert({
                'sender_id': session['user_id'],
                'recipient_id': int(recipient_id),
                'content': content,
                'is_read': False
            }).execute()
            return '', 204
        except Exception as e:
            print("Ошибка отправки сообщения:", e)
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Database error'}), 500

@app.route('/get_messages')
def get_messages():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    current_user_id = session['user_id']
    active_recipient_id = request.args.get('to', type=int)
    
    db = get_supabase()
    messages = []
    if db and active_recipient_id:
        messages = fetch_messages_between(db, current_user_id, active_recipient_id)
        try:
            db.table('messages').update({'is_read': True}).eq('sender_id', active_recipient_id).eq('recipient_id', current_user_id).execute()
        except Exception as e:
            print("Ошибка при отметке прочитанных:", e)

    unread_counts = {}
    if db:
        try:
            res_unread = db.table('messages').select('sender_id').eq('recipient_id', current_user_id).eq('is_read', False).execute()
            if res_unread and res_unread.data:
                for row in res_unread.data:
                    s_id = row['sender_id']
                    unread_counts[s_id] = unread_counts.get(s_id, 0) + 1
        except Exception as e:
            print("Ошибка подсчета непрочитанных:", e)

    return jsonify({
        'messages': messages,
        'current_user_id': current_user_id,
        'unread_counts': unread_counts
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        db = get_supabase()
        if db and username and password:
            try:
                res = db.table('users').select('*').eq('username', username).execute()
                if res and res.data:
                    user = res.data[0]
                    # Проверяем хэш пароля
                    if user.get('password_hash') and check_password_hash(user['password_hash'], password):
                        session['user_id'] = user['id']
                        session['username'] = user['username']
                        return redirect(url_for('index'))
                    else:
                        error = 'Неверный пароль'
                else:
                    error = 'Пользователь не найден'
            except Exception as e:
                print("Ошибка входа:", e)
                error = 'Ошибка базы данных'
        else:
            error = 'Заполните все поля'

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        db = get_supabase()
        if db and username and password:
            try:
                res = db.table('users').select('*').eq('username', username).execute()
                if res and res.data:
                    error = 'Такое имя уже занято'
                else:
                    # Хэшируем пароль перед сохранением
                    pwd_hash = generate_password_hash(password)
                    new_user = db.table('users').insert({
                        'username': username, 
                        'password_hash': pwd_hash, 
                        'status': 'В сети'
                    }).execute()
                    
                    if new_user and new_user.data:
                        user = new_user.data[0]
                        session['user_id'] = user['id']
                        session['username'] = user['username']
                        return redirect(url_for('index'))
            except Exception as e:
                print("Ошибка регистрации:", e)
                error = 'Ошибка базы данных'
        else:
            error = 'Заполните все поля'

    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    db = get_supabase()
    if db and session.get('user_id'):
        try:
            db.table('users').update({'status': 'Не в сети'}).eq('id', session['user_id']).execute()
        except Exception as e:
            print("Ошибка при выходе:", e)
            
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
