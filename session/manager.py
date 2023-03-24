from datetime import datetime
import json
import os

from collections import OrderedDict
from typing import List

import error
from rwlock import RWLock
from schedule import Scheduler
from session.session import Session
from session.text import SessionText


class SessionManager:
    def __init__(self, text: str, database: str, scheduler: Scheduler):
        assert len(text) > 0
        assert len(database) > 0

        self.__lock = RWLock()

        self.__text_path = text
        self.__database = database
        self.__scheduler = scheduler

        self.__texts: OrderedDict[str, SessionText] = OrderedDict()
        self.__load_text()

        self.__sessions: OrderedDict[str, Session] = OrderedDict()
        self.__load_sessions()

    def __load_text(self):
        try:
            for type_ in os.listdir(self.__text_path):
                if type_.startswith("."):
                    continue
                text_path = os.path.join(self.__text_path, type_)
                if not os.path.isdir(text_path):
                    continue
                try:
                    t = SessionText(text_path)
                except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
                    print(e)
                    continue
                self.__texts[type_] = t
        except OSError as e:
            raise error.InternalError(e)

    def __load_sessions(self):
        try:
            for id_ in os.listdir(self.__database):
                if id_.startswith("."):
                    continue
                session_path = os.path.join(self.__database, id_)
                if not os.path.isdir(session_path):
                    continue
                try:
                    s = Session(session_path, self.__texts, self.__scheduler)
                except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
                    print(e)
                    continue
                self.__sessions[id_] = s
        except OSError as e:
            raise error.InternalError(e)

    def list(self) -> List[Session]:
        self.__lock.acquire_read()
        try:
            result = []
            for id_ in self.__sessions:
                result.append(self.__sessions[id_])
        finally:
            self.__lock.release_read()
        return result

    def add(self, id_: str, type_: str, params: dict) -> Session:
        if len(id_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session id: {id_}")
        if len(type_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session type: {type_}")
        if id_ in self.__sessions:
            raise error.InvalidParamError(f"session already exists: {id_}")

        self.__lock.acquire()
        try:
            try:
                text = SessionText(os.path.join(self.__text_path, type_))
            except error.NotFoundError:
                raise error.NotFoundError(f"no such session type: {type_}")
            try:
                level = int(params.get("level", self.__texts[type_].level))
            except ValueError:
                raise error.InvalidParamError(f"invalid param: level: {params.get('level')}")
            params["level"] = level
            for key in text.params:
                try:
                    params[key].strip()
                except KeyError:
                    raise error.InvalidParamError(f"invalid param: no key: {key}")
            os.makedirs(os.path.join(self.__database, id_))
            with open(os.path.join(self.__database, id_, "index.json"), 'w') as f:
                f.write(json.dumps({
                    "id": id_,
                    "type": type_,
                    "params": params,
                }, ensure_ascii=False, indent=2))
            s = Session(os.path.join(self.__database, id_), self.__texts, self.__scheduler)
            self.__sessions[id_] = s
            return s
        except FileExistsError:
            raise error.InvalidParamError(f"session already exists: {id_}")
        except OSError as e:
            raise error.InternalError(e)
        finally:
            self.__lock.release()

    def get(self, id_: str) -> Session:
        if len(id_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session id: {id_}")
        s = self.__sessions.get(id_)
        if s is None:
            raise error.InvalidParamError(f"no such session: {id_}")
        return s

    def get_default(self) -> Session:
        if len(self.__sessions) > 0:
            return self.__sessions[next(iter(self.__sessions))]

    def remove(self, id_: str):
        if len(id_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session id: {id_}")
        if id_ not in self.__sessions:
            raise error.InvalidParamError(f"no such session: {id_}")

        self.__lock.acquire()
        try:
            del self.__sessions[id_]
            suffix = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
            os.rename(os.path.join(self.__database, id_), os.path.join(self.__database, f".{id_}.{suffix}"))
        except FileNotFoundError:
            raise error.InvalidParamError(f"no such session: {id_}")
        except OSError as e:
            raise error.InternalError(e)
        finally:
            self.__lock.release()
