from flask import Flask, render_template, redirect, url_for, flash, request, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Book, Genre, Cover, Review, BookViewLog
from forms import LoginForm, BookForm, ReviewForm
import os
import hashlib
from io import StringIO
import csv
import datetime
import codecs
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from datetime import timedelta

def get_popular_books(limit=5, months=3):
    three_months_ago = datetime.datetime.utcnow() - timedelta(days=90)
    return (
        db.session.query(Book, func.count(BookViewLog.id).label('views'))
        .join(BookViewLog)
        .filter(BookViewLog.timestamp >= three_months_ago)
        .group_by(Book)
        .order_by(db.text('views DESC'))
        .limit(limit)
        .all()
    )

def get_recent_books(limit=5, user_id=None, session_id=None, ip_address=None):
    query = (
        db.session.query(Book)
        .join(BookViewLog)
        .filter(BookViewLog.timestamp >= (datetime.datetime.utcnow() - timedelta(days=30)))
    )
    
    if user_id:
        query = query.filter(BookViewLog.user_id == user_id)
    elif session_id:
        query = query.filter(BookViewLog.session_id == session_id)
    else:
        query = query.filter(BookViewLog.ip_address == ip_address)
    
    return query.order_by(BookViewLog.timestamp.desc()).distinct().limit(limit).all()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/covers'

# --- Init ---
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Для выполнения данного действия необходимо пройти процедуру аутентификации.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Главная с пагинацией ---
@app.route('/')
@app.route('/page/<int:page>')
def index(page=1):
    per_page = 6
    books = Book.query.order_by(Book.year.desc()).paginate(page=page, per_page=per_page)
    
    # Получаем популярные книги
    popular_books = get_popular_books(limit=5)
    
    # Получаем недавно просмотренные книги
    recent_books = None
    if current_user.is_authenticated:
        recent_books = get_recent_books(user_id=current_user.id)
    else:
        session_id = request.cookies.get('session')
        if session_id:
            recent_books = get_recent_books(session_id=session_id)
        else:
            recent_books = get_recent_books(ip_address=request.remote_addr)
    
    return render_template('index.html', 
                         books=books,
                         popular_books=popular_books,
                         recent_books=recent_books)

# --- Просмотр книги ---
@app.route('/book/<int:book_id>')
def view_book(book_id):
    book = Book.query.get_or_404(book_id)
    reviews = Review.query.filter_by(book_id=book_id).order_by(Review.timestamp.desc()).all()

    # Проверка лимита просмотров
    user_id = current_user.id if current_user.is_authenticated else None
    session_id = request.cookies.get('session')
    ip_address = request.remote_addr

    if BookViewLog.check_daily_limit(book_id, user_id, session_id, ip_address):
        # Логирование просмотра
        view_log = BookViewLog(
            book_id=book_id,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address
        )
        db.session.add(view_log)
        db.session.commit()

    user_review = None
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()

    review_form = ReviewForm()           # форма для рецензии
    return render_template('view_book.html', book=book, reviews=reviews, user_review=user_review, review_form=review_form)

# --- Добавление рецензии ---
@app.route('/review/<int:book_id>', methods=['POST'])
@login_required
def add_review(book_id):
    book = Book.query.get_or_404(book_id)
    form = ReviewForm()

    # Проверка: не оставлял ли пользователь уже рецензию на эту книгу
    existing_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    if existing_review:
        flash('Вы уже оставили рецензию на эту книгу.', 'warning')
        return redirect(url_for('view_book', book_id=book_id))

    if form.validate_on_submit():
        print('Форма прошла валидацию!')  # Лог в консоль
        review = Review(
            text=form.text.data,
            rating=form.rating.data,
            user_id=current_user.id,
            book_id=book_id
        )
        db.session.add(review)
        db.session.commit()
        flash('Рецензия добавлена!', 'success')
        return redirect(url_for('view_book', book_id=book_id))
    else:
        if request.method == 'POST':
            print('Форма НЕ прошла валидацию.')
            print(form.errors)

    return render_template('review_form.html', form=form, book=book)



