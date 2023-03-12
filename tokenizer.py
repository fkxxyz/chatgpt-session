from transformers import GPT2TokenizerFast

tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")


def token_len(text: str) -> int:
    return len(tokenizer(text)['input_ids'])
