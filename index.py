import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-change-it')

def get_supabase():
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '').strip()
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    if not SUPABASE_URL.startswith('http://') and not SUPABASE_URL.startswith('https://'):
        return None

    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Ошибка инициализации клиента Supabase:", e)
        return None

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
            # Получаем всех пользователей, кроме себя
            res_users = db.table('users').select('*').neq('id', current_user_id).execute()
            if res_users and hasattr(res_users, 'data'):
                users = res_users.data

            if active_recipient_id:
                res_rec = db.table('users').select('*').eq('id', active_recipient_id).execute()
                if res_rec and res_rec.data:
                    active_recipient = res_rec.data[0]

                # Загружаем историю переписки
                res_msg = db.table('messages').select('*').or_(
                    f"and(sender_id.eq.{current_user_id},recipient_id.eq.{active_recipient_id}),and(sender_id.eq.{active_recipient_id},recipient_id.eq.{current_user_id})"
                ).order('created_at').execute()
                
                if res_msg and hasattr(res_msg, 'data'):
                    messages = res_msg.data
                    
                # Отмечаем сообщения как прочитанные при открытии чата
                db.table('messages').update({'is_read': True}).eq('sender_id', active_recipient_id).eq('recipient_id', current_user_id).execute()

        except Exception as e:
            print("Ошибка загрузки данных из БД:", e)

    # Подсчет непрочитанных сообщений для каждого пользователя
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

# API для получения новых сообщений и непрочитанных в реальном времени (без перезагрузки)
@app.route('/get_messages')
def get_messages():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    current_user_id = session['user_id']
    active_recipient_id = request.args.get('to', type=int)
    
    db = get_supabase()
    if not db:
        return jsonify({'messages': [], 'unread_counts': {}})
    
    try:
        messages = []
        if active_recipient_id:
            res_msg = db.table('messages').select('*').or_(
                f"and(sender_id.eq.{current_user_id},recipient_id.eq.{active_recipient_id}),and(sender_id.eq.{active_recipient_id},recipient_id.eq.{current_user_id})"
            ).order('created_at').execute()
            if res_msg and res_msg.data:
                messages = res_msg.data
                
            # Автоматически помечаем как прочитанные
            db.table('messages').update({'is_read': True}).eq('sender_id', active_recipient_id).eq('recipient_id', current_user_id).execute()

        unread_counts = {}
        res_unread = db.table('messages').select('sender_id').eq('recipient_id', current_user_id).eq('is_read', False).execute()
        if res_unread and res_unread.data:
            for row in res_unread.data:
                s_id = row['sender_id']
                unread_counts[s_id] = unread_counts.get(s_id, 0) + 1

        return jsonify({'messages': messages, 'unread_counts': unread_counts, 'current_user_id': current_user_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/send', methods=['POST'])
def send_message():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    recipient_id = request.form.get('recipient_id', type=int)
    content = request.form.get('content', '').strip()
    
    if recipient_id and content:
        db = get_supabase()
        if db:
            try:
                db.table('messages').insert({
                    'sender_id': session['user_id'],
                    'recipient_id': recipient_id,
                    'content': content,
                    'is_read': False
                }).execute()
            except Exception as e:
                print("Ошибка отправки сообщения:", e)
                
    return redirect(url_for('index', to=recipient_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if username:
            db = get_supabase()
            if not db:
                error = "Ошибка: не заданы или некорректны SUPABASE_URL / SUPABASE_KEY в настройках Vercel."
            else:
                try:
                    existing = db.table('users').select('*').eq('username', username).execute()
                    if existing.data:
                        user_data = existing.data[0]
                    else:
                        new_user = db.table('users').insert({'username': username, 'status': 'В сети'}).execute()
                        user_data = new_user.data[0]
                    
                    session['user_id'] = user_data['id']
                    session['username'] = user_data['username']
                    session['status'] = user_data.get('status', 'В сети')
                    return redirect(url_for('index'))
                except Exception as e:
                    error = f"Ошибка базы данных: {str(e)}"
                
    return f'''
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Вход в мессенджер</title>
        <style>
            body {{ background: #121212; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .login-box {{ background: #1e1e1e; padding: 30px; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 320px; }}
            input {{ width: 100%; padding: 10px; margin: 10px 0 20px; background: #333; border: 1px solid #444; color: #fff; border-radius: 4px; box-sizing: border-box; }}
            button {{ width: 100%; padding: 10px; background: #0088cc; color: white; border: none; border-radius: 4px; cursor: pointer; }}
            button:hover {{ background: #006699; }}
            .error {{ color: #ff4d4d; font-size: 13px; margin-bottom: 10px; background: rgba(255,77,77,0.1); padding: 8px; border-radius: 4px; line-height: 1.4; }}
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
