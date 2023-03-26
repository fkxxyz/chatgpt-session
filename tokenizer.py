import os
import threading
from typing import Any

tokenizer: Any | None = None


def __tokenizer_initialize():
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from transformers import GPT2TokenizerFast
    global tokenizer
    tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")


__tokenizer_thread = threading.Thread(target=__tokenizer_initialize)
__tokenizer_thread.start()


def token_len(text: str) -> int:
    if tokenizer is None:
        __tokenizer_thread.join()
    return len(tokenizer(text)['input_ids'])
