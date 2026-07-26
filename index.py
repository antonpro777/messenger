from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-it'  # Нужен для работы сессий

# Временная заглушка текущего пользователя для сессии
@app.before_request
def load_user():
    # Проверяем, авторизован ли пользователь в сессии
    if 'username' in session:
        # Объект текущего пользователя для шаблона
        class User:
            username = session['username']
            status = session.get('status', 'В сети')
        app.config['CURRENT_USER'] = User()
    else:
        app.config['CURRENT_USER'] = None

@app.route('/')
def index():
    # Если пользователь не вошел, отправляем на страницу логина
    if not session.get('username'):
        return redirect(url_for('login'))
    
    # Передаем пользователя в шаблон
    current_user = app.config.get('CURRENT_USER')
    return render_template('index.html', current_user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            session['username'] = username
            session['status'] = 'В сети'
            return redirect(url_for('index'))
            
    # Простейшая форма входа прямо в коде, пока не подключили отдельный шаблон
    return '''
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Вход в мессенджер</title>
        <style>
            body { background: #121212; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: #1e1e1e; padding: 30px; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 300px; }
            input { width: 100%; padding: 10px; margin: 10px 0 20px; background: #333; border: 1px solid #444; color: #fff; border-radius: 4px; box-sizing: border-box; }
            button { width: 100%; padding: 10px; background: #0088cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #006699; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h3>Вход в мессенджер</h3>
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
