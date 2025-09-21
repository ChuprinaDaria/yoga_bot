import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import NoResultFound

# --- SQLAlchemy setup ---
Base = declarative_base()
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///yogaxbot.db')
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# --- Моделі ---
class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True, autoincrement=False)
    status = Column(String, nullable=False, default='new')
    trial_started_at = Column(DateTime, nullable=True)
    trial_expires_at = Column(DateTime, nullable=True)
    last_reminder_at = Column(DateTime, nullable=True)
    extension_used = Column(Boolean, default=False, nullable=False)
    course_feedback_given = Column(Boolean, default=False)
    course_extension_used = Column(Boolean, default=False)
    feedback_message_id = Column(Integer, nullable=True)
    status_history = Column(Text, nullable=True)
    blocked = Column(Boolean, default=False, nullable=False)
    start_pending_at = Column(DateTime, nullable=True)
    pinned_menu_message_id = Column(Integer, nullable=True)
    workout_messages = relationship('WorkoutMessage', back_populates='user')

class WorkoutMessage(Base):
    __tablename__ = 'workout_messages'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    chat_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    user = relationship('User', back_populates='workout_messages')

class TextBlock(Base):
    __tablename__ = 'text_blocks'
    key = Column(String, primary_key=True)
    content = Column(Text, nullable=False)

class WorkoutCatalog(Base):
    __tablename__ = 'workout_catalogs'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    caption = Column(Text, nullable=False)
    url = Column(String, nullable=True)
    photo_file_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

class BroadcastLog(Base):
    __tablename__ = 'broadcast_logs'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    kind = Column(String, nullable=False)
    payload_preview = Column(Text, nullable=True)
    total = Column(Integer, nullable=False)
    success = Column(Integer, nullable=False)
    failed = Column(Integer, nullable=False)

# --- Створення таблиць ---
Base.metadata.create_all(engine)

# --- Дефолтні тексти ---
DEFAULT_TEXTS = {
    'WELCOME': (
        '<b>Привіт! Вітаю вас у моїй онлайн школі йоги - на безкоштовному курсі</b>. '
        '<i>Я Сергій Дорошенко - Харківський практик йоги і сертифікований викладач із 2009 року.</i>\n\n'
        'Протягом кількох днів ви спробуєте кілька занять із моєї онлайн йога студії і відчуєте (якщо позаймаєтесь) на собі ефект базових тренувань. '
        'Тут у чаті будуть посилання на заняття та кілька лекцій.\n\n'
        'Сподіваюсь, ви знайдете час займатися і відчути на собі ефект.\n\n'
        'Всі свої запитання ви можете писати у чат школи йоги: посилання https://t.me/+xA1DOM00cc4zYmRi '
        'у вигляді кнопки "чат школи йоги" — я особисто відповідаю на всі запитання.'
    ),
    'COURSE_FINISHED': (
        'Доброго дня! Нагадаю що відкритий курс завершено\n'
        'Чи вдалося вам займатися у ці дні?'
    ),
    'FEEDBACK_POSITIVE': (
        'Супер,) Сподіваюсь вам було цікаво і є бажання продовжувати заняття разом.\n'
        'Спеціально для учасників відкритого курсу діє знижка на перший абонемент у школу йоги:'
    ),
    'FEEDBACK_NEGATIVE': (
        'Пропоную вам всеж таки спробувати :)\n'
        'Коли знайдете час - приходьте і починайте\n'
        'Курс буде доступен ще 1 день'
    ),
    'FINAL_COURSE_END': (
        'Відкритий курс йоги завершено - буду радий будь яким вашим запитанням'
    ),
    'REMINDER_WITH_DAYS': (
        'Залишилось "{days_left} днів" дії безкоштовного курсу йоги.\n'
        'Розумію як важко організувати себе для занять онлайн тому такі лагідні нагадування.\n'
        'Сорі що відволікаю\n\n'
        'Якщо ви вже почали займатися і у вас є запитання - буду радий вас чути:'
    ),
    'OPEN_COURSE_INTRO': (
        'У відкритому курсі буде 6 безкоштовних тренувань на різні теми.\n'
        '<b>Заняття безкоштовно у доступі 15 днів</b> і після цього періоду я буду радий отримати зворотній зв’язок та розробити для вас персональну програму занять.\n\n'
        'Загалом у школі йоги 300 тематичних практик і тренувань — від початкового рівня до інтенсивів та матеріалів для підготовки викладачів йоги.\n'
        'Але це все потім — давайте почнемо із відкритого курсу для знайомства.\n\n'
        '<i>Я надсилаю вам 6 тренувань і дуже раджу спробувати всі — вони дуже різні і працюють із різними ділянками тіла і емоцій</i>.'
    ),
    'START_NOW_MSG': (
        'Готові почати? Натисніть кнопку нижче!'
    ),
    'REMINDER_TPL': (
        'Нагадування: не забудьте сьогодні потренуватися!\n'
        'Ваш прогрес важливий для нас.'
    ),
    'AFTER_EXPIRE': (
        'Термін дії безкоштовного доступу завершився.\n'
        'Оформіть абонемент, щоб продовжити тренування.'
    ),
    'DISCOUNT_MSG': (
        'Тільки сьогодні! Знижка на абонемент для нових користувачів.\n'
        'Поспішайте скористатися пропозицією.'
    ),
}

