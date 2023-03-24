import copy
from dataclasses import dataclass
from typing import List

import engine.openai_chat
from tokenizer import token_len


@dataclass
class EnginePointer:
    # 帐号等级
    level: int = 65536

    # 引擎
    engine: str = ""

    # 帐号
    account: str = ""

    # 状态
    status: int = 0
    UNINITIALIZED = 0  # 未初始化的（刚创建或刚替换）
    IDLE = 1  # 空闲，可接收消息
    FULLED = 2  # token 数量已满（无法再接收新消息，接下来需要总结）
    SUMMARIZED = 3  # 总结完毕（无法再接收新消息，接下来需要合并）
    MERGED = 4  # 合并完毕（无法再接收新消息，接下来需要替换、继承）

    # 总结出的临时备忘录
    summary: str = ""

    # 总结出的备忘录
    memo: str = ""

    # AI 最后回复的消息的下标
    ai_index: int = 0

    # 标题（仅用于网页版）
    title: str = ""

    # 会话 id （仅网页版，如果该字段被设置，那么表示已被初始化）
    id: str = ""

    # 消息 id （仅网页版，指向 AI 回复的最后一个消息的 id）
    mid: str = ""

    # 新消息 id （仅网页版，指向 AI 正在回复的消息的 id）
    new_mid: str = ""

    # 提示
    prompt: str = ""


@dataclass
class Message:
    mid: str
    sender: int
    content: str
    tokens: int
    remark: dict

    AI = 0
    USER = 1
    __openai_chat_role = {
        AI: engine.openai_chat.Message.ASSISTANT,
        USER: engine.openai_chat.Message.USER,
    }

    def to_openai_chat(self) -> engine.openai_chat.Message:
        return engine.openai_chat.Message(
            Message.__openai_chat_role[self.sender],
            self.content,
        )


@dataclass
class CurrentConversation:
    guide: str
    memo: str
    recent_history: str
    messages: List[Message]
    pointer: EnginePointer
    tokens: int

    @staticmethod
    def create(guide, memo: str = "", recent_history: str = ""):
        return CurrentConversation(
            guide,
            memo,
            recent_history,
            [],
            EnginePointer(),
            token_len(guide) + 1,
        )

    @staticmethod
    def from_dict(d: dict):
        new_d = copy.deepcopy(d)
        new_d["pointer"] = EnginePointer(**new_d["pointer"])
        messages = []
        for message in new_d["messages"]:
            messages.append(Message(**message))
        new_d["messages"] = messages
        return CurrentConversation(**new_d)

    def append_message(self, message: Message):
        self.messages.append(message)
        self.tokens += token_len(message.content) + 1
