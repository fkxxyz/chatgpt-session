import time

import error
from engine.openai_chat import OpenAIChatCompletion
from engine.rev_chatgpt_web import RevChatGPTWeb
from memory import EnginePointer
from session.session.internal import SessionInternal


def force_compress(self):
    self.logger.info("put command COMPRESS (force)")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert len(self.storage.current.pointer.memo) == 0  # 确保没有备忘录

        self.storage.current.pointer.status = EnginePointer.FULLED

        self.command = SessionInternal.SUMMARIZE
        self.status = SessionInternal.INITIALIZING
        self.worker_cond.notify_all()


def summarize(self):
    self.logger.info("put command SUMMARIZE")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert self.storage.current.pointer.status == EnginePointer.FULLED  # 确保满了
        assert len(self.storage.current.pointer.summary) == 0  # 确保没有总结

        self.command = SessionInternal.SUMMARIZE
        self.status = SessionInternal.INITIALIZING
        self.worker_cond.notify_all()


def merge(self: SessionInternal):
    self.logger.info("put command MERGE")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert self.storage.current.pointer.status == EnginePointer.SUMMARIZED  # 确保已总结
        assert len(self.storage.current.pointer.summary) != 0  # 确保有总结

        self.command = SessionInternal.MERGE
        self.status = SessionInternal.INITIALIZING
        self.worker_cond.notify_all()


def on_summarize(self: SessionInternal):
    self.logger.info("on_summarize() enter")
    with self.worker_lock:
        while not self.readable():
            self.worker_cond.wait()
        self.reading_num += 1

    while True:
        # 先评估在哪个引擎哪个帐号处理信息
        engine, account = self.scheduler.evaluate(self.storage.current.pointer)

        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.engine = engine
            self.storage.current.pointer.account = account
            self.storage.current.pointer.prompt = self.texts[self.type].summary()
            self.storage.save()

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
        pass
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
        reply = new_message.msg

    # 得到备忘录，确保备忘录格式正确
    memo = "```\n" + reply.strip("`\n") + "\n```"

    if len(self.storage.current.memo) == 0:
        # 将备忘录记录
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.memo = memo
            self.storage.current.pointer.status = EnginePointer.MERGED
            self.storage.save()

        # 清理会话
        self.scheduler.clean(self.storage.current.pointer)

        # 备忘录记录完了，进入继承状态
        with self.worker_lock:
            self.reading_num -= 1
        self.replace()
        self.logger.info("on_summarize() leave")
        return

    # 将备忘录记录
    with self.worker_lock:
        while self.writing or self.reading_num > 1:
            self.worker_cond.wait()
        self.storage.current.pointer.summary = memo
        self.storage.current.pointer.status = EnginePointer.SUMMARIZED
        self.storage.save()

    # 备忘录记录完了，进入合并状态
    with self.worker_lock:
        self.reading_num -= 1
        self.command = SessionInternal.MERGE
        self.status = SessionInternal.INITIALIZING
        self.worker_cond.notify_all()
    self.logger.info("on_summarize() leave")


def on_merge(self: SessionInternal):
    self.logger.info("on_merge() enter")
    with self.worker_lock:
        while not self.readable():
            self.worker_cond.wait()
        self.reading_num += 1

    while True:
        # 先评估在哪个引擎哪个帐号处理信息
        engine, account = self.scheduler.evaluate(self.storage.current.pointer)

        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.engine = engine
            self.storage.current.pointer.account = account
            self.storage.current.pointer.prompt = \
                self.texts[self.type].merge(
                    self.params,
                    self.storage.current.memo,
                    self.storage.current.pointer.summary,
                )
            self.storage.save()

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
        pass
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
        reply = new_message.msg

    # 得到备忘录，确保备忘录格式正确
    memo = "```\n" + reply.strip("`\n") + "\n```"

    # 将备忘录记录
    with self.worker_lock:
        while self.writing or self.reading_num > 1:
            self.worker_cond.wait()
        self.storage.current.pointer.memo = memo
        self.storage.current.pointer.status = EnginePointer.MERGED
        self.storage.save()

    # 清理会话
    self.scheduler.clean(self.storage.current.pointer)

    # 备忘录记录完了，进入继承状态
    with self.worker_lock:
        self.reading_num -= 1
    self.replace()
    self.logger.info("on_merge() leave")
