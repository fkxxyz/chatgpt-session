import copy
from dataclasses import dataclass
from typing import List

import engine.openai_chat
from tokenizer import token_len


@dataclass
class EnginePointer:
    engine: str
    account: str
    fulled: bool
    memo: str
    initialized: bool
    ai_index: int
    pointer: dict


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
            EnginePointer("", "", False, "", False, 0, {}),
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
