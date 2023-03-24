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
    assert len(messages) >= 2  # 确保至少有两条消息
    i = len(messages) - 2

    # 最后两条消息，如果 token 数超过 1536，则精简消息，优先精简用户的消息
    token = messages[i].tokens + messages[i].tokens + 2
    if token > 1536:
        messages[i].content = prune_message(messages[i])
        messages[i].tokens = token_len(messages[i].content)
        token = messages[i].tokens + messages[i + 1].tokens + 2
        if token > 1536:
            messages[i + 1].content = prune_message(messages[i + 1])
            messages[i + 1].tokens = token_len(messages[i + 1].content)
            token = messages[i + 1].tokens + messages[i].tokens + 2
    i -= 2

    # 每两条消息为一组，精简消息，计算 token 数，如果 token 数超过 1024，则停止
    while i >= 0:
        messages[i + 1].content = prune_message(messages[i + 1])
        messages[i + 1].tokens = token_len(messages[i + 1].content)
        messages[i].content = prune_message(messages[i])
        messages[i].tokens = token_len(messages[i].content)
        token += messages[i + 1].tokens + messages[i].tokens + 2
        if token > 1024:
            break
        i -= 2
    i += 2

    history = ""
    messages = messages[i:]
    for message in messages:
        history += sender_map[message.sender] + ': ' + message.content + "\n"
    return history, messages


def compile_message(message: Message) -> str:
    return message.content
