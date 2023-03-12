import json
from dataclasses import dataclass

import requests


@dataclass
class AccountInfo:
    id: str
    email: str
    valid: bool
    counter: int
    is_busy: bool
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
        return GetMessageResponse(
            r["conversation_id"],
            r["message"]["id"],
            r["message"]["content"]["parts"][0],
            r["finished"],
        )


class RevChatGPTWeb:
    def __init__(self, url: str):
        self.__session: requests.Session = requests.Session()
        self.__session.headers.update({'Content-Type': 'application/octet-stream'})
        self.__url: str = url

    def accounts(self) -> requests.Response:
        return self.__session.get(self.__url + '/api/account/valid')

    def set_title(self, account: str, id_: str, title: str) -> requests.Response:
        params = {'account': account, 'id': id_}
        data = title.encode('utf-8')
        return self.__session.patch(self.__url + '/api/title', params=params, data=data)

    def history(self, account: str, id_: str) -> requests.Response:
        params = {'account': account, 'id': id_}
        return self.__session.get(self.__url + '/api/history', params=params)

    def send(self, account: str, msg: str, id_: str = '', mid: str = '') -> requests.Response:
        params = {'account': account, 'id': id_, 'mid': mid}
        return self.__session.post(self.__url + '/api/send', params=params, data=msg.encode('utf-8'))

    def get(self, mid: str) -> requests.Response:
        params = {'mid': mid}
        return self.__session.get(self.__url + '/api/get', params=params)
