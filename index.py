from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import os

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_secret_key_change_me')

# Подключение к PostgreSQL (или SQLite локально, если DATABASE_URL не задан)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///messenger.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Модели Базы Данных
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(300), default='Привет, я использую мессенджер!')
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Block(db.Model):
    __tablename__ = 'blocks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        try:
            db.session.commit()
        except:
            db.session.rollback()

# Инициализация таблиц при первом запросе (актуально для Serverless)
@app.before_first_request_custom if hasattr(app, 'before_first_request') else None
def create_tables():
    pass

with app.app_context():
    db.create_all()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('index'))
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    if User.query.filter_by(username=username).first():
        flash('Имя пользователя уже занято')
        return redirect(url_for('login'))
    
    new_user = User(username=username, password=password)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('index.html', users=users, current_user=current_user)

# API для получения списка пользователей и статусов
@app.route('/api/users')
@login_required
def api_users():
    users = User.query.filter(User.id != current_user.id).all()
    users_data = []
    for u in users:
        # Форматируем last_seen
        last_seen_str = u.last_seen.strftime('%d.%m.%Y %H:%M') if u.last_seen else 'неизвестно'
        users_data.append({
            'id': u.id,
            'username': u.username,
            'status': u.status,
            'last_seen': last_seen_str
        })
    return jsonify(users_data)

# API для отправки сообщения
@app.route('/api/messages/send', methods=['POST'])
@login_required
def api_send_message():
    data = request.json
    recipient_id = data.get('recipient_id')
    content = data.get('content')
    
    if not recipient_id or not content:
        return jsonify({'error': 'Неверные данные'}), 400
        
    # Проверка на блокировку
    is_blocked = Block.query.filter_by(user_id=recipient_id, blocked_id=current_user.id).first()
    if is_blocked:
        return jsonify({'error': 'Вы заблокированы этим пользователем'}), 403
        
    msg = Message(sender_id=current_user.id, recipient_id=recipient_id, content=content)
    db.session.add(msg)
    db.session.commit()
    return jsonify({'success': True, 'timestamp': msg.timestamp.strftime('%H:%M')})

# API для получения сообщений с конкретным пользователем
@app.route('/api/messages/<int:recipient_id>')
@login_required
def api_get_messages(recipient_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == recipient_id)) |
        ((Message.sender_id == recipient_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    result = []
    for m in messages:
        result.append({
            'sender_id': m.sender_id,
            'content': m.content,
            'timestamp': m.timestamp.strftime('%H:%M')
        })
    return jsonify(result)

# API для блокировки пользователя
@app.route('/api/block/<int:user_id>', methods=['POST'])
@login_required
def api_block_user(user_id):
    existing = Block.query.filter_by(user_id=current_user.id, blocked_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'unblocked'})
    else:
        new_block = Block(user_id=current_user.id, blocked_id=user_id)
        db.session.add(new_block)
        db.session.commit()
        return jsonify({'status': 'blocked'})

# API для редактирования профиля
@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_update_profile():
    data = request.json
    new_status = data.get('status')
    if new_status is not None:
        current_user.status = new_status
        db.session.commit()
    return jsonify({'success': True})

# Точка входа для Vercel Serverless
# Vercel ищет переменную 'app'
if __name__ == '__main__':
    app.run(debug=True)
