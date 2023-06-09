import json
from dataclasses import dataclass

import requests


@dataclass
class AccountInfo:
    id: str
    email: str
    is_logged_in: bool
    counter: int
    is_busy: bool
    is_disabled: bool
    level: int
    err: str


@dataclass
class SendResponse:
    mid: str


@dataclass
class GetMessageResponse:
    id: str
    mid: str
    msg: str
    end: bool

    @staticmethod
    def from_body(body: bytes):
        r = json.loads(body)
        try:
            return GetMessageResponse(
                r["conversation_id"],
                r["message"]["id"],
                r["message"]["content"]["parts"][0],
                r["finished"],
            )
        except Exception as err:
            print(body.decode())
            raise err


class RevChatGPTWeb:
    def __init__(self, url: str):
        self.__session: requests.Session = requests.Session()
        self.__session.headers.update({'Content-Type': 'application/octet-stream'})
        self.__url: str = url

    def accounts(self, level: int = 65536) -> requests.Response:
        params = {'level': level}
        return self.__session.get(self.__url + '/api/account/valid', params=params, timeout=60)

    def set_title(self, account: str, id_: str, title: str) -> requests.Response:
        params = {'account': account, 'id': id_}
        data = title.encode('utf-8')
        return self.__session.patch(self.__url + '/api/title', params=params, data=data, timeout=60)

    def history(self, account: str, id_: str) -> requests.Response:
        params = {'account': account, 'id': id_}
        return self.__session.get(self.__url + '/api/history', params=params, timeout=60)

    def send(self, account: str, msg: str, id_: str = '', mid: str = '') -> requests.Response:
        params = {'account': account, 'id': id_, 'mid': mid}
        return self.__session.post(self.__url + '/api/send', params=params, data=msg.encode('utf-8'), timeout=60)

    def get(self, mid: str, stop=False) -> requests.Response:
        params = {'mid': mid}
        method = "PATCH" if stop else "GET"
        return self.__session.request(method, self.__url + '/api/get', params=params, timeout=60)

    def delete(self, account: str, id_: str) -> requests.Response:
        params = {'account': account, 'id': id_}
        return self.__session.delete(self.__url + '/api/conversation', params=params, timeout=60)

    def counter(self, account: str, n: int = 1) -> requests.Response:
        params = {'account': account, 'n': n}
        return self.__session.patch(self.__url + '/api/account/lock', params=params, timeout=60)
