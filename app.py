import io
import logging
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import speech_recognition as sr
from flask import (
    Flask,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATABASE = BASE_DIR / "voice_notes.db"
ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a", "webm", "ogg", "flac", "aiff", "aif"}
MAX_AUDIO_SIZE = 100 * 1024 * 1024

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=MAX_AUDIO_SIZE,
)
logging.basicConfig(level=logging.INFO)


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                audio_file TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_forms():
    if request.method == "POST":
        submitted = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not secrets.compare_digest(submitted, expected):
            abort(400, description="Form tidak valid atau sesi telah kedaluwarsa. Muat ulang halaman.")


def get_note(note_id):
    with get_db() as connection:
        note = connection.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
    if note is None:
        abort(404)
    return note


def validate_audio_name(filename):
    if not filename or not re.fullmatch(r"[a-f0-9]{32}\.[a-z0-9]+", filename):
        return None
    path = UPLOAD_DIR / filename
    return path if path.is_file() else None


def save_audio(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    original_name = secure_filename(file_storage.filename)
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Format audio tidak didukung. Gunakan WAV, MP3, M4A, WebM, OGG, FLAC, atau AIFF.")
    filename = f"{uuid.uuid4().hex}.{extension}"
    file_storage.save(UPLOAD_DIR / filename)
    return filename


def transcribe_audio(path):
    extension = path.suffix.lower().lstrip(".")
    try:
        if extension in {"wav", "aiff", "aif", "flac"}:
            audio_source = sr.AudioFile(str(path))
            with audio_source as source:
                audio = sr.Recognizer().record(source)
        else:
            from pydub import AudioSegment

            converted = AudioSegment.from_file(path).set_channels(1).set_frame_rate(16000)
            buffer = io.BytesIO()
            converted.export(buffer, format="wav")
            buffer.seek(0)
            with sr.AudioFile(buffer) as source:
                audio = sr.Recognizer().record(source)
    except (ImportError, OSError, ValueError) as error:
        raise ValueError(
            "Audio tidak dapat dibaca. Untuk MP3, M4A, WebM, atau OGG, pastikan FFmpeg sudah terpasang."
        ) from error
    except Exception as error:
        if not error.__class__.__module__.startswith("pydub."):
            raise
        raise ValueError(
            "Audio tidak dapat dibaca. Untuk MP3, M4A, WebM, atau OGG, pastikan FFmpeg sudah terpasang."
        ) from error

    recognizer = sr.Recognizer()
    try:
        return recognizer.recognize_google(audio, language="id-ID")
    except sr.UnknownValueError as error:
        raise ValueError("Ucapan tidak dapat dikenali. Coba gunakan audio yang lebih jelas.") from error
    except sr.RequestError as error:
        app.logger.warning("Layanan transkripsi tidak tersedia: %s", error)
        raise ValueError("Layanan transkripsi tidak dapat dihubungi. Periksa koneksi internet lalu coba lagi.") from error


def create_note(title, content, category, audio_file=None):
    title = title.strip()
    content = content.strip()
    if not title:
        raise ValueError("Judul catatan wajib diisi.")
    if not content:
        raise ValueError("Isi catatan tidak boleh kosong.")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with get_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO notes (title, content, category, audio_file, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title[:150], content, category.strip()[:80], audio_file, now, now),
        )
        return cursor.lastrowid


@app.errorhandler(413)
def file_too_large(_error):
    flash("Ukuran file terlalu besar. Batas maksimum adalah 100 MB.", "error")
    return redirect(request.referrer or url_for("upload"))


@app.route("/")
def dashboard():
    with get_db() as connection:
        total_notes = connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        total_recordings = connection.execute(
            "SELECT COUNT(*) FROM notes WHERE audio_file IS NOT NULL"
        ).fetchone()[0]
        recent_notes = connection.execute(
            "SELECT * FROM notes ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
    return render_template(
        "dashboard.html",
        total_notes=total_notes,
        total_recordings=total_recordings,
        recent_notes=recent_notes,
    )


@app.route("/record", methods=["GET", "POST"])
def record():
    if request.method == "POST":
        audio_file = None
        try:
            uploaded = request.files.get("audio")
            if uploaded and uploaded.filename:
                audio_file = save_audio(uploaded)
            else:
                audio_file = request.form.get("audio_name", "").strip() or None
                if audio_file and not validate_audio_name(audio_file):
                    abort(400, description="File audio tidak valid.")
            content = request.form.get("content", "")
            if not content.strip() and audio_file:
                content = transcribe_audio(UPLOAD_DIR / audio_file)
            note_id = create_note(
                request.form.get("title", ""),
                content,
                request.form.get("category", ""),
                audio_file,
            )
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "record.html",
                audio_name=audio_file,
                transcript=request.form.get("content", ""),
            )
        flash("Catatan berhasil disimpan.", "success")
        return redirect(url_for("detail_note", note_id=note_id))
    return render_template("record.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        audio_file = None
        try:
            uploaded = request.files.get("audio")
            if uploaded and uploaded.filename:
                audio_file = save_audio(uploaded)
            else:
                audio_file = request.form.get("audio_name", "").strip() or None
                if audio_file and not validate_audio_name(audio_file):
                    abort(400, description="File audio tidak valid.")
            if not audio_file:
                raise ValueError("Pilih file audio terlebih dahulu.")
            transcript = transcribe_audio(UPLOAD_DIR / audio_file)
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "upload.html",
                transcript="",
                audio_name=audio_file or "",
                title=request.form.get("title", ""),
                category=request.form.get("category", ""),
                content=request.form.get("content", ""),
            )
        return render_template("upload.html", transcript=transcript, audio_name=audio_file)
    return render_template("upload.html", transcript="", audio_name="")


