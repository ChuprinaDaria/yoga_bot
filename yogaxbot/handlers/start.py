import logging
import os
import asyncio
from aiogram import Bot
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from yogaxbot.db import SessionLocal, User, WorkoutCatalog, WorkoutMessage, T, TextBlock
from . import router
from .common import get_main_reply_keyboard, menu_text

logger = logging.getLogger(__name__)

async def send_welcome(user_id, chat_id, bot: Bot):
    # 0) Локальний файл у корені проєкту (за замовчуванням: photo_YYYY-MM-DD_..jpg або шлях з .env)
    default_name = os.getenv('WELCOME_PHOTO_PATH', 'photo_2025-09-21_09-36-24.jpg')
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    local_path = os.path.join(project_root, default_name)

    # Статична кнопка для старту курсу
    btn_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='ПОЧАТИ БЕЗКОШТОВНИЙ КУРС', callback_data='start_first_workout')]
    ])

    if os.path.exists(local_path):
        try:
            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(local_path), caption=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)
            return
        except Exception as e:
            logger.warning("Failed to send local welcome photo at %s: %s", local_path, e)

    # 1) .env URL
    photo_url = os.getenv('WELCOME_PHOTO_URL')
    if photo_url:
        try:
            await bot.send_photo(chat_id=chat_id, photo=photo_url, caption=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)
            return
        except Exception as e:
            logger.warning("Failed to send welcome photo by URL %s: %s", photo_url, e)

    # 2) Текстовий блок з URL
    session = SessionLocal()
    try:
        block = session.query(TextBlock).filter_by(key='WELCOME_PHOTO').first()
        url = block.content if block else None
    finally:
        session.close()
    if url:
        try:
            await bot.send_photo(chat_id=chat_id, photo=url, caption=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)
            return
        except Exception as e:
            logger.warning("Failed to send welcome photo by TextBlock URL %s: %s", url, e)

    # Фолбек: тільки текст
    await bot.send_message(chat_id=chat_id, text=await T('WELCOME'), reply_markup=btn_kb, protect_content=True)

async def send_six_workouts(user_id, chat_id, bot: Bot):
    session = SessionLocal()
    workouts = session.query(WorkoutCatalog).all() # Прибираємо фільтр is_active=True
    if not workouts:
        session.close()
        return
    sent_count = 0
    for w in workouts[:6]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='Перейти до тренування', url=w.url)
        ]]) if w.url else None
        msg = None
        if w.photo_file_id:
            try:
                msg = await bot.send_photo(chat_id, w.photo_file_id, caption=w.caption, reply_markup=kb, protect_content=True)
            except Exception as e:
                logger.warning("Failed to send workout photo code=%s: %s; fallback to text", getattr(w, 'code', '?'), e)
        if msg is None:
            msg = await bot.send_message(chat_id, w.caption, reply_markup=kb, protect_content=True)
        session.add(WorkoutMessage(user_id=user_id, chat_id=chat_id, message_id=msg.message_id))
        sent_count += 1
    session.commit()
    session.close()
    
    # Після відправки всіх уроків — через 20 секунд відправити рекомендацію (лише якщо щось надіслали)
    if sent_count > 0:
        await asyncio.sleep(20)
        await bot.send_message(chat_id, await T('POST_LESSONS'), protect_content=True)

async def start_course_flow(user_id: int, chat_id: int, bot: Bot, forced: bool = False):
    """
    Централізована функція для запуску курсу.
    Завжди надсилає інтро, чекає 10 сек, реєструє тріал і надсилає вправи.
    Якщо викликано автоматично (forced=False), спрацює лише коли встановлено start_pending_at і настав час.
    """
    logger.info(f"Executing start_course_flow for user_id={user_id} forced={forced}")

    # Перевірка відкладеного запуску для авто-викликів
    if not forced:
        session_check = SessionLocal()
        try:
            u = session_check.query(User).get(user_id)
            now_local = datetime.now()
            if not u or not getattr(u, 'start_pending_at', None) or now_local < u.start_pending_at:
                logger.info("Auto-start skipped for user_id=%s: pending missing or not yet time", user_id)
                return
            # скинемо pending одразу, щоб уникнути дублювань
            u.start_pending_at = None
            session_check.commit()
        finally:
            session_check.close()

    # 1. Завжди надсилаємо інтро
    await bot.send_message(chat_id, await T('OPEN_COURSE_INTRO'), protect_content=True)
    
    # 2. Чекаємо 10 секунд
    await asyncio.sleep(10)
    
    # 3. Реєструємо тріал (якщо треба) і надсилаємо вправи
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if not user:
            user = User(user_id=user_id, status='new')
            session.add(user)
            session.commit()

        # Ініціалізуємо тріал, якщо ще не активний
        if user.status != 'trial_active':
            now = datetime.utcnow()
            user.status = 'trial_active'
            user.trial_started_at = now
            user.trial_expires_at = now + timedelta(days=15)
            user.last_reminder_at = now
            session.commit()

        # Надсилаємо тренування завжди після інтро
        await send_six_workouts(user_id, chat_id, bot)
    finally:
        session.close()


