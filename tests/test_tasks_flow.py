import asyncio
import pytest
from datetime import datetime, timedelta
from types import SimpleNamespace

from yogaxbot.handlers.tasks import trial_maintenance, cleanup_old_messages
from yogaxbot.db import SessionLocal, User


class DummyBot:
    def __init__(self):
        self.sent = []
        self.deleted = []

    async def send_message(self, chat_id, text, reply_markup=None, protect_content=None):
        self.sent.append(("message", chat_id, text))
        return SimpleNamespace(message_id=len(self.sent))

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


@pytest.fixture(autouse=True)
def _clean_db():
    # ensure clean users table between tests
    session = SessionLocal()
    try:
        session.query(User).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.query(User).delete()
        session.commit()
    finally:
        session.close()


@pytest.mark.asyncio
async def test_reminder_every_3_days_and_finish_flow(monkeypatch):
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        user = User(
            user_id=123,
            status='trial_active',
            trial_started_at=now - timedelta(days=5),
            trial_expires_at=now + timedelta(days=12),
            last_reminder_at=now - timedelta(days=3),
            course_feedback_given=False,
        )
        session.add(user)
        session.commit()
    finally:
        session.close()

    bot = DummyBot()
    await trial_maintenance(bot)

    # one reminder should be sent with days_left included
    assert any("Залишилось" in msg[2] for msg in bot.sent)


@pytest.mark.asyncio
async def test_course_finish_prompts_feedback(monkeypatch):
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        user = User(
            user_id=456,
            status='trial_active',
            trial_started_at=now - timedelta(days=16),
            trial_expires_at=now - timedelta(hours=1),
            last_reminder_at=now - timedelta(days=4),
            course_feedback_given=False,
        )
        session.add(user)
        session.commit()
    finally:
        session.close()

    bot = DummyBot()
    await trial_maintenance(bot)

    # Should send finish message asking for feedback
    assert any("відкритий курс завершено" in msg[2].lower() for msg in bot.sent)


@pytest.mark.asyncio
async def test_cleanup_after_extension_24h(monkeypatch):
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        user = User(
            user_id=789,
            status='trial_expired',
            trial_started_at=now - timedelta(days=17),
            trial_expires_at=now - timedelta(days=1, hours=1),
            course_extension_used=True,
            course_feedback_given=True,
            feedback_message_id=111,
        )
        session.add(user)
        session.commit()
    finally:
        session.close()

    bot = DummyBot()
    await cleanup_old_messages(bot)

    # The old message should be attempted to delete and a final message sent
    assert (789, 111) in bot.deleted
    assert any("завершено" in msg[2].lower() for msg in bot.sent)