@app.route("/notes/create", methods=["POST"])
def create_note_route():
    audio_file = request.form.get("audio_name", "").strip() or None
    if audio_file and not validate_audio_name(audio_file):
        abort(400, description="File audio tidak valid.")
    try:
        note_id = create_note(
            request.form.get("title", ""),
            request.form.get("content", ""),
            request.form.get("category", ""),
            audio_file,
        )
    except ValueError as error:
        flash(str(error), "error")
        if audio_file:
            return render_template(
                "upload.html",
                transcript=request.form.get("content", ""),
                audio_name=audio_file,
                title=request.form.get("title", ""),
                category=request.form.get("category", ""),
                content=request.form.get("content", ""),
            )
        return render_template(
            "record.html",
            audio_name=None,
            transcript=request.form.get("content", ""),
            title=request.form.get("title", ""),
            category=request.form.get("category", ""),
        )
    flash("Catatan berhasil disimpan.", "success")
    return redirect(url_for("detail_note", note_id=note_id))


@app.route("/notes")
def notes():
    query = request.args.get("q", "").strip()
    with get_db() as connection:
        if query:
            pattern = f"%{query}%"
            note_list = connection.execute(
                """
                SELECT * FROM notes
                WHERE title LIKE ? OR content LIKE ? OR category LIKE ?
                ORDER BY created_at DESC
                """,
                (pattern, pattern, pattern),
            ).fetchall()
        else:
            note_list = connection.execute(
                "SELECT * FROM notes ORDER BY created_at DESC"
            ).fetchall()
    return render_template("notes.html", notes=note_list, query=query)


@app.route("/notes/<int:note_id>")
def detail_note(note_id):
    return render_template("detail_note.html", note=get_note(note_id))


@app.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
def edit_note(note_id):
    note = get_note(note_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("Judul dan isi catatan wajib diisi.", "error")
            return render_template("edit_note.html", note=note)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with get_db() as connection:
            connection.execute(
                """
                UPDATE notes SET title = ?, content = ?, category = ?, updated_at = ?
                WHERE id = ?
                """,
                (title[:150], content, request.form.get("category", "").strip()[:80], now, note_id),
            )
        flash("Perubahan catatan berhasil disimpan.", "success")
        return redirect(url_for("detail_note", note_id=note_id))
    return render_template("edit_note.html", note=note)


@app.route("/notes/<int:note_id>/delete", methods=["POST"])
def delete_note(note_id):
    note = get_note(note_id)
    with get_db() as connection:
        connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    if note["audio_file"]:
        audio_path = validate_audio_name(note["audio_file"])
        if audio_path:
            audio_path.unlink(missing_ok=True)
    flash("Catatan berhasil dihapus.", "success")
    return redirect(url_for("notes"))


@app.route("/notes/<int:note_id>/download/<string:format_name>")
def download_note(note_id, format_name):
    note = get_note(note_id)
    safe_title = secure_filename(note["title"]) or f"catatan-{note_id}"
    if format_name == "txt":
        response = make_response(f"{note['title']}\n\n{note['content']}\n")
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="{safe_title}.txt"'
        return response
    if format_name == "pdf":
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
        from xml.sax.saxutils import escape

        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm
        )
        styles = getSampleStyleSheet()
        content = [
            Paragraph(escape(note["title"]), styles["Title"]),
            Spacer(1, 8 * mm),
        ]
        if note["category"]:
            content.extend(
                [Paragraph(f"Kategori: {escape(note['category'])}", styles["Normal"]), Spacer(1, 4 * mm)]
            )
        for paragraph in note["content"].splitlines():
            content.append(Paragraph(escape(paragraph) or "&nbsp;", styles["BodyText"]))
            content.append(Spacer(1, 2 * mm))
        document.build(content)
        response = make_response(buffer.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{safe_title}.pdf"'
        return response
    abort(404)


@app.route("/uploads/<string:filename>")
def uploaded_audio(filename):
    path = validate_audio_name(filename)
    if path is None:
        abort(404)
    response = make_response(path.read_bytes())
    response.headers["Content-Type"] = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "webm": "audio/webm",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "m4a": "audio/mp4",
        "aiff": "audio/aiff",
        "aif": "audio/aiff",
    }.get(path.suffix.lower().lstrip("."), "application/octet-stream")
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