DISCOUNT_DEEP_LINK = 'https://t.me/yogaxbot?start=discount2024'

# --- Хелпер для текстів ---
def T_session():
    return SessionLocal()

async def T(key, **fmt):
    session = T_session()
    try:
        block = session.query(TextBlock).filter_by(key=key).first()
        text = block.content if block else DEFAULT_TEXTS.get(key, key)
    finally:
        session.close()
    if fmt:
        try:
            text = text.format(**fmt)
        except Exception:
            pass
    return text


def log_status_change(user, old_status, new_status, reason: str = "") -> None:
    import json
    import datetime as _dt

    if not getattr(user, 'status_history', None):
        user.status_history = "[]"

    try:
        history = json.loads(user.status_history)
    except Exception:
        history = []
    history.append({
        "timestamp": _dt.datetime.utcnow().isoformat(),
        "from": old_status,
        "to": new_status,
        "reason": reason,
    })
    try:
        user.status_history = json.dumps(history)
    except Exception:
        # У разі неможливості серіалізувати — ігноруємо, щоб не ламати логіку
        pass

def seed_free_workouts_if_empty() -> None:
    session = SessionLocal()
    try:
        has_any = session.query(WorkoutCatalog).first() is not None
        if has_any:
            return
        items = [
            {
                'code': '360',
                'caption': "мʼяка ранкова практика на пробудження і зняття скутості. Зміцнення і звільнення. 29 хвилин",
                'url': 'https://vimeopro.com/seryogaji/fem'
            },
            {
                'code': '159',
                'caption': "Одне із найпопулярніших тренувань у школі йоги — звільнення лопаток та грудного відділу від напруги. 35 хвилин",
                'url': 'https://vimeopro.com/seryogaji/dy'
            },
            {
                'code': '351',
                'caption': "Мʼяка ранкова силова руханка на кожен день — 33 хвилини",
                'url': 'https://vimeopro.com/seryogaji/er'
            },
            {
                'code': '287',
                'caption': "Практика на звільнення хребта від скутості та повне розслаблення мʼязів спини",
                'url': 'https://vimeopro.com/seryogaji/wdf'
            },
            {
                'code': '358',
                'caption': "Звільнення тазу і попереку. Сила та гнучкість. 48 хвилин",
                'url': 'https://vimeopro.com/seryogaji/duo'
            },
            {
                'code': '193',
                'caption': "Універсальна практика по роботі із всім тілом: і силові, і трохи балансів, і гнучкість, і пробудження. 37 хвилин",
                'url': 'https://vimeopro.com/seryogaji/wq'
            },
        ]
        for it in items:
            existing = session.query(WorkoutCatalog).filter_by(code=it['code']).first()
            if existing:
                existing.caption = it['caption']
                existing.url = it['url']
                existing.is_active = True
            else:
                session.add(WorkoutCatalog(
                    code=it['code'],
                    caption=it['caption'],
                    url=it['url'],
                    photo_file_id='',
                    is_active=True
                ))
        session.commit()
    finally:
        session.close()
