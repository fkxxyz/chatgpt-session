import copy
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import List

from memory import Message, CurrentConversation
from schedule import Scheduler
from session.storage import SessionStorage
from session.text import SessionText


@dataclass
class SessionMessageResponse:
    msg: str
    end: bool


class Session:
    # 命令
    __NONE = 0
    __CREATE = 1
    __SEND = 2
    __STOP = 3
    __EXIT = 4

    # 状态
    __IDLE = 0  # 空闲
    __GENERATING = 1  # 生成中（可停止）
    __INITIALIZING = 2  # 初始化中（不可停止）

    def __init__(self, d: str, texts: OrderedDict[str, SessionText], scheduler: Scheduler):
        with open(os.path.join(d, "index.json"), "r") as f:
            j = json.loads(f.read())
        self.id: str = j["id"]
        self.type: str = j["type"]
        self.params: dict = j["params"]

        self.__texts: OrderedDict[str, SessionText] = texts
        self.__scheduler: Scheduler = scheduler
        self.__storage: SessionStorage = SessionStorage(d, self.type, self.params)
        self.__main_loop: threading.Thread = threading.Thread(target=self.__main_loop)
        self.__worker: threading.Thread = threading.Thread()  # 执行命令用的线程

        self.__status: int = Session.__IDLE
        self.__command: int = Session.__NONE
        self.__reading_num = 0
        self.__writing = False
        self.__worker_lock: threading.Lock = threading.Lock()
        self.__worker_cond: threading.Condition = threading.Condition(self.__worker_lock)

        self.__main_loop.start()

    def __del__(self):
        pass

    def __main_loop(self):
        # 根据 storage 判断初始命令
        self.__worker.start()
        if not self.__storage.load():
            self.create()  # 没有当前储存的会话，直接创建
        elif len(self.__storage.current.messages) == 0 or self.__storage.current.messages[-1].sender == Message.USER:
            self.send()  # 消息为空或者最后一条消息是用户消息，需要AI回复

        cmd_map = {
            Session.__SEND: self.__on_send,
            Session.__CREATE: self.__on_send,
        }
        while True:  # 开始主循环
            with self.__worker_lock:
                while self.__command == Session.__NONE:  # 等待新命令
                    self.__worker_cond.wait()
                command = self.__command
                self.__command = Session.__NONE
            fn = cmd_map.get(command)
            assert fn is not None
            self.__worker.join()  # 确保工作线程完全结束
            self.__worker = threading.Thread(target=fn)
            self.__worker.start()  # 启动新线程执行命令

    def __readable(self) -> bool:
        return not self.__writing

    def __writeable(self) -> bool:
        return not self.__writing and self.__reading_num == 0

    def asdict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "params": self.params,
        }

    def create(self):
        with self.__worker_lock:
            while self.__status != Session.__IDLE:  # 确保空闲状态
                self.__worker_cond.wait()
            while not self.__writeable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert self.__storage.current is None  # 确保没有被初始化

            # 生引导语
            guide = self.__texts[self.type].guide(self.params)

            # 创建出数据
            self.__storage.current = CurrentConversation.create(guide)
            self.__storage.current.pointer.pointer["title"] = self.id
            self.__storage.save()  # 保存到磁盘

            self.__command = Session.__CREATE
            self.__status = Session.__INITIALIZING
            self.__worker_cond.notify_all()

    def send(self):
        with self.__worker_lock:
            while self.__status != Session.__IDLE:  # 确保空闲状态
                self.__worker_cond.wait()
            while not self.__readable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert len(self.__storage.current.messages) == 0 or \
                   self.__storage.current.messages[-1].sender == Message.USER  # 确保确实需要AI回复

            self.__command = Session.__SEND
            self.__status = Session.__GENERATING
            self.__worker_cond.notify_all()

    def get(self) -> SessionMessageResponse:
        with self.__worker_lock:
            while not self.__readable():
                self.__worker_cond.wait()
            pointer = copy.deepcopy(self.__storage.current.pointer)
            messages: List[Message] = []
            if len(self.__storage.current.messages) != 0:
                messages.append(copy.deepcopy(self.__storage.current.messages[-1]))

        new_mid = pointer.pointer.get("new_mid")
        if new_mid is None:
            if len(messages) == 0:
                return SessionMessageResponse("", True)
            assert messages[-1].sender == Message.USER
            return SessionMessageResponse("", False)
        mid = pointer.pointer.get("mid")
        if mid == new_mid:
            assert len(messages) != 0
            if messages[-1].sender == Message.AI:
                return SessionMessageResponse(messages[-1].content, True)
            else:
                return SessionMessageResponse("", False)
        new_message = self.__scheduler.get(pointer)
        return SessionMessageResponse(new_message.msg, new_message.end)

    def append_msg(self, msg: str):
        with self.__worker_lock:
            while self.__status != Session.__IDLE:  # 确保空闲状态
                self.__worker_cond.wait()
            while not self.__writeable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert self.__storage.current.messages[-1].sender == Message.AI  # 确保最后一条消息是AI的消息
            self.__storage.current.append_message(Message(Message.USER, msg))  # 将要发送的消息追加到最后
            self.__storage.save()  # 保存到磁盘

            self.__command = Session.__SEND
            self.__status = Session.__GENERATING
            self.__worker_cond.notify_all()

    def __on_send(self):
        # 先评估在哪个引擎哪个帐号处理信息
        with self.__worker_lock:
            while not self.__readable():
                self.__worker_cond.wait()
            self.__reading_num += 1
        engine, account = self.__scheduler.evaluate(self.__storage.current.pointer)

        # 考虑需要压缩的情况
        if len(self.__storage.current.pointer.engine) != 0 and self.__storage.current.pointer.account != 0 and \
                (engine != self.__storage.current.pointer.engine or account != self.__storage.current.pointer.account):
            # TODO 需要压缩
            pass

        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.pointer.engine = engine
            self.__storage.current.pointer.account = account

        # 发送信息，得到新信息的 mid
        mid = self.__scheduler.send(self.__storage.current)

        # 记录得到新消息的 mid
        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.pointer.pointer["new_mid"] = mid
            self.__storage.save()

        # 循环等到 ChatGPT 回复完成
        while True:
            new_message = self.__scheduler.get(self.__storage.current.pointer)
            if new_message.end:
                break
            time.sleep(0.1)

        # 将 ChatGPT 回复的消息加入到记录中
        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.append_message(Message(Message.AI, new_message.msg))
            self.__storage.current.pointer.pointer["id"] = new_message.id
            self.__storage.current.pointer.pointer["mid"] = new_message.mid
            self.__storage.save()

        # 生成完了，进入空闲状态
        with self.__worker_lock:
            self.__reading_num -= 1
            self.__status = Session.__IDLE
            self.__worker_cond.notify_all()
