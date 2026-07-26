from datetime import datetime

# (остальной код импортов и get_supabase остается прежним)

@app.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    current_user_id = session['user_id']
    current_user_name = session['username']
    
    db = get_supabase()
    
    if db:
        try:
            # Обновляем статус текущего пользователя на "В сети"
            db.table('users').update({'status': 'В сети'}).eq('id', current_user_id).execute()
        except Exception as e:
            print("Ошибка обновления статуса:", e)

    users = []
    messages = []
    active_recipient_id = request.args.get('to', type=int)
    active_recipient = None

    if db:
        try:
            res_users = db.table('users').select('*').neq('id', current_user_id).execute()
            if res_users and res_users.data:
                users = res_users.data

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

@app.route('/logout')
def logout():
    db = get_supabase()
    if db and session.get('user_id'):
        try:
            # Фиксируем время выхода или статус "Был в сети"
            time_str = datetime.now().strftime("%H:%M")
            db.table('users').update({'status': f'Был в сети в {time_str}'}).eq('id', session['user_id']).execute()
        except Exception as e:
            print("Ошибка при выходе:", e)
            
    session.clear()
    return redirect(url_for('login'))
