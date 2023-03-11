import threading


class RWLock:
    def __init__(self):
        self.__lock = threading.Lock()
        self.__reading_num = 0
        self.__writing = False
        self.__cond = threading.Condition(self.__lock)

    def acquire_read(self, blocking: bool = True) -> bool:
        self.__lock.acquire()
        if blocking:
            while not self.__readable():
                self.__cond.wait()
        else:
            if not self.__readable():
                self.__lock.release()
                return False
        self.__reading_num += 1
        self.__lock.release()
        return True

    def release_read(self):
        self.__lock.acquire()
        assert self.__reading_num > 0
        self.__reading_num -= 1
        self.__cond.notify_all()
        self.__lock.release()

    def acquire(self, blocking: bool = True):
        self.__lock.acquire()
        if blocking:
            while not self.__writeable():
                self.__cond.wait()
        else:
            if not self.__writeable():
                self.__lock.release()
                return False
        self.__writing = True
        self.__lock.release()
        return True

    def release(self):
        self.__lock.acquire()
        assert self.__writing
        self.__writing = False
        self.__cond.notify_all()
        self.__lock.release()

    def read_locked(self) -> bool:
        self.__lock.acquire()
        readable = self.__readable()
        self.__lock.release()
        return not readable

    def write_locked(self) -> bool:
        self.__lock.acquire()
        writeable = self.__writeable()
        self.__lock.release()
        return not writeable

    def __readable(self) -> bool:
        return not self.__writing

    def __writeable(self) -> bool:
        return not self.__writing and self.__reading_num == 0
