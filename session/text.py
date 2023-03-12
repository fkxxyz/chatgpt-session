import json
import os

import error


class SessionText:
    def __init__(self, d: str):
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
            with open(os.path.join(d, "compress.txt"), "r") as f:
                self.t_compress: str = f.read()
            with open(os.path.join(d, "compress2.txt"), "r") as f:
                self.t_compress2: str = f.read()

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

    def compress(self, params: dict, old_memo: str) -> str:
        if len(old_memo) == 0:
            prompt = self.t_compress
        else:
            prompt = self.t_compress2
        for key in params:
            prompt = prompt.replace("${" + key + "}", params[key])
        if len(old_memo) != 0:
            prompt = prompt.replace("${memo}", old_memo)
        return prompt

    def inherit(self, params: dict, memo: str, history: str) -> str:
        guide = self.t_inherit
        for key in params:
            guide = guide.replace("${" + key + "}", params[key])
        guide = guide.replace("${memo}", memo)
        guide = guide.replace("${history}", history)
        return guide
