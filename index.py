from datetime import datetime, timezone, timedelta

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    if not session.get('user_id'):
        return '', 401
    
    db = get_supabase()
    if db:
        try:
            # Обновляем метку времени последнего визита на текущий момент (UTC)
            now_utc = datetime.now(timezone.utc).isoformat()
            db.table('users').update({
                'status': 'В сети',
                'last_seen': now_utc
            }).eq('id', session['user_id']).execute()
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
            # Сразу обновляем себя при заходе
            now_utc = datetime.now(timezone.utc).isoformat()
            db.table('users').update({
                'status': 'В сети',
                'last_seen': now_utc
            }).eq('id', current_user_id).execute()

            # Загружаем пользователей
            res_users = db.table('users').select('*').neq('id', current_user_id).execute()
            if res_users and res_users.data:
                raw_users = res_users.data
                now_dt = datetime.now(timezone.utc)
                
                # Проверяем, кто реально в сети (был активен менее чем 60 секунд назад)
                for u in raw_users:
                    last_seen_str = u.get('last_seen')
                    if last_seen_str:
                        # Парсим время из базы (Supabase отдает ISO формат)
                        try:
                            # Очищаем строку от возможных артефактов
                            clean_date = last_seen_str.replace('Z', '+00:00')
                            last_seen_dt = datetime.fromisoformat(clean_date)
                            diff_seconds = (now_dt - last_seen_dt).total_seconds()
                            
                            if diff_seconds > 60:
                                # Пользователь не пинговал больше минуты — он офлайн
                                offline_time = last_seen_dt.astimezone().strftime("%H:%M")
                                u['status'] = f'Был в сети в {offline_time}'
                            else:
                                u['status'] = 'В сети'
                        except Exception as parse_err:
                            print("Ошибка парсинга даты:", parse_err)
                            u['status'] = 'Не в сети'
                    else:
                        u['status'] = 'Не в сети'
                        
                users = raw_users

            if active_recipient_id:
                res_rec = db.table('users').select('*').eq('id', active_recipient_id).execute()
                if res_rec and res_rec.data:
                    active_recipient = res_rec.data[0]
                    # Также форматируем статус собеседника в шапке чата
                    last_seen_str = active_recipient.get('last_seen')
                    if last_seen_str:
                        try:
                            clean_date = last_seen_str.replace('Z', '+00:00')
                            last_seen_dt = datetime.fromisoformat(clean_date)
                            if (now_dt - last_seen_dt).total_seconds() > 60:
                                active_recipient['status'] = f"Был в сети в {last_seen_dt.astimezone().strftime('%H:%M')}"
                            else:
                                active_recipient['status'] = 'В сети'
                        except:
                            pass

                messages = fetch_messages_between(db, current_user_id, active_recipient_id)
                db.table('messages').update({'is_read': True}).eq('sender_id', active_recipient_id).eq('recipient_id', current_user_id).execute()

        except Exception as e:
            print("Ошибка загрузки данных из БД:", e)

    # (подсчет непрочитанных остается без изменений)
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
