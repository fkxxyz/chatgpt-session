import json
import os
from dataclasses import dataclass
from typing import List

import error
from memory import Message


@dataclass
class Rule:
    sender: List[str]
    message: str


class SessionText:
    def __init__(self, d: str):
        # 规则
        try:
            with open(os.path.join(d, "rule.json"), "r") as f:
                self.rule: Rule = Rule(**json.loads(f.read()))
        except FileNotFoundError:
            raise error.InvalidParamError(f"no such text {d}")
        except json.JSONDecodeError as e:
            raise error.InternalError(f"invalid text rule.json in {d}: {e}")

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
            with open(os.path.join(d, "summary.txt"), "r") as f:
                self.t_summary: str = f.read()
            with open(os.path.join(d, "merge.txt"), "r") as f:
                self.t_merge: str = f.read()

            # 继承需要的提示
            with open(os.path.join(d, "inherit.txt"), "r") as f:
                self.t_inherit: str = f.read()
        except OSError as e:
            raise error.InternalError(f"invalid text in {d}: {e}")

    def create(self, params: dict) -> str:
        guide = self.t_create
        for key in params:
            guide = guide.replace("${" + key + "}", params[key])
        return guide

    def summary(self) -> str:
        return self.t_summary

    def merge(self, params: dict, memo: str, summary: str) -> str:
        prompt = self.t_merge
        for key in params:
            prompt = prompt.replace("${" + key + "}", params[key])
        prompt = prompt.replace("${memo}", memo)
        prompt = prompt.replace("${summary}", summary)
        return prompt

    def inherit(self, params: dict, memo: str, history: str) -> str:
        guide = self.t_inherit
        for key in params:
            guide = guide.replace("${" + key + "}", params[key])
        guide = guide.replace("${memo}", memo)
        guide = guide.replace("${history}", history)
        return guide

    def message(self, message: Message, params: dict) -> str:
        result = self.rule.message
        result = result.replace("${sender}", self.rule.sender[message.sender])
        for key in params:
            result = result.replace("${" + key + "}", params[key])
        for key in message.remark:
            result = result.replace("${" + key + "}", message.remark[key])
        result = result.replace("${content}", message.content)
        return result
