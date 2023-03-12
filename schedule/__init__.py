import http
import json
import time
from dataclasses import dataclass
from typing import Tuple, Callable, List

import requests

import error
from engine.rev_chatgpt_web import RevChatGPTWeb, AccountInfo, SendResponse, GetMessageResponse
from memory import CurrentConversation, Message, EnginePointer


def call_until_success(fn: Callable[[], requests.Response]) -> bytes:
    while True:
        try:
            resp = fn()
        except requests.RequestException as e:
            print(f"请求错误： {e}")
            print(f"等待 10 毫秒后重试 ...")
            time.sleep(10)
            continue
        if resp.status_code != http.HTTPStatus.OK:
            print(f"响应返回错误 {resp.status_code}： {resp.content.decode()}")
            print(f"等待 10 毫秒后重试 ...")
            time.sleep(10)
            continue

        return resp.content


def account_load(account: AccountInfo) -> int:
    return account.counter * 2 if account.is_busy else account.counter


@dataclass
class SleepStrategy:
    start: int
    growth: int
    upper: int


sleep_strategies = {
    409: SleepStrategy(10000, 2, 1200000),
    500: SleepStrategy(10000, 2, 120000),
    503: SleepStrategy(10000, 2, 120000),
    522: SleepStrategy(10000, 2, 120000),
}


def rev_chatgpt_web_send(api: RevChatGPTWeb, account: str, msg: str, id_: str = '', mid: str = '') -> str:
    wait_ms = 0
    while True:
        try:
            resp = api.send(account, msg, id_, mid)
        except requests.RequestException:
            time.sleep(10)
            continue
        if resp.status_code == http.HTTPStatus.OK:
            r = SendResponse(**json.loads(resp.content))
            return r.mid
        sleep_strategy = sleep_strategies.get(resp.status_code)
        if sleep_strategy is None:
            raise error.InternalError(resp.status_code, resp.content)
        if wait_ms == 0:
            wait_ms = sleep_strategy.start
        else:
            wait_ms *= sleep_strategy.growth
        if wait_ms > sleep_strategy.upper:
            wait_ms = sleep_strategy.upper
        print(f"send 错误 {resp.status_code}： {resp.content.decode()}")
        print(f"等待 {wait_ms} 毫秒后重试 ...")
        time.sleep(wait_ms)


class Scheduler:
    def __init__(self, engines: RevChatGPTWeb):
        self.__engines: dict = {
            RevChatGPTWeb.__name__: engines
        }

    # 评估一个会话的请求应该被调度到哪个引擎的哪个账户上，返回引擎id和账户id
    def evaluate(self, pointer: EnginePointer) -> Tuple[str, str]:
        api: RevChatGPTWeb = self.__engines[RevChatGPTWeb.__name__]
        while True:
            accounts_dict = json.loads(call_until_success(api.accounts))
            if len(accounts_dict) != 0:
                break
            time.sleep(10)
        accounts: List[AccountInfo] = []
        for account_dict in accounts_dict:
            accounts.append(AccountInfo(**account_dict))

        # 如果会话未满，则不改变账户
        if len(pointer.engine) != 0 and len(pointer.account) != 0 and not pointer.fulled:
            return pointer.engine, pointer.account

        # 如果会话已满，则选择负载最低的账户
        accounts.sort(key=account_load)
        return RevChatGPTWeb.__name__, accounts[0].id

    def send(self, current: CurrentConversation) -> str:
        assert current.pointer.engine in self.__engines

        if current.pointer.engine == RevChatGPTWeb.__name__:
            # 使用网页版的免费 ChatGPT
            api: RevChatGPTWeb = self.__engines[RevChatGPTWeb.__name__]
            if len(current.messages) == 0:
                # 第一次发送消息，需要新建会话，发送 guide
                mid = rev_chatgpt_web_send(api, current.pointer.account, current.guide)

                # 设置新建会话的标题
                new_message = GetMessageResponse.from_body(call_until_success(lambda: api.get(mid)))
                call_until_success(lambda: api.set_title(
                    current.pointer.account,
                    new_message.id,
                    current.pointer.pointer["title"],
                ))
            else:
                # 非第一次发送消息，发送最后一条消息即可
                last_message = current.messages[-1]
                assert last_message.sender == Message.USER  # 最后一条消息必须是用户
                mid = rev_chatgpt_web_send(
                    api, current.pointer.account, last_message.content,
                    current.pointer.pointer["id"], current.pointer.pointer["mid"],
                )

            return mid

    def get(self, pointer: EnginePointer) -> GetMessageResponse:
        assert pointer.engine in self.__engines

        if pointer.engine == RevChatGPTWeb.__name__:
            # 使用网页版的免费 ChatGPT
            api: RevChatGPTWeb = self.__engines[RevChatGPTWeb.__name__]
            new_message = GetMessageResponse.from_body(
                call_until_success(lambda: api.get(pointer.pointer["new_mid"])))
        else:
            raise error.NotImplementedError1(f"no such engine: f{pointer.engine}")
        return new_message
