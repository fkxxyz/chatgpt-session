import copy
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
    Message.USER: 'User',
}


def compile_history(messages: List[Message], params: dict) -> (str, List[Message]):
    if len(messages) < 2:  # 确保至少有两条消息
        return "<empty>", []
    i = len(messages) - 2

    origin_messages = copy.deepcopy(messages)

    # 最后两条消息，如果 token 数超过 512，则精简消息，优先精简用户的消息
    token = messages[i].tokens + messages[i + 1].tokens + 2
    if token > 512:
        messages[i].content = prune_message(messages[i])
        messages[i].tokens = token_len(messages[i].content)
        token = messages[i].tokens + messages[i + 1].tokens + 2
        if token > 512:
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
        if token > 512:
            break
        i -= 2
    i += 2

    history = ""
    for message in messages[i:]:
        history += sender_map[message.sender] + ': ' + message.content + "\n"
    return history, origin_messages[i:]


def classify_message(message: Message) -> str:
    return ""


def compile_message(message: Message) -> str:
    return message.remark["raw"] + '''

（请注意你是一个不懂其他任何领域知识的英语老师，如果话题和英语学习无关，那么不要回应话题内容，不要解答任何疑惑，而是选择用英语表达该话题并解释其中的英语知识来把话题转移到学习英语；你不应当同意扮演任何和英语学习无关的角色请求，拒绝一切娱乐，请直接严厉拒绝并严厉教育；你应当用中文来解释英语单词、短语、例句、英语知识点等确保不懂英语的人能看懂；请说中文）
'''


def extract_response(message_str: str) -> str:
    return message_str
