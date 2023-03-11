from session import SessionManager


class GlobalObjectClass:
    def __init__(self):
        self.text: str = ""
        self.config_path: str = ""
        self.database: str = ""
        self.session_manager: SessionManager = None


globalObject = GlobalObjectClass()
