import http
import json
import time
from dataclasses import dataclass
from typing import Tuple, Callable, List

import openai
import requests

import engine
import error
from engine.openai_chat import OpenAIChatCompletion
from engine.rev_chatgpt_web import RevChatGPTWeb, AccountInfo, SendResponse, GetMessageResponse
from memory import CurrentConversation, Message, EnginePointer


def call_until_success(fn: Callable[[], requests.Response]) -> bytes:
    while True:
        try:
            resp = fn()
        except requests.RequestException as e:
            print(f"请求错误： {e}")
            print(f"等待 10 秒后重试 ...")
            time.sleep(10)
            continue
        if resp.status_code != http.HTTPStatus.OK:
            print(f"响应返回错误 {resp.status_code}： {resp.content.decode()}")
            print(f"等待 10 秒后重试 ...")
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
    409: SleepStrategy(10000, 1, 10000),
    500: SleepStrategy(10000, 2, 120000),
    503: SleepStrategy(10000, 2, 120000),
    522: SleepStrategy(10000, 2, 120000),
    524: SleepStrategy(10000, 2, 60000),
    529: SleepStrategy(10000, 2, 60000),
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
            if resp.status_code == http.HTTPStatus.UNAUTHORIZED:
                raise error.Unauthorized(resp.content)
            if resp.status_code == http.HTTPStatus.TOO_MANY_REQUESTS:
                raise error.ServerIsBusy(resp.content)
            raise error.InternalError(resp.status_code, resp.content)
        if wait_ms == 0:
            wait_ms = sleep_strategy.start
        else:
            wait_ms *= sleep_strategy.growth
        if wait_ms > sleep_strategy.upper:
            wait_ms = sleep_strategy.upper
        print(f"send 错误 {resp.status_code}： {resp.content.decode()}")
        print(f"等待 {wait_ms} 毫秒后重试 ...")
        time.sleep(float(wait_ms) / 1000)


def openai_chat_send(api: OpenAIChatCompletion, messages: List[engine.openai_chat.Message]) -> str:
    while True:
        try:
            return api.send(messages)
        except openai.error.APIConnectionError as err:
            print(f"send 错误： {err}")
            print(f"等待 10 秒后重试 ...")
            time.sleep(10)
            continue


class Scheduler:
    def __init__(self, engines: dict):
        self.__engines: dict = engines

    # 评估一个会话的请求应该被调度到哪个引擎的哪个账户上，返回引擎id和账户id
    def evaluate(self, pointer: EnginePointer) -> Tuple[str, str]:
        api: RevChatGPTWeb = self.__engines[RevChatGPTWeb.__name__]
        accounts_dict = json.loads(call_until_success(api.accounts))
        accounts: List[AccountInfo] = []
        accounts_found = False
        for account_dict in accounts_dict:
            account = AccountInfo(**account_dict)
            if account.id == pointer.account:
                accounts_found = True
            accounts.append(account)

        # 如果不是新创建会话，则不改变账户
        if pointer.status != EnginePointer.UNINITIALIZED and pointer.engine == RevChatGPTWeb.__name__ and accounts_found:
            assert len(pointer.account) != 0
            return pointer.engine, pointer.account

        if len(accounts_dict) > 0:
            if pointer.status == EnginePointer.UNINITIALIZED or pointer.engine != RevChatGPTWeb.__name__:
                # 如果是新创建的会话，则选择负载最低的账户
                accounts.sort(key=account_load)
                return RevChatGPTWeb.__name__, accounts[0].id

        return OpenAIChatCompletion.__name__, ""

    def send(self, current: CurrentConversation) -> str:
        assert current.pointer.engine in self.__engines

        if current.pointer.engine == RevChatGPTWeb.__name__:
            # 使用网页版的免费 ChatGPT
            api: RevChatGPTWeb = self.__engines[RevChatGPTWeb.__name__]

            if current.pointer.status == EnginePointer.UNINITIALIZED:
                # 第一次发送消息，需要新建会话，发送 guide
                mid = rev_chatgpt_web_send(api, current.pointer.account, current.guide)

                # 设置新建会话的标题
                new_message = GetMessageResponse.from_body(call_until_success(lambda: api.get(mid)))
                call_until_success(lambda: api.set_title(
                    current.pointer.account,
                    new_message.id,
                    current.pointer.title,
                ))
            elif current.pointer.status == EnginePointer.IDLE:
                # 非第一次发送消息，发送最后一条消息即可
                last_message = current.messages[-1]
                assert last_message.sender == Message.USER  # 最后一条消息必须是用户
                mid = rev_chatgpt_web_send(
                    api, current.pointer.account, last_message.content,
                    current.pointer.id, current.pointer.mid,
                )
            else:
                # 总 token 已满，需要压缩
                assert current.messages[-1].sender == Message.AI  # 最后一条消息必须是 AI
                mid = rev_chatgpt_web_send(
                    api, current.pointer.account, current.pointer.prompt,
                    current.pointer.id, current.pointer.mid,
                )

            return mid
        elif current.pointer.engine == OpenAIChatCompletion.__name__:
            # openai 的 chat
            api: OpenAIChatCompletion = self.__engines[OpenAIChatCompletion.__name__]

            messages: List[engine.openai_chat.Message] = [engine.openai_chat.Message(
                engine.openai_chat.Message.USER,
                current.guide,
            )]
            for message in current.messages:
                messages.append(message.to_openai_chat())

            if current.pointer.status >= EnginePointer.IDLE:
                # 总 token 已满，需要压缩
                assert current.messages[-1].sender == Message.AI  # 最后一条消息必须是 AI
                messages.append(engine.openai_chat.Message(
                    engine.openai_chat.Message.USER,
                    current.pointer.prompt,
                ))
            return openai_chat_send(api, messages)
        else:
            raise error.NotImplementedError1(f"no such engine: f{current.pointer.engine}")

    def get(self, pointer: EnginePointer) -> GetMessageResponse:
        assert pointer.engine in self.__engines

        if pointer.engine == RevChatGPTWeb.__name__:
            # 使用网页版的免费 ChatGPT
            api: RevChatGPTWeb = self.__engines[RevChatGPTWeb.__name__]

            new_message = GetMessageResponse.from_body(
                call_until_success(lambda: api.get(pointer.new_mid)))
        elif pointer.engine == OpenAIChatCompletion.__name__:
            raise error.NotImplementedError1(f"get() not support engine: f{pointer.engine}")
        else:
            raise error.NotImplementedError1(f"no such engine: f{pointer.engine}")
        return new_message
