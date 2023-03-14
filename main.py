#!/usr/bin/env python3
# -*- encoding:utf-8 -*-

import argparse
import json
import logging
import os
import sys

from config import Config
from engine.rev_chatgpt_web import RevChatGPTWeb
from schedule import Scheduler
from server import app
from server.common import globalObject
from session.manager import SessionManager


def run(host: str, port: int, text: str, config_path: str, database: str):
    os.makedirs(database, exist_ok=True)

    config = Config.from_file(config_path)
    engines = RevChatGPTWeb(config.engines[RevChatGPTWeb.__name__].url)
    scheduler = Scheduler(engines)

    globalObject.text = text
    globalObject.database = database
    globalObject.session_manager = SessionManager(text, database, scheduler)

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

    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format=LOG_FORMAT, handlers=[logging.StreamHandler(sys.stdout)])

    run(args.host, args.port, args.text, args.config, args.database)
    return 0


if __name__ == "__main__":
    exit(main())
