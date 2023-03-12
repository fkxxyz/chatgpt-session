import copy
from dataclasses import dataclass
from typing import List

from tokenizer import token_len


@dataclass
class EnginePointer:
    engine: str
    account: str
    fulled: bool
    pointer: dict


@dataclass
class Message:
    sender: int
    content: str

    AI = 0
    USER = 1


@dataclass
class CurrentConversation:
    guide: str
    memo: str
    recent_history: str
    messages: List[Message]
    pointer: EnginePointer
    tokens: int

    @staticmethod
    def create(guide):
        return CurrentConversation(
            guide,
            "",
            "",
            [],
            EnginePointer("", "", False, {}),
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