# --- Добавление книги ---
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_book():
    print(f"Метод: {request.method}")

    # Проверка прав
    if current_user.role.name != 'Администратор':
        flash('У вас недостаточно прав для выполнения данного действия.', 'danger')
        print("Пользователь не админ!")
        return redirect(url_for('index'))

    form = BookForm()
    form.genres.choices = [(g.id, g.name) for g in Genre.query.all()]  # список жанров в форме

    if form.validate_on_submit():
        print("Форма прошла валидацию!")

        # Создание новой книги
        book = Book(
            title=form.title.data,
            description=form.description.data,
            year=form.year.data,
            publisher=form.publisher.data,
            author=form.author.data,
            pages=form.pages.data
        )

        # Связывание жанров
        selected_genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
        book.genres = selected_genres

        db.session.add(book)
        db.session.commit()

        # Обработка обложки
        if form.cover.data:
            file = form.cover.data
            content = file.read()
            md5 = hashlib.md5(content).hexdigest()

            existing_cover = Cover.query.filter_by(md5_hash=md5).first()
            if existing_cover:
                book.cover = existing_cover
            else:
                filename = f"{book.id}_{secure_filename(file.filename)}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(file_path, 'wb') as f:
                    f.write(content)
                new_cover = Cover(filename=filename, mimetype=file.mimetype, md5_hash=md5, book=book)
                db.session.add(new_cover)

        db.session.commit()

        flash('Книга успешно добавлена!', 'success')
        return redirect(url_for('index'))
    else:
        if request.method == 'POST':
            print("Форма НЕ прошла валидацию.")
            print(form.errors)  # вывод ошибок в консоль

    return render_template('book_form.html', form=form, show_cover_field=True)

