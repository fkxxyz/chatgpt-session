import time

import error
from engine.openai_chat import OpenAIChatCompletion
from engine.rev_chatgpt_web import RevChatGPTWeb
from memory import EnginePointer
from session.session.initialize import prune_memo
from session.session.internal import SessionInternal
from tokenizer import token_len


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


def clean(self: SessionInternal):
    self.logger.info("put command CLEAN")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE:  # 确保空闲状态
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert len(self.storage.current.pointer.memo) != 0  # 确保有备忘录

        self.command = SessionInternal.CLEAN
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
            self.storage.current.pointer.prompt = self.texts[self.type].summary(self.params)
            self.storage.save()

        # 发送信息，得到新信息的 mid
        try:
            reply = self.scheduler.send(self.storage.current)
            break
        except (error.Unauthorized, error.ServerIsBusy) as err:
            self.logger.error("on_summarize() send error: %s", err)
            self.storage.current.pointer.engine = ""
            self.storage.current.pointer.account = ""

            # 帐号问题导致消息记录需要丢弃
            with self.worker_lock:
                self.status = SessionInternal.INITIALIZING
                self.reading_num -= 1
            self.break_()
            self.logger.info("on_summarize() leave")
            return

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

        # 备忘录记录完了，进入清理状态
        with self.worker_lock:
            self.reading_num -= 1
            self.command = SessionInternal.CLEAN
            self.status = SessionInternal.INITIALIZING
            self.worker_cond.notify_all()
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

        while self.writing or self.reading_num > 1:
            self.worker_cond.wait()
        self.storage.current.pointer.prompt = \
            self.texts[self.type].merge(
                self.params,
                self.storage.current.memo,
                self.storage.current.pointer.summary,
            )
        self.storage.save()

    # 用一次性发送接口合并出备忘录
    try:
        reply = self.scheduler.send_away(self.storage.current.pointer.prompt, self.level)
    except error.TooLarge:
        self.logger.error("on_merge() send too large. prune summary ...")
        summary = prune_memo(self.storage.current.pointer.summary)
        memo = self.storage.current.memo
        if token_len(summary + self.storage.current.memo) > 1152:
            memo = prune_memo(self.storage.current.memo)
        with self.worker_lock:
            while self.writing or self.reading_num > 1:
                self.worker_cond.wait()
            self.storage.current.pointer.summary = summary
            self.storage.current.memo = memo
            self.storage.save()
            self.reading_num -= 1
            self.command = SessionInternal.MERGE
            self.status = SessionInternal.INITIALIZING
            self.worker_cond.notify_all()
        self.logger.info("on_merge() leave")
        return

    # 得到备忘录，确保备忘录格式正确
    memo = "```\n" + reply.strip("`\n") + "\n```"

    # 将备忘录记录
    with self.worker_lock:
        while self.writing or self.reading_num > 1:
            self.worker_cond.wait()
        self.storage.current.pointer.memo = memo
        self.storage.current.pointer.status = EnginePointer.MERGED
        self.storage.save()

    # 备忘录记录完了，进入清理状态
    with self.worker_lock:
        self.reading_num -= 1
        self.command = SessionInternal.CLEAN
        self.status = SessionInternal.INITIALIZING
        self.worker_cond.notify_all()
    self.logger.info("on_merge() leave")


def on_clean(self: SessionInternal):
    self.logger.info("on_clean() enter")
    with self.worker_lock:
        while not self.readable():
            self.worker_cond.wait()
        self.reading_num += 1

    # 清理会话
    try:
        self.scheduler.clean(self.storage.current.pointer)
    except error.NotFoundError:
        pass

    # 清理完了，进入继承状态
    with self.worker_lock:
        self.storage.current.pointer.status = EnginePointer.CLEANED
        self.storage.save()
        self.reading_num -= 1
    self.replace()
    self.logger.info("on_clean() leave")
