import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "super_secret_messenger_key")

# Подключение к Supabase PostgreSQL
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# Главная страница мессенджера (отдает графический интерфейс)
@app.route('/')
def index():
    # Убедитесь, что у вас в проекте создана папка templates с файлом index.html
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)