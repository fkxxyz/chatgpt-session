import importlib
import json
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import List

from memory import Message
from schedule import Scheduler
from session.storage import SessionStorage
from session.text import SessionText


@dataclass
class SessionMessageResponse:
    mid: str
    msg: str
    end: bool


@dataclass
class SessionInternalModules:
    main_loop: any
    initialize: any
    send: any
    compress: any


class SessionInternal:
    # 命令
    NONE = 0
    CREATE = 1
    SEND = 2
    SUMMARIZE = 3
    MERGE = 4
    INHERIT = 5
    CMD_STR = {
        NONE: "NONE",
        CREATE: "CREATE",
        SEND: "SEND",
        SUMMARIZE: "SUMMARIZE",
        MERGE: "MERGE",
        INHERIT: "INHERIT",
    }

    # 状态
    IDLE = 0  # 空闲
    GENERATING = 1  # 生成中（可停止）
    INITIALIZING = 2  # 初始化中（不可停止）
    STOPPING = 3  # 停止中

    def __init__(self, d: str, texts: OrderedDict[str, SessionText], scheduler: Scheduler):
        self.modules: SessionInternalModules = SessionInternalModules(
            importlib.import_module("session.session.main_loop"),
            importlib.import_module("session.session.initialize"),
            importlib.import_module("session.session.send"),
            importlib.import_module("session.session.compress"),
        )

        with open(os.path.join(d, "index.json"), "r") as f:
            j = json.loads(f.read())
        self.id: str = j["id"]
        self.type: str = j["type"]
        self.params: dict = j["params"]
        self.level: int = int(self.params["level"])

        self.logger = logging.getLogger(self.id)
        self.texts: OrderedDict[str, SessionText] = texts
        self.scheduler: Scheduler = scheduler
        self.storage: SessionStorage = SessionStorage(d, self.type, self.params)
        self.main_loop: threading.Thread = threading.Thread(target=self.main_loop)
        self.worker: threading.Thread = threading.Thread()  # 执行命令用的线程

        self.status: int = SessionInternal.IDLE
        self.command: int = SessionInternal.NONE
        self.reading_num = 0
        self.writing = False
        self.worker_lock: threading.Lock = threading.Lock()
        self.worker_cond: threading.Condition = threading.Condition(self.worker_lock)

        self.main_loop.start()

    def __del__(self):
        # TODO 终止所有线程
        pass

    def readable(self) -> bool:
        return not self.writing

    def writeable(self) -> bool:
        return not self.writing and self.reading_num == 0

    def get_status(self) -> (int, int):
        with self.worker_lock:
            if self.storage.current is None:
                return self.status, 0
            else:
                return self.status, self.storage.current.tokens

    def main_loop(self):
        return self.modules.main_loop.main_loop(self)

    def create(self):
        return self.modules.initialize.create(self)

    def replace(self):
        return self.modules.initialize.replace(self)

    def inherit(self):
        return self.modules.initialize.inherit(self)

    def force_compress(self):
        return self.modules.compress.force_compress(self)

    def summarize(self):
        return self.modules.compress.summarize(self)

    def merge(self):
        return self.modules.compress.merge(self)

    def send(self):
        return self.modules.send.send(self)

    def get(self, stop=False) -> SessionMessageResponse:
        return self.modules.send.get(self, stop)

    def append_msg(self, msg: str, remark: dict):
        return self.modules.send.append_msg(self, msg, remark)

    def memo(self) -> str:
        with self.worker_lock:
            if self.storage.current is None:
                return ""
            else:
                return self.storage.current.memo

    def history(self) -> List[Message]:
        with self.worker_lock:
            if self.storage.current is None:
                return []
            else:
                return self.storage.current.messages

    def get_remark(self) -> dict:
        return self.storage.load_remark()

    def set_remark(self, remark: dict):
        self.storage.save_remark(remark)

    def on_send(self):
        return self.modules.send.on_send(self)

    def on_summarize(self):
        return self.modules.compress.on_summarize(self)

    def on_merge(self):
        return self.modules.compress.on_merge(self)

    def on_inherit(self):
        return self.modules.initialize.on_inherit(self)
