import importlib
import json
import os
from copy import deepcopy
from typing import List, Any
import importlib.util

import error
from memory import Message


class SessionText:
    def __init__(self, d: str):
        # 规则
        spec = importlib.util.spec_from_file_location("rule", os.path.join(d, "rule.py"))
        self.rule: Any = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rule)

        # 参数
        try:
            with open(os.path.join(d, "params.json"), "r") as f:
                self.params: dict = json.loads(f.read())
        except FileNotFoundError:
            raise error.InvalidParamError(f"no such text {d}")
        except json.JSONDecodeError as e:
            raise error.InternalError(f"invalid text params.json in {d}: {e}")
        try:
            self.level: int = int(self.params["level"])
        except (KeyError, ValueError):
            raise error.InternalError(f"invalid level key in params.json")

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
            if type(params[key]) != str:
                continue
            guide = guide.replace("${" + key + "}", params[key])
        return guide

    def summary(self, params: dict) -> str:
        summary = self.t_summary
        for key in params:
            if type(params[key]) != str:
                continue
            summary = summary.replace("${" + key + "}", params[key])
        return summary

    def merge(self, params: dict, memo: str, summary: str) -> str:
        prompt = self.t_merge
        for key in params:
            if type(params[key]) != str:
                continue
            prompt = prompt.replace("${" + key + "}", params[key])
        prompt = prompt.replace("${memo}", memo)
        prompt = prompt.replace("${summary}", summary)
        return prompt

    def inherit(self, params: dict, memo: str, history: str) -> str:
        guide = self.t_inherit
        for key in params:
            if type(params[key]) != str:
                continue
            guide = guide.replace("${" + key + "}", params[key])
        guide = guide.replace("${memo}", memo)
        guide = guide.replace("${history}", history)
        return guide

    def compile_history(self, messages: List[Message], params: dict) -> (str, List[Message]):
        return self.rule.compile_history(deepcopy(messages), deepcopy(params))

    def classify_message(self, message: Message) -> str:
        return self.rule.classify_message(deepcopy(message))

    def compile_message(self, message: Message) -> str:
        return self.rule.compile_message(deepcopy(message))

    def extract_response(self, message_str: str) -> str:
        return self.rule.extract_response(message_str)
