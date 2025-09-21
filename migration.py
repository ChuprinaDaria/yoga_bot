from yogaxbot.db import SessionLocal
from sqlalchemy import text


def migrate_add_fields() -> None:
    session = SessionLocal()
    try:
        session.execute(text(
            """
            ALTER TABLE users ADD COLUMN course_feedback_given BOOLEAN DEFAULT FALSE;
            """
        ))
    except Exception as e:
        print(f"Migration note: course_feedback_given may already exist: {e}")
    try:
        session.execute(text(
            """
            ALTER TABLE users ADD COLUMN course_extension_used BOOLEAN DEFAULT FALSE;
            """
        ))
    except Exception as e:
        print(f"Migration note: course_extension_used may already exist: {e}")
    try:
        session.execute(text(
            """
            ALTER TABLE users ADD COLUMN feedback_message_id INTEGER;
            """
        ))
    except Exception as e:
        print(f"Migration note: feedback_message_id may already exist: {e}")
    try:
        session.execute(text(
            """
            ALTER TABLE users ADD COLUMN status_history TEXT;
            """
        ))
    except Exception as e:
        print(f"Migration note: status_history may already exist: {e}")
    finally:
        session.commit()
        session.close()


if __name__ == "__main__":
    migrate_add_fields()


