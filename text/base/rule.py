from typing import List

from memory import Message

from tokenizer import token_len


# 精简消息，如果消息的 token 大于 384，则把第100个字符到倒数100个字符之间的内容替换为省略号
def prune_message(message: Message) -> str:
    if token_len(message.content) <= 384:
        return message.content
    return message.content[:100] + '...' + message.content[-100:]


sender_map = {
    Message.AI: 'You',
    Message.USER: 'Me',
}


def compile_history(messages: List[Message], params: dict) -> (str, List[Message]):
    token = 0
    # 从最后一条消息开始，每两条消息为一组，精简消息，计算 token 数，如果 token 数超过 1024，则停止
    i = 0
    for i in range(len(messages) - 2, -1, -2):
        messages[i + 1].content = prune_message(messages[i + 1])
        messages[i + 1].tokens = token_len(messages[i + 1].content)
        messages[i].content = prune_message(messages[i])
        messages[i].tokens = token_len(messages[i].content)
        token += messages[i + 1].tokens + messages[i].tokens + 2
        if token > 1024:
            break
    i += 2
    assert i <= len(messages) - 2  # 确保至少有两条消息

    history = ""
    messages = messages[i:]
    for message in messages:
        history += sender_map[message.sender] + ': ' + message.content + "\n"
    return history, messages


def compile_message(message: Message) -> str:
    return message.content