# --- Редактирование книги ---
@app.route('/edit/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    if current_user.role.name not in ['Администратор', 'Модератор']:
        flash('У вас недостаточно прав.', 'danger')
        return redirect(url_for('index'))

    form = BookForm(obj=book)
    form.genres.choices = [(g.id, g.name) for g in Genre.query.all()]

    if request.method == 'GET':
        form.genres.data = [g.id for g in book.genres]

    if form.validate_on_submit():
        book.title = form.title.data
        book.description = form.description.data
        book.year = form.year.data
        book.publisher = form.publisher.data
        book.author = form.author.data
        book.pages = form.pages.data
        book.genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()

        db.session.commit()
        flash('Книга обновлена', 'success')
        return redirect(url_for('view_book', book_id=book.id))

    return render_template('book_form.html', form=form, title='Редактировать книгу', show_cover_field=False)

# --- Удаление книги ---
@app.route('/delete/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    if current_user.role.name != 'Администратор':
        flash('У вас недостаточно прав для выполнения данного действия.', 'danger')
        return redirect(url_for('index'))
    
    book = Book.query.get_or_404(book_id)
    
    # Сначала удаляем все записи просмотров
    BookViewLog.query.filter_by(book_id=book_id).delete()
    
    # Удаляем обложку если есть
    if book.cover:
        cover_path = os.path.join(app.config['UPLOAD_FOLDER'], book.cover.filename)
        if os.path.exists(cover_path):
            os.remove(cover_path)
    
    # Удаляем саму книгу
    db.session.delete(book)
    
    try:
        db.session.commit()
        flash('Книга удалена', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Ошибка при удалении книги', 'danger')
        print(f"Error: {str(e)}")
    
    return redirect(url_for('index'))

# --- Вход ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            flash('Успешный вход', 'success')
            return redirect(url_for('index'))
        flash('Неверный логин или пароль', 'danger')
    return render_template('login.html', form=form)

# --- Выход ---
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

# --- Статистика просмотров ---
@app.route('/statistics')
@app.route('/statistics/page/<int:page>')
@login_required
def statistics(page=1):
    if current_user.role.name != 'Администратор':
        flash('У вас недостаточно прав для просмотра статистики.', 'danger')
        return redirect(url_for('index'))

    week_ago = datetime.datetime.utcnow() - timedelta(days=7)
    month_ago = datetime.datetime.utcnow() - timedelta(days=30)
    
    # Детальная статистика просмотров
    per_page = 10
    book_stats = []
    books = Book.query.all()
    
    for book in books:
        views = BookViewLog.query.filter_by(book_id=book.id)
        stats = {
            'book': book,
            'total_views': views.count(),
            'monthly_views': views.filter(BookViewLog.timestamp >= month_ago).count(),
            'weekly_views': views.filter(BookViewLog.timestamp >= week_ago).count(),
            'first_view': views.order_by(BookViewLog.timestamp.asc()).first().timestamp if views.first() else None,
            'last_view': views.order_by(BookViewLog.timestamp.desc()).first().timestamp if views.first() else None
        }
        book_stats.append(stats)
    
    book_stats.sort(key=lambda x: x['total_views'], reverse=True)
    
    # Создаем пагинацию вручную
    total = len(book_stats)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_stats = book_stats[start:end]
    
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page
    }
    
    return render_template('statistics.html', 
                         book_stats=paginated_stats,
                         pagination=pagination)

# --- Журнал действий ---
@app.route('/activity_log')
@app.route('/activity_log/page/<int:page>')
@login_required
def activity_log(page=1):
    if current_user.role.name != 'Администратор':
        flash('У вас недостаточно прав для просмотра журнала.', 'danger')
        return redirect(url_for('index'))
    
    per_page = 10
    log_query = BookViewLog.query.options(
        db.joinedload(BookViewLog.user),
        db.joinedload(BookViewLog.book)
    ).order_by(BookViewLog.timestamp.desc())
    
    log_entries = log_query.paginate(page=page, per_page=per_page)
    return render_template('activity_log.html', activity_log=log_entries)

# --- Экспорт статистики ---
@app.route('/export_statistics')
@login_required
def export_statistics():
    if current_user.role.name != 'Администратор':
        flash('У вас недостаточно прав для выполнения данного действия.', 'danger')
        return redirect(url_for('statistics'))

    # Подготовка данных
    week_ago = datetime.datetime.utcnow() - timedelta(days=7)
    month_ago = datetime.datetime.utcnow() - timedelta(days=30)
    
    book_stats = []
    for book in Book.query.all():
        views = BookViewLog.query.filter_by(book_id=book.id)
        stats = [
            book.title,
            book.author,
            str(views.count()),
            str(views.filter(BookViewLog.timestamp >= month_ago).count()),
            str(views.filter(BookViewLog.timestamp >= week_ago).count()),
            views.order_by(BookViewLog.timestamp.asc()).first().timestamp.strftime('%d.%m.%Y %H:%M') if views.first() else '-',
            views.order_by(BookViewLog.timestamp.desc()).first().timestamp.strftime('%d.%m.%Y %H:%M') if views.first() else '-'
        ]
        book_stats.append(stats)

    # Создаем CSV
    output = StringIO()
    output.write(codecs.BOM_UTF8.decode('utf-8'))
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, dialect='excel')
    
    writer.writerow([
        'Название книги',
        'Автор',
        'Всего просмотров',
        'За последний месяц',
        'За последнюю неделю',
        'Первый просмотр',
        'Последний просмотр'
    ])
    
    for stats in sorted(book_stats, key=lambda x: int(x[2]) if x[2] != '-' else 0, reverse=True):
        writer.writerow(stats)

    # Отправляем файл
    output.seek(0)
    response = make_response(output.getvalue())
    current_date = datetime.datetime.now().strftime('%d_%m_%Y_%H_%M')
    response.headers["Content-Disposition"] = f"attachment; filename=statistics_{current_date}.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return response

@app.route('/export_activity_log')
@login_required
def export_activity_log():
    if current_user.role.name != 'Администратор':
        flash('У вас недостаточно прав для выполнения данного действия.', 'danger')
        return redirect(url_for('activity_log'))

    # Получаем все записи журнала с загрузкой связей
    logs = BookViewLog.query.options(
        db.joinedload(BookViewLog.user),
        db.joinedload(BookViewLog.book)
    ).order_by(BookViewLog.timestamp.desc()).all()

    # Создаем CSV
    output = StringIO()
    output.write(codecs.BOM_UTF8.decode('utf-8'))
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, dialect='excel')
    
    writer.writerow([
        'Дата и время',
        'Пользователь',
        'Книга',
        'IP адрес',
        'Идентификатор сессии'
    ])
    
    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%d.%m.%Y %H:%M'),
            log.user.username if log.user else 'Гость',
            log.book.title,
            log.ip_address or '-',
            log.session_id or '-'
        ])

    # Отправляем файл
    output.seek(0)
    response = make_response(output.getvalue())
    current_date = datetime.datetime.now().strftime('%d_%m_%Y_%H_%M')
    response.headers["Content-Disposition"] = f"attachment; filename=activity_log_{current_date}.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return response

if __name__ == '__main__':
    if not os.path.exists('library.db'):
        with app.app_context():
            db.create_all()
            print('✅ База данных создана')
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
