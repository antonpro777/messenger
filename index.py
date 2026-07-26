import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Секретный ключ для сессий
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_messenger_key")

# Подключение к удаленной базе данных PostgreSQL (Supabase) через переменную окружения Vercel
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Пример простой модели пользователя (приведите к вашей схеме, если она уже написана)
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

@app.route('/')
def index():
    return "Messenger is running on Vercel with Supabase!"

if __name__ == '__main__':
    app.run(debug=True)