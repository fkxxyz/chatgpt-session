import threading


class RWLock:
    def __init__(self):
        self.__lock = threading.Lock()
        self.__reading_num = 0
        self.__writing = False
        self.__cond = threading.Condition(self.__lock)

    def acquire_read(self, blocking: bool = True) -> bool:
        with self.__lock:
            if blocking:
                while not self.__readable():
                    self.__cond.wait()
            else:
                if not self.__readable():
                    return False
            self.__reading_num += 1
        return True

    def release_read(self):
        with self.__lock:
            assert self.__reading_num > 0
            self.__reading_num -= 1
            self.__cond.notify_all()

    def acquire(self, blocking: bool = True) -> bool:
        with self.__lock:
            if blocking:
                while not self.__writeable():
                    self.__cond.wait()
            else:
                if not self.__writeable():
                    return False
            self.__writing = True
        return True

    def release(self):
        with self.__lock:
            assert self.__writing
            self.__writing = False
            self.__cond.notify_all()

    def read_locked(self) -> bool:
        with self.__lock:
            readable = self.__readable()
        return not readable

    def write_locked(self) -> bool:
        with self.__lock:
            writeable = self.__writeable()
        return not writeable

    def __readable(self) -> bool:
        return not self.__writing

    def __writeable(self) -> bool:
        return not self.__writing and self.__reading_num == 0
