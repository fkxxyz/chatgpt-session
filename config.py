import json
from typing import NamedTuple, OrderedDict


class EngineConfig(NamedTuple):
    url: str


class Config(NamedTuple):
    engines: OrderedDict[str, EngineConfig]
    openai: dict

    @staticmethod
    def from_file(config_path: str):
        with open(config_path, "r") as f:
            config_str = f.read()
        config = Config(**json.loads(config_str))
        for engine in config.engines:
            config.engines[engine] = EngineConfig(**dict(config.engines[engine]))
        return config
