from models import db, User, Role, Book, Genre
from werkzeug.security import generate_password_hash
from app import app

with app.app_context():
    db.create_all()

    admin_role = Role(name='Администратор', description='Полный доступ')
    moder_role = Role(name='Модератор', description='Редактирование книг и рецензий')
    user_role = Role(name='Пользователь', description='Может оставлять рецензии')

    db.session.add_all([admin_role, moder_role, user_role])
    db.session.commit()

    users = [
        User(username='admin', password_hash=generate_password_hash('adminpass'),
             last_name='Админов', first_name='Админ', middle_name='Админович', role=admin_role),
        User(username='mod', password_hash=generate_password_hash('modpass'),
             last_name='Модеров', first_name='Мод', middle_name='Модович', role=moder_role),
        User(username='user', password_hash=generate_password_hash('userpass'),
             last_name='Юзеров', first_name='Юзер', middle_name='Юзерович', role=user_role)
    ]
    db.session.add_all(users)

    genres = [Genre(name=name) for name in ['Фантастика', 'Приключения', 'Научные']]
    db.session.add_all(genres)
    db.session.commit()

    books = [
        Book(title='Звёздный путь', description='Про космос и приключения.', year=2020,
             publisher='КосмоИздат', author='Иван Космонавтов', pages=320,
             genres=[genres[0], genres[1]]),
        Book(title='Мозг и разум', description='Научные исследования о мозге.', year=2021,
             publisher='НаукаПресс', author='Доктор Разумов', pages=280,
             genres=[genres[2]]),
        Book(title='Тайна третьей планеты', description='Классика советской фантастики.', year=1981,
             publisher='Детгиз', author='Кир Булычёв', pages=190,
             genres=[genres[0], genres[1]]),
        Book(title='Путешествие к центру Земли', description='Приключенческий роман.', year=1864,
             publisher='Hetzel', author='Жюль Верн', pages=320,
             genres=[genres[1]]),
        Book(title='Краткая история времени', description='Популярная наука о космосе и времени.', year=1988,
             publisher='Bantam Books', author='Стивен Хокинг', pages=256,
             genres=[genres[2]]),
        Book(title='Дети капитана Гранта', description='Приключения и открытия.', year=1868,
             publisher='Hetzel', author='Жюль Верн', pages=350,
             genres=[genres[1]]),
        Book(title='Основание', description='Научно-фантастическая сага о будущем человечества.', year=1951,
             publisher='Gnome Press', author='Айзек Азимов', pages=255,
             genres=[genres[0]]),
        Book(title='Нейромант', description='Киберпанк-роман о виртуальной реальности.', year=1984,
             publisher='Ace', author='Уильям Гибсон', pages=271,
             genres=[genres[0]]),
        Book(title='Квантовая механика', description='Введение в квантовую физику.', year=2023,
             publisher='НаукаПресс', author='Профессор Квантов', pages=412,
             genres=[genres[2]]),
        Book(title='Марсианин', description='История выживания на Марсе.', year=2011,
             publisher='Crown', author='Энди Вейер', pages=369,
             genres=[genres[0], genres[2]]),
        Book(title='Вокруг света за 80 дней', description='Классическое приключение.', year=1872,
             publisher='Hetzel', author='Жюль Верн', pages=304,
             genres=[genres[1]]),
        Book(title='Теория струн', description='Современная физическая теория.', year=2024,
             publisher='НаукаПресс', author='Мария Струнина', pages=520,
             genres=[genres[2]]),
        Book(title='Солярис', description='Философская фантастика о контакте.', year=1961,
             publisher='МИР', author='Станислав Лем', pages=286,
             genres=[genres[0]]),
        Book(title='В горах безумия', description='Мистические приключения в Антарктиде.', year=1936,
             publisher='Astounding', author='Говард Лавкрафт', pages=186,
             genres=[genres[0], genres[1]]),
        Book(title='Параллельные вселенные', description='Теория мультивселенной.', year=2025,
             publisher='НаукаПресс', author='Алекс Мультиверс', pages=345,
             genres=[genres[2]])
    ]

    db.session.add_all(books)
    db.session.commit()
    print('✅ Пользователи, роли, жанры и книги успешно добавлены.')
