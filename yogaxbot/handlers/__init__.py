from aiogram import Router

router = Router()

# Імпортуємо підмодулі, які реєструють свої маршрути на спільному router
from . import common  # noqa: F401
from . import start  # noqa: F401
from . import admin  # noqa: F401
from . import workouts  # noqa: F401
from . import broadcast  # noqa: F401
from . import tasks  # noqa: F401
from . import course_feedback  # noqa: F401
