import time
from copy import deepcopy
from typing import List

import error
from engine.openai_chat import OpenAIChatCompletion
from engine.rev_chatgpt_web import RevChatGPTWeb
from memory import CurrentConversation, Message, EnginePointer
from session.session.internal import SessionInternal
from tokenizer import token_len


# 精简消息，如果消息的 token 大于 384，则把第100个字符到倒数100个字符之间的内容替换为省略号
def prune_message(message: Message) -> str:
    if token_len(message.content) <= 384:
        return message.content
    return message.content[:100] + '...' + message.content[-100:]


# 获取最近消息，每两条消息为一组，返回尽可能多的 token 不超过 1024 的最晚的精简过的消息
def recent_history(current: CurrentConversation) -> List[Message]:
    messages = deepcopy(current.messages)

    token = 0
    # 从最后一条消息开始，每两条消息为一组，精简消息，计算 token 数，如果 token 数超过 1024，则停止
    i = 0
    for i in range(len(messages) - 2, -1, -2):
        messages[i + 1].content = prune_message(messages[i + 1])
        messages[i + 1].tokens = token_len(messages[i + 1].content)
        messages[i].content = prune_message(messages[i])
        messages[i].tokens = token_len(messages[i].content)
        token += messages[i + 1].tokens + messages[i].tokens + 2
        if token > 1024:
            break
    i += 2
    assert i <= len(messages) - 2  # 确保至少有两条消息
    return messages[i:]


def create(self: SessionInternal):
    self.logger.info("put command CREATE")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is None  # 确保没有被初始化

        # 生成引导语
        guide = self.texts[self.type].create(self.params)

        # 创建出数据
        self.storage.current = CurrentConversation.create(guide)
        self.storage.current.pointer.title = self.id
        self.storage.current.pointer.status = EnginePointer.UNINITIALIZED
        self.storage.save()  # 保存到磁盘

        self.command = SessionInternal.CREATE
        self.status = SessionInternal.INITIALIZING
        self.worker_cond.notify_all()


def replace(self: SessionInternal):
    self.logger.info("put command REPLACE")
    with self.worker_lock:
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert len(self.storage.current.pointer.memo) != 0  # 确保有备忘录

        # 生引导语
        memo = self.storage.current.pointer.memo
        messages = recent_history(self.storage.current)
        history = ""
        for i in range(len(messages)):
            history += self.texts[self.type].message(messages[i], self.params)
        guide = self.texts[self.type].inherit(self.params, memo, history)

        # 处理旧的 messages 备注
        for message in messages:
            message.remark["inherit"] = True

        # 创建出数据
        current = CurrentConversation.create(guide, memo, history)
        current.messages = messages
        current.pointer.title = self.id
        current.pointer.status = EnginePointer.UNINITIALIZED
        self.storage.replace(current)  # 保存到磁盘

        self.command = SessionInternal.INHERIT
        self.status = SessionInternal.INITIALIZING
        self.reading_num += 1
        self.worker_cond.notify_all()


def inherit(self: SessionInternal):
    self.logger.info("put command INHERIT")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.readable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert self.storage.current.pointer.status == EnginePointer.UNINITIALIZED  # 确保需要继承
        assert len(self.storage.current.memo) != 0  # 确保需要继承

        self.command = SessionInternal.INHERIT
        self.status = SessionInternal.INITIALIZING
        self.reading_num += 1
        self.worker_cond.notify_all()


def on_inherit(self: SessionInternal):
    self.logger.info("on_inherit() enter")

    while True:
        # 先评估在哪个引擎哪个帐号处理信息
        engine, account = self.scheduler.evaluate(self.storage.current.pointer)

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
            time.sleep(1)

    if self.storage.current.pointer.engine == OpenAIChatCompletion.__name__:
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.engine = engine
            self.storage.current.pointer.account = account
            self.storage.save()
    if self.storage.current.pointer.engine == RevChatGPTWeb.__name__:
        mid = reply

        # 记录得到新消息的 mid
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.new_mid = mid
            self.storage.save()

        # 循环等到 ChatGPT 回复完成
        while True:
            new_message = self.scheduler.get(self.storage.current.pointer)
            if new_message.end:
                break
            time.sleep(0.1)
        new_tokens = token_len(new_message.msg)

        # 完成了继承，记录帐号以及 id 和 mid
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.engine = engine
            self.storage.current.pointer.account = account
            self.storage.current.pointer.id = new_message.id
            self.storage.current.pointer.mid = new_message.mid
            self.storage.current.pointer.status = EnginePointer.IDLE
            self.storage.current.tokens += new_tokens + 1
            self.storage.save()

    # 新创建的会话一定不能超过
    assert self.storage.current.tokens < 4096

    # 生成完了，进入空闲状态
    with self.worker_lock:
        self.reading_num -= 1
        self.status = SessionInternal.IDLE
        self.worker_cond.notify_all()
    self.logger.info("on_inherit() leave")
