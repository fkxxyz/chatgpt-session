import json
import os
import shutil
import threading
from typing import List

import error
from rwlock import RWLock


class SessionText:
    def __init__(self, d: str):
        # 参数
        try:
            with open(os.path.join(d, "params.json"), "r") as f:
                self.params: dict = json.loads(f.read())
        except FileNotFoundError:
            raise error.InvalidParamError(f"no such text {d}")
        except json.JSONDecodeError as e:
            raise error.InternalError(f"invalid text params.json in {d}: {e}")

        try:
            # 创建提示
            with open(os.path.join(d, "create.txt"), "r") as f:
                self.t_create: str = f.read()

            # 压缩需要的提示
            with open(os.path.join(d, "compress.txt"), "r") as f:
                self.t_compress: str = f.read()

            # 继承需要的提示
            with open(os.path.join(d, "inherit.txt"), "r") as f:
                self.t_inherit: str = f.read()
        except OSError as e:
            raise error.InternalError(f"invalid text in {d}: {e}")


class Session:
    def __init__(self, d: str):
        with open(os.path.join(d, "index.json"), "r") as f:
            j = json.loads(f.read())
        self.id: str = j["id"]
        self.type: str = j["type"]
        self.params: dict = j["params"]

    def __dict__(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "params": self.params,
        }


class SessionManager:
    def __init__(self, text: str, database: str):
        assert len(text) > 0
        assert len(database) > 0

        self.__lock = RWLock()

        self.__text_path = text
        self.__database = database

    def list(self) -> List[Session]:
        self.__lock.acquire_read()
        try:
            result = []
            for id_ in os.listdir(self.__database):
                session_path = os.path.join(self.__database, id_)
                if not os.path.isdir(session_path):
                    continue
                try:
                    s = Session(session_path)
                except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
                    print(e)
                    continue
                result.append(s)
        except OSError as e:
            raise error.InternalError(e)
        finally:
            self.__lock.release_read()
        return result

    def add(self, id_: str, type_: str, params: dict) -> Session:
        if len(id_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session id: {id_}")
        if len(type_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session type: {type_}")

        self.__lock.acquire()
        try:
            try:
                text = SessionText(os.path.join(self.__text_path, type_))
            except error.NotFoundError:
                raise error.NotFoundError(f"no such session type: {type_}")
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
                }))
            return Session(os.path.join(self.__database, id_))
        except FileExistsError:
            raise error.InvalidParamError(f"session already exists: {id_}")
        except OSError as e:
            raise error.InternalError(e)
        finally:
            self.__lock.release()

    def remove(self, id_: str):
        if len(id_.strip()) == 0:
            raise error.InvalidParamError(f"invalid session id: {id_}")

        self.__lock.acquire()
        try:
            shutil.rmtree(os.path.join(self.__database, id_))
        except FileNotFoundError:
            raise error.InvalidParamError(f"no such session: {id_}")
        except OSError as e:
            raise error.InternalError(e)
        finally:
            self.__lock.release()
