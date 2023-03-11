#!/usr/bin/env python3
# -*- encoding:utf-8 -*-

import argparse
import os

from server import app
from server.common import globalObject
from session import SessionManager


def run(host: str, port: int, text: str, config: str, database: str):
    os.makedirs(database, exist_ok=True)

    globalObject.text = text
    globalObject.config_path = config
    globalObject.database = database
    globalObject.session_manager = SessionManager(text, database)

    from waitress import serve
    serve(app, host=host, port=port)


def main() -> int:
    parser = argparse.ArgumentParser(description="chatgpt session")
    parser.add_argument('--host', '-o', type=str, help='host', default="127.0.0.1")
    parser.add_argument('--port', '-p', type=int, help='port', default=9988)
    parser.add_argument('--text', '-t', type=str, help='text data path', default='./text')
    parser.add_argument('--config', '-c', type=str, help='config.json', default="config.json")
    parser.add_argument('--database', '-d', type=str, help='database path', default='./database')
    args = parser.parse_args()
    run(args.host, args.port, args.text, args.config, args.database)
    return 0


if __name__ == "__main__":
    exit(main())
