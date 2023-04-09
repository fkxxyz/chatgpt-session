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
        while True:
            wait = False

            if stop and self.status == SessionInternal.GENERATING:
                self.status = SessionInternal.STOPPING
                if self.status == SessionInternal.STOPPING:
                    wait = True

            if not self.readable():
                wait = True

            if self.storage.current.break_message is not None:
                wait = True

            if not wait:
                break
            self.worker_cond.wait()
        status = self.status
        current = copy.deepcopy(self.storage.current)
        messages: List[Message] = []
        is_new_created = len(self.storage.current.memo) == 0
        if len(self.storage.current.messages) != 0:
            messages.append(copy.deepcopy(self.storage.current.messages[-1]))

    if current.queue_message or current.break_message:
        return SessionMessageResponse("", "", False)
    if current.pointer.status > EnginePointer.IDLE:
        # 压缩中，直接返回最后 AI 回复的消息
        assert len(messages) != 0
        if messages[-1].sender == Message.AI:
            return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
        else:
            return SessionMessageResponse("", "", False)

    if current.pointer.engine == RevChatGPTWeb.__name__:
        if status == SessionInternal.INITIALIZING:
            if is_new_created:
                if len(current.pointer.new_mid) == 0:
                    # 刚创建的会话
                    return SessionMessageResponse("", "", False)
                else:
                    # 刚创建的会话，且正在生成中
                    new_message = self.scheduler.get(current.pointer)
                    return SessionMessageResponse(new_message.mid, new_message.msg, new_message.end)
            else:
                # 继承中，直接返回最后 AI 回复的消息
                assert messages[-1].sender == Message.AI
                return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
        if status == SessionInternal.IDLE:
            # 空闲状态，直接返回最后 AI 回复的消息
            assert messages[-1].sender == Message.AI
            return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
        if status == SessionInternal.GENERATING:
            if len(current.pointer.new_mid) == 0:
                # 正在生成中，但是还没有生成出来
                return SessionMessageResponse("", "", False)
            else:
                try:
                    new_message = self.scheduler.get(current.pointer)
                except Exception as err:
                    print(err)
                    print(self.params)
                    print(current.pointer)
                    return SessionMessageResponse("", "", False)
                return SessionMessageResponse(new_message.mid, new_message.msg, new_message.end)
        assert False  # 未知状态

    if current.pointer.status != EnginePointer.IDLE:
        if len(messages) == 0:
            return SessionMessageResponse("", "", False)
        assert messages[-1].sender == Message.AI
        return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
    if status == SessionInternal.GENERATING:
        return SessionMessageResponse("", "", False)
    if len(messages) == 0:
        return SessionMessageResponse("", "", False)
    if messages[-1].sender == Message.AI:
        return SessionMessageResponse(messages[-1].mid, messages[-1].content, True)
    return SessionMessageResponse("", "", False)


def append_msg(self: SessionInternal, msg: str, remark: dict):
    t_len = token_len(msg)
    if t_len > 1536:
        raise error.TooLarge("message too long: " + str(t_len) + " > 1536")
    with self.worker_lock:
        while True:
            if self.storage.current.queue_message or self.storage.current.break_message:
                raise error.NotAcceptable('session is busy')
            if len(self.storage.current.messages) != 0 and \
                    self.storage.current.messages[-1].sender == Message.USER:
                raise error.NotAcceptable('session is busy')
            if self.status != SessionInternal.IDLE:
                self.storage.current.queue_message = Message("", Message.USER, msg, token_len(msg), remark)
                return
            if self.writeable():
                break
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None
        assert self.storage.current.pointer.status == EnginePointer.IDLE

        message = Message("", Message.USER, msg, token_len(msg), remark)
        message.content = self.texts[self.type].rule.compile_message(message)
        self.storage.current.append_message(message)  # 将要发送的消息追加到最后
        self.storage.current.pointer.new_mid = ""  # 清空新消息的ID
        self.storage.save()  # 保存到磁盘

        self.command = SessionInternal.SEND
        self.status = SessionInternal.GENERATING
        self.worker_cond.notify_all()


def send(self: SessionInternal):
    self.logger.info("put command SEND")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE or not self.readable():  # 确保空闲状态
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
        self.storage.current.queue_message = None
        self.storage.current.break_message = None

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

            if self.storage.current.pointer.status == EnginePointer.UNINITIALIZED:
                time.sleep(1)
                continue

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
