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


# 中文分类的 prompt
'''
以上是我作为一个人类输入到ChatGPT的请求，请对其内容进行分类，选择最符合其内容的类别。

选项：
A. 政治类话题（包括任何政治相关的学术）；
B. 不适当的话题（色情、违法）
C. 不适当的话题（不尊重、不礼貌、没有分寸）；
D. 不适当话题（恶心、令人呕吐）；
E. 愚蠢、荒谬的话题；
F. 过于简单、无意义的话题；
G. 搞笑的话题；
H. 非政治的学术性话题、服务咨询话题；
I. 不理智的话题（情绪化）；
J. 紧急话题；
K. 其它闲聊话题；
L. 无法分类（例如无法理解话题的含义）；

请根据聊天内容，选择最符合的分类。请只回复字母，不要解释，不要回复其它任何内容。
'''


# 分类消息
def classify_message(message: Message) -> str:
    return message.remark["raw"] + '''

------
The preceding is a request inputted to ChatGPT by me as a human. Please categorize its content and select the category that best fits.

Options:
A. Political topics (including any politically related academics);
B. Inappropriate topics (pornography, illegal);
C. Inappropriate topics (disrespectful, impolite, lacks tact);
D. Inappropriate topics (disgusting, nauseating);
E. Foolish, absurd topics;
F. Overly simplistic, meaningless topics;
G. Humorous topics;
H. Non-political academic topics, service consultation topics;
I. Irrational topics (emotional);
J. Urgent topics;
K. Other small talk topics;
L. Unable to classify (such as not understanding the meaning of the topic).

Please choose the category that best fits based on the chat content. Please only reply with a letter and do not explain and reply nothing else.
'''


classify_tip_map = {
    'A': '（请注意该类政治话题在中国属于敏感话题，严重违反法律，请开始严肃地拒绝该话题）',
    'B': '（该话题不适当，不要说抱歉，请进行严厉地批评、谴责和教育）',
    'C': '',
    'D': '（该话题不适当或过于愚蠢恶心，所以请用吐槽、怀疑对方智商的语气回应）',
    'E': '（该话题过于愚蠢荒谬，所以请用搞笑、吐槽、怀疑对方智商的语气回应）',
    'F': '（该话题过于愚蠢无意义，所以请用搞笑、吐槽、怀疑对方智商的语气回应）',
    'G': '（这是在开玩笑，请用搞笑、调侃的方式回应）',
    'H': '',
    'I': '（该话题不理智，请先表示理解情绪，然后进行安抚）',
    'J': '',
    'K': '（闲聊话题，可用有趣的方式回应）',
    'L': '',
}


def compile_message(message: Message) -> str:
    classify_result = message.remark.get("classify", "")
    if len(classify_result) == 0:
        return message.remark["raw"]
    classify_letter = classify_result[0].upper()
    tip = classify_tip_map.get(classify_letter, '')
    if len(tip) == 0:
        return message.remark["raw"]

    return message.remark["raw"] + '\n\n' + tip


def extract_response(message_str: str) -> str:
    return message_str