@router.message(Command('start'))
async def cmd_start(message: Message, bot: Bot, **data):
    scheduler: AsyncIOScheduler = data.get('scheduler')
    user_id = message.from_user.id
    # ensure user exists
    session = SessionLocal()
    user = session.query(User).get(user_id)
    if not user:
        user = User(user_id=user_id, status='new')
        session.add(user)
        session.commit()
    session.close()
    await send_welcome(user_id, message.chat.id, bot)
    try:
        await bot.send_message(message.chat.id, '\u2063', reply_markup=get_main_reply_keyboard())
    except TelegramBadRequest:
        await bot.send_message(message.chat.id, '.', reply_markup=get_main_reply_keyboard())
   
    # Якщо тріал завершився — не плануємо автозапуск і показуємо повідомлення
    session_chk = SessionLocal()
    try:
        u = session_chk.query(User).get(user_id)
        expired = bool(u and u.trial_expires_at and datetime.utcnow() >= u.trial_expires_at)
        blocked_status = bool(u and getattr(u, 'status', '') in {'trial_expired', 'open', 'active'})
    finally:
        session_chk.close()

    if expired or blocked_status:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/seryogaji')]])
        await bot.send_message(message.chat.id, await T('AFTER_EXPIRE'), reply_markup=kb, protect_content=True)
        return

    if scheduler:
        run_at = datetime.now() + timedelta(minutes=1)
        logger.info("Scheduling run_start_open_course at %s for user_id=%s", run_at.isoformat(), user_id)
        # Позначити очікування автозапуску
        session2 = SessionLocal()
        try:
            u = session2.query(User).get(user_id)
            if u:
                u.start_pending_at = run_at
                session2.commit()
        finally:
            session2.close()
        scheduler.add_job(start_course_flow, 'date', run_date=run_at, args=[user_id, message.chat.id, bot])

@router.message(F.text == '🧘‍♀️ Безкоштовний курс')
async def handle_free_course(message: Message, bot: Bot):
    user_id = message.from_user.id
    session = SessionLocal()
    try:
        u = session.query(User).get(user_id)
        expired = bool(u and u.trial_expires_at and datetime.utcnow() >= u.trial_expires_at)
        blocked_status = bool(u and getattr(u, 'status', '') in {'trial_expired', 'open', 'active'})
    finally:
        session.close()

    if expired or blocked_status:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/seryogaji')]])
        await message.answer(await T('AFTER_EXPIRE'), reply_markup=kb)
        return

    await start_course_flow(user_id, message.chat.id, bot, forced=True)



@router.message(F.text == '💬 Чат школи йоги')
async def handle_chat_link(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Перейти до чату', url='https://t.me/+xA1DOM00cc4zYmRi')]])
    await message.answer('Приєднуйтесь до нашого чату:', reply_markup=kb)



@router.message(Command('contact'))
@router.message(F.text.in_({'Написати тренеру', '✉️Написати тренеру'}))
async def handle_write_coach(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/seryogaji')]])
    await message.answer('Напишіть тренеру, щоб підібрати персональну програму:', reply_markup=kb)

# Видалено хендлер "Купити абонемент" — замість цього пропонуємо писати тренеру
@router.callback_query(F.data == 'start_first_workout')
async def cb_start_first_workout(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    # Відповідаємо на callback одразу, щоб уникнути "query is too old"
    try:
        await callback.answer()
    except Exception:
        pass
    session = SessionLocal()
    try:
        u = session.query(User).get(user_id)
        expired = bool(u and u.trial_expires_at and datetime.utcnow() >= u.trial_expires_at)
        blocked_status = bool(u and getattr(u, 'status', '') in {'trial_expired', 'open', 'active'})
    finally:
        session.close()

    if expired or blocked_status:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Написати тренеру', url='https://t.me/seryogaji')]])
        await callback.message.answer(await T('AFTER_EXPIRE'), reply_markup=kb)
        await callback.answer()
        return

    await start_course_flow(user_id, chat_id, bot, forced=True)

