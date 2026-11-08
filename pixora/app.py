import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "static" / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-deploying")
database_url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'pixora.db'}")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Войдите в Pixora, чтобы продолжить."
login_manager.login_message_category = "info"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(60), nullable=False)
    bio = db.Column(db.String(180), default="")
    avatar = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    posts = db.relationship("Post", backref="author", lazy="dynamic", cascade="all, delete-orphan")
    likes = db.relationship("Like", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    likes = db.relationship("Like", backref="post", lazy="dynamic", cascade="all, delete-orphan")

    def liked_by(self, user):
        return bool(user.is_authenticated and Like.query.filter_by(user_id=user.id, post_id=self.id).first())


class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="unique_user_post_like"),)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.context_processor
def inject_globals():
    return {"site_name": "Pixora"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file):
    if not file or not file.filename or not allowed_file(file.filename):
        raise ValueError("Поддерживаются JPG, PNG, GIF и WEBP.")
    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(UPLOAD_DIR / filename)
    return filename


def remove_image(filename):
    if filename:
        path = UPLOAD_DIR / Path(filename).name
        if path.exists():
            path.unlink()


@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    pagination = Post.query.order_by(Post.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template("feed.html", posts=pagination.items, pagination=pagination)


@app.route("/explore")
def explore():
    posts = Post.query.order_by(func.random()).limit(36).all()
    return render_template("explore.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not (3 <= len(username) <= 30) or not username.replace("_", "").isalnum():
            flash("Имя пользователя: 3–30 символов, латинские буквы, цифры и _.", "error")
        elif len(password) < 8:
            flash("Пароль должен содержать не менее 8 символов.", "error")
        elif User.query.filter(or_(User.username == username, User.email == email)).first():
            flash("Такое имя пользователя или почта уже зарегистрированы.", "error")
        else:
            user = User(username=username, email=email, display_name=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Добро пожаловать в Pixora!", "success")
            return redirect(url_for("index"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip().lower()
        user = User.query.filter(or_(User.username == identity, User.email == identity)).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user)
            return redirect(request.args.get("next") or url_for("index"))
        flash("Неверное имя пользователя, почта или пароль.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Вы вышли из аккаунта.", "info")
    return redirect(url_for("index"))


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        try:
            filename = save_image(request.files.get("photo"))
            post = Post(image=filename, caption=request.form.get("caption", "").strip()[:500], author=current_user)
            db.session.add(post)
            db.session.commit()
            flash("Фото опубликовано!", "success")
            return redirect(url_for("profile", username=current_user.username))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("upload.html")


@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def toggle_like(post_id):
    post = db.get_or_404(Post, post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(Like(user_id=current_user.id, post_id=post.id))
    db.session.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id != current_user.id:
        abort(403)
    if request.method == "POST":
        post.caption = request.form.get("caption", "").strip()[:500]
        replacement = request.files.get("photo")
        if replacement and replacement.filename:
            try:
                new_name = save_image(replacement)
                remove_image(post.image)
                post.image = new_name
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("edit_post.html", post=post)
        db.session.commit()
        flash("Публикация обновлена.", "success")
        return redirect(url_for("profile", username=current_user.username))
    return render_template("edit_post.html", post=post)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id != current_user.id:
        abort(403)
    filename = post.image
    db.session.delete(post)
    db.session.commit()
    remove_image(filename)
    flash("Публикация удалена.", "info")
    return redirect(url_for("profile", username=current_user.username))


@app.route("/u/<username>")
def profile(username):
    user = User.query.filter_by(username=username.lower()).first_or_404()
    posts = user.posts.order_by(Post.created_at.desc()).all()
    return render_template("profile.html", profile_user=user, posts=posts)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "").strip()
        if not display_name or len(display_name) > 60 or len(bio) > 180:
            flash("Проверьте имя (1–60 символов) и описание (до 180 символов).", "error")
        else:
            current_user.display_name = display_name
            current_user.bio = bio
            avatar = request.files.get("avatar")
            if avatar and avatar.filename:
                try:
                    filename = save_image(avatar)
                    remove_image(current_user.avatar)
                    current_user.avatar = filename
                except ValueError as exc:
                    flash(str(exc), "error")
                    return render_template("settings.html")
            db.session.commit()
            flash("Профиль сохранён.", "success")
            return redirect(url_for("profile", username=current_user.username))
    return render_template("settings.html")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    users = []
    if q:
        users = User.query.filter(or_(User.username.ilike(f"%{q}%"), User.display_name.ilike(f"%{q}%"))).limit(30).all()
    return render_template("search.html", q=q, users=users)


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="У вас нет доступа к этому действию."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Кажется, эта страница потерялась."), 404


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
