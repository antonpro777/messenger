import os
import uuid
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "static" / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-development-only-change-me")
if os.environ.get("VERCEL") and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("Set SECRET_KEY in Vercel Project Environment Variables.")
# Never accept ephemeral SQLite on Vercel: it would silently lose accounts and posts.
database_url = os.environ.get("DATABASE_URL")
if os.environ.get("VERCEL") and not database_url:
    raise RuntimeError("Pixora is not configured: add DATABASE_URL (Supabase PostgreSQL) to Vercel.")
if not database_url:
    database_url = f"sqlite:///{BASE_DIR / 'pixora.db'}"
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = (
    {
        "pool_pre_ping": True,
        "pool_size": 1,
        "max_overflow": 0,
        "connect_args": {"prepare_threshold": None},
    }
    if database_url.startswith("postgresql")
    else {}
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # Videos upload directly to Storage
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
    stories = db.relationship("Story", backref="author", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(500), nullable=False)
    media_type = db.Column(db.String(12), nullable=False, default="image")
    is_pixo = db.Column(db.Boolean, nullable=False, default=False)
    duration_seconds = db.Column(db.Float, nullable=True)
    caption = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    likes = db.relationship("Like", backref="post", lazy="dynamic", cascade="all, delete-orphan")

    def liked_by(self, user):
        return bool(user.is_authenticated and Like.query.filter_by(user_id=user.id, post_id=self.id).first())


class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    media = db.Column(db.String(500), nullable=False)
    caption = db.Column(db.String(180), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)
    author = db.relationship("User")



class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    body = db.Column(db.String(2000), default="")
    attachment = db.Column(db.String(500), default="")
    attachment_type = db.Column(db.String(12), nullable=False, default="image")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="unique_user_post_like"),)


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("follower_id", "followed_id", name="unique_follow_pair"),
        db.CheckConstraint("follower_id <> followed_id", name="no_self_follow"),
    )


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route("/css/<path:filename>")
def public_css(filename):
    return send_from_directory(BASE_DIR / "public" / "css", filename)


@app.context_processor
def inject_globals():
    return {"site_name": "Pixora", "media_url": media_url, "post_comments": lambda post_id: Comment.query.filter_by(post_id=post_id).order_by(Comment.created_at.asc()).all()}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def media_url(value):
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return url_for("static", filename="uploads/" + Path(value).name)


