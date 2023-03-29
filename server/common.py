from schedule import Scheduler
from session.manager import SessionManager


class GlobalObjectClass:
    def __init__(self):
        self.text: str = ""
        self.database: str = ""
        self.session_manager: SessionManager | None = None
        self.scheduler: Scheduler | None = None


globalObject = GlobalObjectClass()
