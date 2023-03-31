import copy
import time
from typing import List

import error
from engine.openai_chat import OpenAIChatCompletion
from engine.rev_chatgpt_web import RevChatGPTWeb
from memory import Message, EnginePointer
from session.session.internal import SessionInternal, SessionMessageResponse
from tokenizer import token_len


def get(self: SessionInternal, stop=False) -> SessionMessageResponse:
    with self.worker_lock:
        if stop and self.status == SessionInternal.GENERATING:
            self.status = SessionInternal.STOPPING
            while self.status == SessionInternal.STOPPING:
                self.worker_cond.wait()

        while not self.readable():
            self.worker_cond.wait()
        pointer = copy.deepcopy(self.storage.current.pointer)
        messages: List[Message] = []
        if len(self.storage.current.messages) != 0:
            messages.append(copy.deepcopy(self.storage.current.messages[-1]))

    if self.status == SessionInternal.INITIALIZING:
        return SessionMessageResponse("", "", False)

    if pointer.engine == RevChatGPTWeb.__name__:
        if len(pointer.new_mid) == 0:
            if pointer.status == EnginePointer.UNINITIALIZED:
                return SessionMessageResponse("", "", False)
            if len(messages) == 0:
                return SessionMessageResponse("", "", True)
            elif messages[-1].sender == Message.AI:
                return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
            else:
                return SessionMessageResponse("", "", False)
        if pointer.mid == pointer.new_mid:
            if pointer.status == EnginePointer.UNINITIALIZED:
                return SessionMessageResponse("", "", False)
            if len(messages) == 0:
                return SessionMessageResponse("", "", True)
            if messages[-1].sender == Message.AI:
                return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
            else:
                return SessionMessageResponse("", "", False)
        new_message = self.scheduler.get(pointer)
        return SessionMessageResponse(new_message.mid, new_message.msg, new_message.end)
    elif pointer.engine == OpenAIChatCompletion.__name__:
        if pointer.status == EnginePointer.UNINITIALIZED:
            return SessionMessageResponse("", "", False)
        if len(messages) == 0:
            return SessionMessageResponse("", "", True)
        if messages[-1].sender == Message.AI:
            return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
        return SessionMessageResponse("", "", False)
    else:
        if pointer.status == EnginePointer.UNINITIALIZED:
            return SessionMessageResponse("", "", False)
        if len(messages) == 0:
            return SessionMessageResponse("", "", True)
        if messages[-1].sender == Message.AI:
            return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
        return SessionMessageResponse("", "", False)


def append_msg(self: SessionInternal, msg: str, remark: dict):
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None
        assert self.storage.current.pointer.status == EnginePointer.IDLE
        assert len(self.storage.current.messages) == 0 or \
               self.storage.current.messages[-1].sender == Message.AI  # 确保最后一条消息是AI的消息

        message = Message("", Message.USER, msg, token_len(msg), remark)
        message.content = self.texts[self.type].rule.compile_message(message)
        self.storage.current.append_message(message)  # 将要发送的消息追加到最后
        self.storage.save()  # 保存到磁盘

        self.command = SessionInternal.SEND
        self.status = SessionInternal.GENERATING
        self.worker_cond.notify_all()


def send(self: SessionInternal):
    self.logger.info("put command SEND")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.readable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None
        assert self.storage.current.pointer.status <= EnginePointer.IDLE
        assert len(self.storage.current.messages) == 0 or \
               self.storage.current.messages[-1].sender == Message.USER  # 确保确实需要AI回复

        self.command = SessionInternal.SEND
        self.status = SessionInternal.GENERATING
        self.worker_cond.notify_all()


def on_send(self: SessionInternal):
    self.logger.info("on_send() enter")

    # 先评估在哪个引擎哪个帐号处理信息
    with self.worker_lock:
        while not self.readable():
            self.worker_cond.wait()
        self.reading_num += 1

    while True:
        engine, account = self.scheduler.evaluate(self.storage.current.pointer)

        self.logger.info("on_send() select engine %s", engine)
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.engine = engine
            self.storage.current.pointer.account = account

        # 发送信息，得到新信息的 mid
        try:
            reply = self.scheduler.send(self.storage.current)
            break
        except (error.Unauthorized, error.ServerIsBusy) as err:
            self.logger.error("on_send() send error: %s", err)
            self.storage.current.pointer.engine = ""
            self.storage.current.pointer.account = ""

            # 帐号问题导致消息记录需要丢弃
            with self.worker_lock:
                self.status = SessionInternal.INITIALIZING
                self.reading_num -= 1
            self.break_()
            self.logger.info("on_send() leave")
            return

    if self.storage.current.pointer.engine == OpenAIChatCompletion.__name__:
        # 将回复的消息加入到记录中
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.ai_index = len(self.storage.current.messages)
            self.storage.current.append_message(Message("", Message.AI, reply, token_len(reply), {}))
            if self.storage.current.tokens >= 2048:
                self.storage.current.pointer.status = EnginePointer.FULLED
            self.storage.save()
    if self.storage.current.pointer.engine == RevChatGPTWeb.__name__:
        mid = reply

        # 记录得到新消息的 mid
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.ai_index = len(self.storage.current.messages)
            self.storage.current.pointer.new_mid = mid
            self.storage.save()

        # 循环等到 ChatGPT 回复完成
        stop_flag = False
        while True:
            new_message = self.scheduler.get(self.storage.current.pointer, stop_flag)
            if new_message.end:
                break
            with self.worker_lock:
                if self.status == SessionInternal.STOPPING:
                    stop_flag = True
            time.sleep(0.1)

        # 将 ChatGPT 回复的消息加入到记录中
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.append_message(
                Message(new_message.mid, Message.AI, new_message.msg, token_len(new_message.msg), {}))
            self.storage.current.pointer.id = new_message.id
            self.storage.current.pointer.mid = new_message.mid
            self.storage.current.pointer.status = EnginePointer.IDLE
            if self.storage.current.tokens >= 2560:
                self.storage.current.pointer.status = EnginePointer.FULLED
            self.storage.save()

    # token 数量达到一定程度时需要压缩
    if self.storage.current.pointer.status == EnginePointer.FULLED:
        # 准备生成备忘录，进入备忘录记录状态
        with self.worker_lock:
            self.reading_num -= 1
            self.command = SessionInternal.SUMMARIZE
            self.status = SessionInternal.INITIALIZING
            self.worker_cond.notify_all()
        self.logger.info("on_send() leave")
        return

    # 生成完了，进入空闲状态
    with self.worker_lock:
        self.reading_num -= 1
        self.status = SessionInternal.IDLE
        self.worker_cond.notify_all()
    self.logger.info("on_send() leave")