def save_image(file):
    if not file or not file.filename or not allowed_file(file.filename):
        raise ValueError("Поддерживаются JPG, PNG, GIF и WEBP.")
    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    storage_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if storage_url and storage_key:
        content_type = (file.mimetype or "").lower()
        allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if content_type not in allowed_types:
            raise ValueError("Формат файла не поддерживается. Выберите JPG, PNG, GIF или WEBP.")
        file_data = file.stream.read()
        if not file_data:
            raise ValueError("Выберите непустой файл.")
        if len(file_data) > 12 * 1024 * 1024:
            raise ValueError("Размер фотографии не должен превышать 12 МБ.")
        try:
            response = requests.post(
                f"{storage_url}/storage/v1/object/pixora-uploads/{filename}",
                headers={
                    "Authorization": f"Bearer {storage_key}",
                    "apikey": storage_key,
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                data=file_data,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ValueError("Supabase Storage временно недоступен. Попробуйте ещё раз.") from exc
        if not response.ok:
            raise ValueError("Supabase Storage отклонил загрузку. Проверьте ключ и настройки bucket pixora-uploads.")
        return f"{storage_url}/storage/v1/object/public/pixora-uploads/{filename}"
    if os.environ.get("VERCEL"):
        raise ValueError("Для загрузки фото нужно настроить SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY в Vercel.")
    file.save(UPLOAD_DIR / filename)
    return filename


def remove_image(value):
    if not value:
        return
    storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    storage_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY")
    if storage_url and storage_key and value.startswith(storage_url + "/storage/v1/object/"):
        bucket = "pixora-videos" if "/pixora-videos/" in value else "pixora-uploads"
        marker = "/" + bucket + "/"
        object_path = value.split(marker, 1)[1].split("?", 1)[0] if marker in value else value.rsplit("/", 1)[-1]
        requests.delete(
            f"{storage_url}/storage/v1/object/{bucket}",
            headers={"Authorization": f"Bearer {storage_key}", "apikey": storage_key},
            json={"prefixes": [object_path]},
            timeout=20,
        )
        return
    path = UPLOAD_DIR / Path(value).name
    if path.exists():
        path.unlink()


@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    pagination = Post.query.order_by(Post.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    stories = Story.query.order_by(Story.created_at.desc()).limit(40).all()
    return render_template("feed.html", posts=pagination.items, pagination=pagination, stories=stories)


@app.route("/pixo")
def pixo_feed():
    posts = Post.query.filter_by(media_type="video", is_pixo=True).order_by(Post.created_at.desc()).limit(60).all()
    return render_template("pixo.html", posts=posts)


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
        if not (3 <= len(username) <= 30) or not username.isascii() or not username.replace("_", "").isalnum():
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
    flash("Вы вышли из аккаунта. Теперь можно войти в другой или создать новый.", "info")
    return redirect(url_for("login"))



def video_public_url(path):
    storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not storage_url:
        return ""
    return f"{storage_url}/storage/v1/object/public/pixora-videos/{path}"


@app.route("/api/videos/sign", methods=["POST"])
@login_required
def sign_video_upload():
    storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    storage_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not storage_url or not storage_key:
        return {"error": "Видеохранилище пока не настроено."}, 503
    data = request.get_json(silent=True) or {}
    is_pixo = bool(data.get("is_pixo", True))
    content_type = "video/webm" if is_pixo else str(data.get("content_type", "video/mp4"))
    if content_type not in {"video/webm", "video/mp4"}:
        return {"error": "Поддерживаются MP4 и WebM."}, 400
    extension = "webm" if content_type == "video/webm" else "mp4"
    path = f"user_{current_user.id}/{uuid.uuid4().hex}.{extension}"
    endpoint = f"{storage_url}/storage/v1/object/upload/sign/pixora-videos/{quote(path, safe='/')}"
    try:
        response = requests.post(endpoint, headers={"Authorization": f"Bearer {storage_key}", "apikey": storage_key}, json={}, timeout=20)
        if not response.ok:
            app.logger.warning("Video signing failed with status %s", response.status_code)
            return {"error": "Не удалось подготовить загрузку видео."}, 502
        payload = response.json()
        token = payload.get("token")
        if not token:
            return {"error": "Хранилище не вернуло токен загрузки."}, 502
        project_ref = storage_url.split("//", 1)[-1].split(".", 1)[0]
        return {"path": path, "token": token, "content_type": content_type, "is_pixo": is_pixo, "endpoint": f"https://{project_ref}.storage.supabase.co/storage/v1/upload/resumable"}
    except (requests.RequestException, ValueError):
        return {"error": "Хранилище временно недоступно."}, 502


@app.route("/api/videos/publish", methods=["POST"])
@login_required
def publish_video():
    data = request.get_json(silent=True) or {}
    path = str(data.get("path", ""))
    try:
        duration = float(data.get("duration_seconds", 0))
    except (TypeError, ValueError):
        duration = 0
    caption = str(data.get("caption", "")).strip()[:500]
    is_pixo = bool(data.get("is_pixo", True))
    if not path.startswith(f"user_{current_user.id}/") or not path.endswith((".webm", ".mp4")) or ".." in path:
        abort(400)
    if duration <= 0 or (is_pixo and duration > 60.5):
        return {"error": "Pixo — это видео длительностью до 60 секунд."}, 400
    public_url = video_public_url(path)
    try:
        check = requests.head(public_url, timeout=15)
    except requests.RequestException:
        return {"error": "Не удалось проверить загруженное видео."}, 502
    if check.status_code != 200:
        return {"error": "Видео ещё не загрузилось полностью. Попробуй снова."}, 400
    post = Post(image=public_url, media_type="video", is_pixo=is_pixo, duration_seconds=round(duration, 2), caption=caption, author=current_user)
    db.session.add(post)
    db.session.commit()
    return {"ok": True, "redirect": url_for("profile", username=current_user.username)}


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        try:
            filename = save_image(request.files.get("photo"))
            post = Post(image=filename, caption=request.form.get("caption", "").strip()[:500], author=current_user)
            db.session.add(post)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                remove_image(filename)
                raise
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
                old_name = post.image
                new_name = save_image(replacement)
                post.image = new_name
                post.media_type = "image"
                post.is_pixo = False
                post.duration_seconds = None
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    remove_image(new_name)
                    raise
                remove_image(old_name)
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
    followers_count = Follow.query.filter_by(followed_id=user.id).count()
    following_count = Follow.query.filter_by(follower_id=user.id).count()
    is_following = bool(current_user.is_authenticated and Follow.query.filter_by(
        follower_id=current_user.id, followed_id=user.id
    ).first())
    return render_template(
        "profile.html", profile_user=user, posts=posts,
        followers_count=followers_count, following_count=following_count,
        is_following=is_following,
        stories=user.stories.order_by(Story.created_at.desc()).all(),
    )


@app.route("/follow/<username>", methods=["POST"])
@login_required
def toggle_follow(username):
    user = User.query.filter_by(username=username.lower()).first_or_404()
    if user.id == current_user.id:
        abort(400)
    relation = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
    if relation:
        db.session.delete(relation)
    else:
        db.session.add(Follow(follower_id=current_user.id, followed_id=user.id))
    db.session.commit()
    return redirect(url_for("profile", username=user.username))



@app.route("/stories/create", methods=["POST"])
@login_required
def create_story():
    try:
        media = save_image(request.files.get("photo"))
        story = Story(media=media, caption=request.form.get("caption", "").strip()[:180], author=current_user)
        db.session.add(story)
        db.session.commit()
        flash("История опубликована!", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(request.referrer or url_for("index"))


@app.route("/stories/<int:story_id>")
def view_story(story_id):
    story = db.get_or_404(Story, story_id)
    return render_template("story.html", story=story)


@app.route("/u/<username>/<kind>")
def connections(username, kind):
    user = User.query.filter_by(username=username.lower()).first_or_404()
    if kind == "followers":
        ids = db.session.query(Follow.follower_id).filter_by(followed_id=user.id).subquery()
        people = User.query.filter(User.id.in_(ids)).order_by(User.username.asc()).all()
        heading = "Подписчики"
    elif kind == "following":
        ids = db.session.query(Follow.followed_id).filter_by(follower_id=user.id).subquery()
        people = User.query.filter(User.id.in_(ids)).order_by(User.username.asc()).all()
        heading = "Подписки"
    else:
        abort(404)
    return render_template("connections.html", profile_user=user, people=people, heading=heading)


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    post = db.get_or_404(Post, post_id)
    body = request.form.get("body", "").strip()
    if not body or len(body) > 500:
        flash("Комментарий должен содержать от 1 до 500 символов.", "error")
    else:
        db.session.add(Comment(body=body, user_id=current_user.id, post_id=post.id))
        db.session.commit()
    return redirect(request.referrer or url_for("index"))




@app.route("/api/audio/sign", methods=["POST"])
@login_required
def sign_audio_upload():
    storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    storage_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not storage_url or not storage_key:
        return {"error": "Голосовые сообщения пока не настроены."}, 503
    path = f"user_{current_user.id}/{uuid.uuid4().hex}.webm"
    endpoint = f"{storage_url}/storage/v1/object/upload/sign/pixora-audio/{quote(path, safe='/')}"
    try:
        response = requests.post(endpoint, headers={"Authorization": f"Bearer {storage_key}", "apikey": storage_key}, json={}, timeout=20)
        if not response.ok:
            return {"error": "Не удалось подготовить голосовое сообщение."}, 502
        token = response.json().get("token")
        if not token:
            return {"error": "Хранилище не вернуло токен."}, 502
        project_ref = storage_url.split("//", 1)[-1].split(".", 1)[0]
        return {"path": path, "token": token, "endpoint": f"https://{project_ref}.storage.supabase.co/storage/v1/upload/resumable"}
    except (requests.RequestException, ValueError):
        return {"error": "Хранилище временно недоступно."}, 502


@app.route("/audio/<int:message_id>")
@login_required
def play_voice_message(message_id):
    message = db.get_or_404(Message, message_id)
    if current_user.id not in (message.sender_id, message.recipient_id) or message.attachment_type != "voice":
        abort(403)
    storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    storage_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not storage_url or not storage_key:
        abort(503)
    endpoint = f"{storage_url}/storage/v1/object/sign/pixora-audio/{quote(message.attachment, safe='/')}"
    try:
        response = requests.post(endpoint, headers={"Authorization": f"Bearer {storage_key}", "apikey": storage_key}, json={"expiresIn": 3600}, timeout=15)
        if not response.ok:
            abort(502)
        signed = response.json().get("signedURL") or response.json().get("signedUrl")
        if not signed:
            abort(502)
        if signed.startswith("http://") or signed.startswith("https://"):
            return redirect(signed)
        return redirect(storage_url + "/storage/v1" + signed)
    except requests.RequestException:
        abort(502)


@app.route("/chats")
@login_required
def chats():
    from sqlalchemy import case
    peer_id = case((Message.sender_id == current_user.id, Message.recipient_id), else_=Message.sender_id)
    latest = db.session.query(func.max(Message.created_at).label("last_at"), peer_id.label("peer_id")).filter(or_(Message.sender_id == current_user.id, Message.recipient_id == current_user.id)).group_by(peer_id).subquery()
    people = User.query.join(latest, User.id == latest.c.peer_id).order_by(latest.c.last_at.desc()).all()
    return render_template("chats.html", people=people)

@app.route("/chats/<username>", methods=["GET", "POST"])
@login_required
def chat_thread(username):
    peer = User.query.filter_by(username=username.lower()).first_or_404()
    if peer.id == current_user.id:
        abort(400)
    if request.method == "POST":
        body = request.form.get("body", "").strip()[:2000]
        attachment = ""
        attachment_type = "image"
        voice_path = request.form.get("voice_path", "").strip()
        if voice_path:
            if not voice_path.startswith(f"user_{current_user.id}/") or not voice_path.endswith(".webm") or ".." in voice_path:
                abort(400)
            storage_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
            storage_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if not storage_url or not storage_key:
                abort(503)
            check_url = f"{storage_url}/storage/v1/object/pixora-audio/{quote(voice_path, safe='/')}"
            check = requests.head(check_url, headers={"Authorization": f"Bearer {storage_key}", "apikey": storage_key}, timeout=15)
            if check.status_code != 200:
                flash("Голосовое сообщение ещё не загрузилось.", "error")
                return redirect(url_for("chat_thread", username=peer.username))
            attachment = voice_path
            attachment_type = "voice"
        upload = request.files.get("photo")
        if upload and upload.filename:
            try:
                attachment = save_image(upload)
                attachment_type = "image"
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("chat_thread", username=peer.username))
        if body or attachment:
            db.session.add(Message(sender_id=current_user.id, recipient_id=peer.id, body=body, attachment=attachment, attachment_type=attachment_type))
            db.session.commit()
        return redirect(url_for("chat_thread", username=peer.username))
    messages = Message.query.filter(or_((Message.sender_id == current_user.id) & (Message.recipient_id == peer.id), (Message.sender_id == peer.id) & (Message.recipient_id == current_user.id))).order_by(Message.created_at.asc()).limit(300).all()
    return render_template("chat_thread.html", peer=peer, messages=messages)

@app.route("/api/revision")
def api_revision():
    stamps = [
        db.session.query(func.max(Post.created_at)).scalar(),
        db.session.query(func.max(Story.created_at)).scalar(),
        db.session.query(func.max(Like.created_at)).scalar(),
        db.session.query(func.max(Follow.created_at)).scalar(),
        db.session.query(func.max(Comment.created_at)).scalar(),
    ]
    stamps.append(db.session.query(func.max(Message.created_at)).scalar())
    counts = [Post.query.count(), Story.query.count(), Like.query.count(), Follow.query.count(), Comment.query.count(), Message.query.count()]
    return {"revision": "|".join(x.isoformat() if x else "" for x in stamps) + "|" + ",".join(map(str, counts))}


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
            new_avatar = None
            old_avatar = current_user.avatar
            if avatar and avatar.filename:
                try:
                    new_avatar = save_image(avatar)
                    current_user.avatar = new_avatar
                except ValueError as exc:
                    flash(str(exc), "error")
                    return render_template("settings.html")
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                if new_avatar:
                    remove_image(new_avatar)
                raise
            if new_avatar:
                remove_image(old_avatar)
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
    try:
        db.create_all()
        from sqlalchemy import inspect, text
        message_columns = {column["name"] for column in inspect(db.engine).get_columns("message")}
        if "attachment_type" not in message_columns:
            db.session.execute(text("ALTER TABLE message ADD COLUMN attachment_type VARCHAR(12) NOT NULL DEFAULT 'image'"))
        # Additive migration for existing Pixora installations (Postgres and SQLite).
        from sqlalchemy import inspect, text
        post_columns = {column["name"] for column in inspect(db.engine).get_columns("post")}
        if "media_type" not in post_columns:
            db.session.execute(text("ALTER TABLE post ADD COLUMN media_type VARCHAR(12) NOT NULL DEFAULT 'image'"))
        if "duration_seconds" not in post_columns:
            db.session.execute(text("ALTER TABLE post ADD COLUMN duration_seconds FLOAT"))
        if "is_pixo" not in post_columns:
            db.session.execute(text("ALTER TABLE post ADD COLUMN is_pixo BOOLEAN NOT NULL DEFAULT FALSE"))
        db.session.commit()
    except Exception as exc:
        # Keep the real database error visible in Vercel logs without exposing credentials.
        import re
        safe_error = re.sub(r"(?i)(password\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", str(exc))
        safe_error = re.sub(r"(?i)(://[^:/@]+:)[^@]+@", r"\1[REDACTED]@", safe_error)
        app.logger.error("Pixora database initialization failed: %s: %s", type(exc).__name__, safe_error)
        raise


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
