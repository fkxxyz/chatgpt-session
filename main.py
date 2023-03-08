#!/usr/bin/env python3
# -*- encoding:utf-8 -*-

import argparse
import os

from server import app
from server.common import globalObject


def run(host: str, port: int, data: str, config: str, cache: str):
    from waitress import serve
    globalObject.data = data
    globalObject.cache_path = cache
    globalObject.config_path = config
    serve(app, host=host, port=port)


def main() -> int:
    home_path = os.getenv("HOME")
    parser = argparse.ArgumentParser(description="chatgpt session")
    parser.add_argument('--data', '-d', type=str, help='text data path', default='./ui/dist')
    parser.add_argument('--host', '-o', type=str, help='host', default="127.0.0.1")
    parser.add_argument('--port', '-p', type=int, help='port', default=9988)
    parser.add_argument('--config', '-c', type=str, help='config.json',
                        default=os.path.join(home_path, ".config", "chatgpt-session", "config.json"))
    parser.add_argument('--cache', '-e', type=str, help='cache directory',
                        default=os.path.join(home_path, ".cache", "chatgpt-session"))
    args = parser.parse_args()
    run(args.host, args.port, args.data, args.config, args.cache)
    return 0


if __name__ == "__main__":
    exit(main())
