import json
import os.path
from dataclasses import asdict
from datetime import datetime

from memory import CurrentConversation


class SessionStorage:
    def __init__(self, d: str, type_: str, params: dict):
        self.__path: str = d
        self.__session_type: str = type_
        self.__params: dict = params
        self.current: CurrentConversation | None = None

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
        os.sync()

    def replace(self, current: CurrentConversation):
        os.makedirs(os.path.join(self.__path, "archive"), exist_ok=True)
        assert self.current is not None
        current_str = json.dumps(asdict(self.current), ensure_ascii=False, indent=2)
        archive_name = datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".json"
        with open(os.path.join(self.__path, "archive", archive_name), "w") as f:
            f.write(current_str)

        self.current = current
        self.save()

    def load_remark(self) -> dict:
        try:
            with open(os.path.join(self.__path, "remark.json"), "r") as f:
                current_str = f.read()
        except FileNotFoundError:
            return {}
        return json.loads(current_str)

    def save_remark(self, remark: dict):
        remark_str = json.dumps(remark, ensure_ascii=False, indent=2)
        with open(os.path.join(self.__path, "remark.json"), "w") as f:
            f.write(remark_str)
