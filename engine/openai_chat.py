from dataclasses import dataclass, asdict
from typing import List

import openai
from openai.error import AuthenticationError

import error


@dataclass
class Message:
    role: str
    content: str

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class OpenAIChatCompletion:
    def __init__(self, keys: List[str]):
        self.__index = 0
        self.__keys = keys

    def send(self, messages: List[Message], model="gpt-3.5-turbo") -> str:
        if not self.available():
            raise error.NoResource()

        messages_ = []
        for message in messages:
            messages_.append(asdict(message))

        while self.available():
            openai.api_key = self.__keys[self.__index]
            try:
                completion = openai.ChatCompletion.create(model=model, messages=messages_)
            except AuthenticationError as err:
                self.__index += 1
                continue
            return completion.choices[0].message.content
        raise error.NoResource()

    def available(self) -> bool:
        return self.__index <= len(self.__keys)
