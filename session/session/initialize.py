import time

import error
from engine.openai_chat import OpenAIChatCompletion
from engine.rev_chatgpt_web import RevChatGPTWeb
from memory import CurrentConversation, EnginePointer, Message
from session.session.internal import SessionInternal
from tokenizer import token_len


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
        self.storage.current.pointer.level = self.level
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
        history, messages = self.texts[self.type].compile_history(self.storage.current.messages, self.params)
        guide = self.texts[self.type].inherit(self.params, memo, history)

        # 处理旧的 messages 备注
        for message in messages:
            message.remark["inherit"] = True

        # 创建出数据
        current = CurrentConversation.create(guide, memo, history)
        current.messages = messages
        current.pointer.level = self.level
        current.pointer.title = self.id
        current.pointer.status = EnginePointer.UNINITIALIZED
        self.storage.replace(current)  # 保存到磁盘

        self.command = SessionInternal.INHERIT
        self.status = SessionInternal.INITIALIZING
        self.reading_num += 1
        self.worker_cond.notify_all()


def break_(self: SessionInternal):
    self.logger.info("put command BREAK")
    with self.worker_lock:
        while not self.writeable():
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert len(self.storage.current.messages) != 0  # 确保有消息

        # 生引导语
        memo = self.storage.current.memo
        if len(self.storage.current.memo) == 0:
            memo = '```\n<empty>\n```'
        history, messages = self.texts[self.type].compile_history(self.storage.current.messages, self.params)
        guide = self.texts[self.type].inherit(self.params, memo, history)

        # 处理旧的 messages 备注
        for message in messages:
            message.remark["inherit"] = True

        # 创建出数据
        current = CurrentConversation.create(guide, memo, history)
        current.messages = messages
        if self.storage.current.messages[-1].sender == Message.USER:
            current.break_message = self.storage.current.messages.pop()
        else:
            current.break_message = None
        current.pointer.level = self.level
        current.pointer.title = self.id
        current.pointer.status = EnginePointer.BREAK
        self.storage.replace(current)  # 保存到磁盘

        self.command = SessionInternal.BREAK
        self.status = SessionInternal.INITIALIZING
        self.reading_num += 1
        self.worker_cond.notify_all()


def inherit(self: SessionInternal):
    self.logger.info("put command INHERIT")
    with self.worker_lock:
        while self.status != SessionInternal.IDLE or not self.readable():  # 确保空闲状态
            self.worker_cond.wait()

        assert self.command == SessionInternal.NONE  # 确保命令为空
        assert self.storage.current is not None  # 确保有数据
        assert self.storage.current.pointer.status == EnginePointer.UNINITIALIZED  # 确保需要继承
        assert len(self.storage.current.memo) != 0  # 确保需要继承

        self.command = SessionInternal.INHERIT
        self.status = SessionInternal.INITIALIZING
        self.reading_num += 1
        self.worker_cond.notify_all()


def prune_memo(memo: str) -> str:
    token_sum = token_len(memo)
    memo_lines = memo.splitlines()
    memo_line_flags = [[False, index, token_len(memo_lines[index]) if memo_lines[index].startswith("- ") else 0]
                       for index in range(len(memo_lines))]

    # 按 token 长度从大到小排序
    memo_line_flag_indexes = list(range(len(memo_line_flags)))
    memo_line_flag_indexes.sort(key=lambda index: memo_line_flags[index][2], reverse=True)

    # 逐步标记删除最长的行
    i = 0
    while token_sum > 576 and i < len(memo_line_flags):
        memo_line_flags[memo_line_flag_indexes[i]][0] = True
        token_sum -= memo_line_flags[memo_line_flag_indexes[i]][2]
        i += 1

    # 将未删除的行拼接起来
    new_memo = ""
    for flag in memo_line_flags:
        if not flag[0]:
            new_memo += memo_lines[flag[1]] + "\n"

    return new_memo.strip()


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
            self.logger.error("on_inherit() send error: %s", err)
            self.storage.current.pointer.engine = ""
            self.storage.current.pointer.account = ""
            time.sleep(1)
        except error.TooLarge:
            self.logger.error("on_inherit() send too large. prune memo ...")
            memo = prune_memo(self.storage.current.memo)
            with self.worker_lock:
                while self.writing or self.reading_num > 1:
                    self.worker_cond.wait()
                self.storage.current.pointer.memo = memo
                self.storage.save()
                self.reading_num -= 1
            self.replace()
            self.logger.info("on_inherit() leave")
            return

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
            self.storage.current.tokens += new_tokens + 1
            if self.storage.current.pointer.status == EnginePointer.BREAK and \
                    self.storage.current.break_message is not None:
                # 生成完了，恢复用户信息，恢复 send 流程
                self.reading_num -= 1
                self.storage.current.append_message(self.storage.current.break_message)  # 将要发送的消息追加到最后
                self.storage.current.pointer.status = EnginePointer.IDLE
                self.storage.save()  # 保存到磁盘

                self.command = SessionInternal.SEND
                self.status = SessionInternal.GENERATING
                self.worker_cond.notify_all()
                self.logger.info("on_inherit() leave")
                return
            self.storage.current.pointer.status = EnginePointer.IDLE
            self.storage.save()

    # 新创建的会话一定不能超过
    assert self.storage.current.tokens < 4096

    # 生成完了，进入空闲状态
    with self.worker_lock:
        self.reading_num -= 1
        self.status = SessionInternal.IDLE
        self.worker_cond.notify_all()
    self.logger.info("on_inherit() leave")
