import threading

from memory import EnginePointer, Message
from session.session.internal import SessionInternal


def main_loop(self: SessionInternal):
    # 根据 storage 判断初始命令
    self.worker.start()
    if not self.storage.load():
        self.create()  # 没有当前储存的会话，直接创建
    elif self.storage.current.pointer.status == EnginePointer.FULLED:
        self.summarize()
    elif self.storage.current.pointer.status == EnginePointer.SUMMARIZED:
        self.merge()
    elif self.storage.current.pointer.status == EnginePointer.MERGED:
        self.replace()
    elif self.storage.current.pointer.status == EnginePointer.UNINITIALIZED:
        if len(self.storage.current.memo) == 0:
            self.send()
        else:
            self.inherit()
    else:
        if len(self.storage.current.messages) != 0:
            if self.storage.current.messages[-1].sender == Message.USER:
                self.send()

    cmd_map = {
        SessionInternal.SEND: self.on_send,
        SessionInternal.CREATE: self.on_send,
        SessionInternal.SUMMARIZE: self.on_summarize,
        SessionInternal.MERGE: self.on_merge,
        SessionInternal.INHERIT: self.on_inherit,
    }
    while True:  # 开始主循环
        with self.worker_lock:
            if self.command == SessionInternal.NONE:
                self.logger.info("waiting for command ...")
            while self.command == SessionInternal.NONE:  # 等待新命令
                self.worker_cond.wait()
            command = self.command
            self.logger.info("get command %s", SessionInternal.CMD_STR[command])
            self.command = SessionInternal.NONE
        fn = cmd_map.get(command)
        assert fn is not None
        self.worker.join()  # 确保工作线程完全结束
        self.worker = threading.Thread(target=fn)
        self.worker.start()  # 启动新线程执行命令
