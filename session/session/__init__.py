from collections import OrderedDict
from dataclasses import dataclass
from typing import List

from memory import Message
from schedule import Scheduler
from session.session.internal import SessionInternal
from text import SessionText


@dataclass
class SessionMessageResponse:
    mid: str
    msg: str
    end: bool


class Session:
    def __init__(self, d: str, texts: OrderedDict[str, SessionText], scheduler: Scheduler):
        self.__internal = SessionInternal(d, texts, scheduler)

    def asdict(self) -> dict:
        return {
            "id": self.__internal.id,
            "type": self.__internal.type,
            "params": self.__internal.params,
        }

    def exit(self):
        return self.__internal.exit()

    def reload(self):
        return self.__internal.reload()

    def set_params(self, params: dict):
        return self.__internal.set_params(params)

    def status(self) -> (int, int):
        return self.__internal.get_status()

    def force_compress(self):
        return self.__internal.force_compress()

    def send(self):
        return self.__internal.send()

    def get(self, stop=False) -> SessionMessageResponse:
        return self.__internal.get(stop)

    def append_msg(self, msg: str, remark: dict):
        return self.__internal.append_msg(msg, remark)

    def memo(self) -> str:
        return self.__internal.memo()

    def history(self) -> List[Message]:
        return self.__internal.history()

    def get_remark(self) -> dict:
        return self.__internal.get_remark()

    def set_remark(self, remark: dict):
        return self.__internal.set_remark(remark)
