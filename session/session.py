import copy
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import List

import error
from memory import Message, CurrentConversation
from schedule import Scheduler
from session.storage import SessionStorage
from session.text import SessionText
from tokenizer import token_len


@dataclass
class SessionMessageResponse:
    msg: str
    end: bool


class Session:
    # 命令
    __NONE = 0
    __CREATE = 1
    __SEND = 2
    __COMPRESS = 3
    __INHERIT = 4
    __STOP = 5
    __EXIT = 6
    __CMD_STR = {
        __NONE: "NONE",
        __CREATE: "CREATE",
        __SEND: "SEND",
        __COMPRESS: "COMPRESS",
        __INHERIT: "INHERIT",
        __STOP: "STOP",
        __EXIT: "EXIT",
    }

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

        self.__logger = logging.getLogger(self.id)
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
            self.__create()  # 没有当前储存的会话，直接创建
        elif self.__storage.current.pointer.fulled:
            if len(self.__storage.current.pointer.memo) == 0:
                self.__compress()
            else:
                self.__replace()
        elif self.__storage.current.pointer.uninitialized:
            self.__inherit()
        elif len(self.__storage.current.messages) == 0 or self.__storage.current.messages[-1].sender == Message.USER:
            self.send()  # 消息为空或者最后一条消息是用户消息，需要AI回复

        cmd_map = {
            Session.__SEND: self.__on_send,
            Session.__CREATE: self.__on_send,
            Session.__COMPRESS: self.__on_compress,
            Session.__INHERIT: self.__on_inherit,
        }
        while True:  # 开始主循环
            with self.__worker_lock:
                if self.__command == Session.__NONE:
                    self.__logger.info("waiting for command ...")
                while self.__command == Session.__NONE:  # 等待新命令
                    self.__worker_cond.wait()
                command = self.__command
                self.__logger.info("get command %s", Session.__CMD_STR[command])
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

    def status(self) -> int:
        with self.__worker_lock:
            return self.__status

    def __create(self):
        self.__logger.info("put command CREATE")
        with self.__worker_lock:
            while self.__status != Session.__IDLE:  # 确保空闲状态
                self.__worker_cond.wait()
            while not self.__writeable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert self.__storage.current is None  # 确保没有被初始化

            # 生成引导语
            guide = self.__texts[self.type].create(self.params)

            # 创建出数据
            self.__storage.current = CurrentConversation.create(guide)
            self.__storage.current.pointer.pointer["title"] = self.id
            self.__storage.save()  # 保存到磁盘

            self.__command = Session.__CREATE
            self.__status = Session.__INITIALIZING
            self.__worker_cond.notify_all()

    def __replace(self):
        self.__logger.info("put command REPLACE")
        with self.__worker_lock:
            while not self.__writeable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert self.__storage.current is not None  # 确保有数据
            assert len(self.__storage.current.pointer.memo) != 0  # 确保有备忘录

            # 生引导语
            memo = self.__storage.current.pointer.memo
            recent_history, messages = Session.__recent_history(self.__storage.current)
            guide = self.__texts[self.type].inherit(self.params, memo, recent_history)

            # 处理旧的 messages 备注
            for message in messages:
                message.remark["inherit"] = True

            # 创建出数据
            current = CurrentConversation.create(guide, memo, recent_history)
            current.messages = messages
            current.pointer.pointer["title"] = self.id
            self.__storage.replace(current)  # 保存到磁盘

            self.__command = Session.__INHERIT
            self.__status = Session.__INITIALIZING
            self.__worker_cond.notify_all()

    def __inherit(self):
        self.__logger.info("put command INHERIT")
        with self.__worker_lock:
            while self.__status != Session.__IDLE:  # 确保空闲状态
                self.__worker_cond.wait()
            while not self.__readable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert self.__storage.current is not None  # 确保有数据
            assert self.__storage.current.pointer.uninitialized  # 确保需要继承

            self.__command = Session.__INHERIT
            self.__status = Session.__INITIALIZING
            self.__worker_cond.notify_all()

    def __compress(self):
        self.__logger.info("put command COMPRESS")
        with self.__worker_lock:
            while self.__status != Session.__IDLE:  # 确保空闲状态
                self.__worker_cond.wait()
            while not self.__writeable():
                self.__worker_cond.wait()

            assert self.__command == Session.__NONE  # 确保命令为空
            assert self.__storage.current is not None  # 确保有数据
            assert self.__storage.current.pointer.fulled  # 确保满了
            assert len(self.__storage.current.pointer.memo) == 0  # 确保没有备忘录

            self.__command = Session.__COMPRESS
            self.__status = Session.__INITIALIZING
            self.__worker_cond.notify_all()

    def send(self):
        self.__logger.info("put command SEND")
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
            elif messages[-1].sender == Message.AI:
                return SessionMessageResponse(messages[-1].content, True)
            else:
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
            self.__storage.current.append_message(Message(Message.USER, msg, token_len(msg), {}))  # 将要发送的消息追加到最后
            self.__storage.save()  # 保存到磁盘

            self.__command = Session.__SEND
            self.__status = Session.__GENERATING
            self.__worker_cond.notify_all()

    def __on_send(self):
        self.__logger.info("__on_send() enter")

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
        try:
            mid = self.__scheduler.send(self.__storage.current)
        except (error.Unauthorized, error.ServerIsBusy) as e:
            pass

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
            self.__storage.current.append_message(Message(Message.AI, new_message.msg, token_len(new_message.msg), {
                "mid": new_message.mid,
            }))
            self.__storage.current.pointer.pointer["id"] = new_message.id
            self.__storage.current.pointer.pointer["mid"] = new_message.mid
            if self.__storage.current.tokens >= 2048:
                self.__storage.current.pointer.fulled = True
            self.__storage.save()

        # token 数量达到一定程度时需要压缩
        if self.__storage.current.pointer.fulled:
            # 准备生成备忘录，进入备忘录记录状态
            with self.__worker_lock:
                self.__reading_num -= 1
                self.__command = Session.__COMPRESS
                self.__status = Session.__INITIALIZING
                self.__worker_cond.notify_all()
            return

        # 生成完了，进入空闲状态
        with self.__worker_lock:
            self.__reading_num -= 1
            self.__status = Session.__IDLE
            self.__worker_cond.notify_all()
        self.__logger.info("__on_send() leave")

    def __on_compress(self):
        self.__logger.info("__on_compress() enter")
        # 先评估在哪个引擎哪个帐号处理信息
        with self.__worker_lock:
            while not self.__readable():
                self.__worker_cond.wait()
            self.__reading_num += 1
        engine, account = self.__scheduler.evaluate(self.__storage.current.pointer)

        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.pointer.engine = engine
            self.__storage.current.pointer.account = account
            self.__storage.current.pointer.pointer["compress"] = \
                self.__texts[self.type].compress(self.params, self.__storage.current.memo)
            self.__storage.save()

        # 发送信息，得到新信息的 mid
        mid = self.__scheduler.send(self.__storage.current)

        # 记录得到新消息的 mid
        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.pointer.pointer["memo_mid"] = mid
            self.__storage.save()

        # 循环等到 ChatGPT 回复完成
        while True:
            new_message = self.__scheduler.get(self.__storage.current.pointer)
            if new_message.end:
                break
            time.sleep(0.1)

        # 将备忘录记录
        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.pointer.memo = new_message.msg
            self.__storage.save()

        # 备忘录记录完了，进入继承状态
        with self.__worker_lock:
            self.__reading_num -= 1
        self.__replace()
        self.__logger.info("__on_compress() leave")

    def __on_inherit(self):
        self.__logger.info("__on_inherit() enter")
        with self.__worker_lock:
            while not self.__writeable():
                self.__worker_cond.wait()
            self.__reading_num += 1

        # 先评估在哪个引擎哪个帐号处理信息
        engine, account = self.__scheduler.evaluate(self.__storage.current.pointer)

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
            self.__storage.current.pointer.pointer["inherited_mid"] = mid
            self.__storage.save()

        # 循环等到 ChatGPT 回复完成
        while True:
            new_message = self.__scheduler.get(self.__storage.current.pointer)
            if new_message.end:
                break
            time.sleep(0.1)
        new_tokens = token_len(new_message.msg)

        # 完成了继承，记录帐号以及 id 和 mid
        with self.__worker_lock:
            while self.__writing or self.__reading_num > 1:
                self.__worker_cond.wait()
            self.__storage.current.pointer.engine = engine
            self.__storage.current.pointer.account = account
            self.__storage.current.pointer.pointer["id"] = new_message.id
            self.__storage.current.pointer.pointer["mid"] = new_message.mid
            self.__storage.current.pointer.uninitialized = False
            self.__storage.current.tokens += new_tokens + 1
            self.__storage.save()

        # 新创建的会话一定不能超过
        assert self.__storage.current.tokens < 3072

        # 生成完了，进入空闲状态
        with self.__worker_lock:
            self.__reading_num -= 1
            self.__status = Session.__IDLE
            self.__worker_cond.notify_all()
        self.__logger.info("__on_inherit() leave")

    @staticmethod
    def __recent_history(current: CurrentConversation) -> (str, List[Message]):
        if len(current.messages) <= 2:
            return Session.__messages_str(current.messages), current.messages[:]

        i = len(current.messages) - 3
        tokens = current.messages[i + 1].tokens + current.messages[i + 2].tokens + 2
        while i >= 0:
            tokens += current.messages[i].tokens
            if tokens > 1024:
                break
        return Session.__messages_str(current.messages, i + 1, len(current.messages)), current.messages[i + 1:]

    @staticmethod
    def __messages_str(messages: List[Message], start: int = 0, end: int = None) -> str:
        if end is None:
            end = len(messages)
        s = ""
        for i in range(start, end):
            if messages[i].sender == Message.AI:
                s += 'You: ' + messages[i].content + "\n"
            if messages[i].sender == Message.USER:
                s += 'Me: ' + messages[i].content + "\n"
        return s
