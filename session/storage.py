import json
import os.path
from dataclasses import asdict

from memory import CurrentConversation


class SessionStorage:
    def __init__(self, d: str, type_: str, params: dict):
        self.__path: str = d
        self.__session_type: str = type_
        self.__params: dict = params
        self.current: CurrentConversation = None

    def load(self) -> bool:
        try:
            with open(os.path.join(self.__path, "current.json"), "r") as f:
                current_str = f.read()
        except FileNotFoundError:
            return False
        self.current = CurrentConversation.from_dict(json.loads(current_str))
        return True

    def save(self):
        assert self.current is not None
        current_str = json.dumps(asdict(self.current), ensure_ascii=False, indent=2)
        with open(os.path.join(self.__path, "current.json"), "w") as f:
            f.write(current_str)
