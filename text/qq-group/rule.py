import copy
import re
from typing import List

from memory import Message

from tokenizer import token_len


def get_raw_message(message: Message) -> str:
    if "raw" in message.remark:
        return message.remark["raw"]
    return message.content


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

    origin_messages = copy.deepcopy(messages)

    for i in range(len(messages)):
        messages[i].content = get_raw_message(messages[i])
        messages[i].tokens = token_len(messages[i].content)

    i = len(messages) - 2

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


# 分类消息
def classify_message(message: Message) -> str:
    prompt = message.remark["raw"] + '''

------
The preceding is a request inputted to ChatGPT by me as a human. Please categorize its content and select the category that best fits.

Options:'''
    if token_len(message.content) > 1024:
        prompt += message.remark["raw"] + '''
A. Sensitive Topics in China (Including politics, political science, political system, government system, social system, social form, Marxism, ideology, modern Chinese history, Internet censorship circumvention, VPN technology or software，network accelerator, etc.; excluding ethics and morality, gender and sexual orientation, social responsibility);
B. Inappropriate topics (pornography, illegal);
L. Other topics;
'''
    else:
        prompt += message.remark["raw"] + '''
A. Sensitive Topics in China (Including politics, political science, political system, government system, social system, social form, Marxism, ideology, modern Chinese history, Internet censorship circumvention, VPN technology or software，network accelerator, etc.; excluding ethics and morality, gender and sexual orientation, social responsibility);
B. Inappropriate topics (pornography, illegal);
C. Want to know about this AI (including name, age, feature, characteristics, abilities, personality, etc.)
D. Inappropriate topics (disrespectful, impolite, lacks tact);
E. Inappropriate topics (disgusting, nauseating);
F. Absurd, illogical topics (against common sense);
G. Brain teasers with logic traps;
H. Foolishly simple, pointless, worthless topics;
I. Interest and hobby topics (such as entertainment programs, movies, sports, etc.);
J. Humorous topics;
K. Creation/Writing (including all sci-fi, illogical);
L. Other academic topics (other than option A), service consulting topics;
M. Asking about personal decisions;
N. Asking or talking about personal mental or emotional distress;
O. Urgent topics;
P. Other small talk topics not related to the AI (such as weather, etc);
Q. Unable to classify (such as not understanding the meaning of the topic).
'''

    if len(message.remark["raw"]) > 96:
        prompt += '''
Please output in the following format:
```
Classification: X
'''
    else:
        prompt += '''
Please translate the content to be classified into English first, and then write the classification number.
Please output in the following format:
```
Translation to English: <content>
Classification: X
'''
    return prompt


classify_tip_map = {
    'A': '（请注意该类话题在中国属于敏感话题，严重违反法律，请30字以内拒绝）',
    'B': '（话题走向不适当，请30字以内拒绝）',
    'C': '',
    'D': '（话题走向可能不适当，请30字以内友好回应）',
    'E': '（话题走向可能不适当或过于愚蠢，请30字以内友好回应）',
    'F': '（话题走向过于愚蠢荒谬搞笑，请指出荒谬、不现实或搞笑的地方简单30字以内回应）',
    'G': '（话题趋向过于简单，请打破常规逻辑结合现实找到隐藏的最佳可能性）',
    'H': '（话题走向过于简单无意义，可能在测试你的能力，请进行30字以内回应）',
    'I': '',
    'J': '（请用两三句简单30字以内回应）',
    'K': '',
    'L': '',
    'M': '（尽量考虑周全，有必要时询问更多细节）',
    'N': '（先正常回应，然后询问更多细节）',
    'O': '',
    'P': '（可用两三句简单30字以内回应）',
    'Q': '',
}


def compile_message(message: Message) -> str:
    classify_result = message.remark.get("classify", "")
    if len(classify_result) == 0:
        return message.remark["raw"]
    match = re.search(r'Classification:\s*(\w)', classify_result)
    if match is None:
        return message.remark["raw"]
    classify_letter = match.group(1)
    tip = classify_tip_map.get(classify_letter, '')
    if len(tip) == 0:
        return message.remark["raw"]

    return message.remark["raw"] + '\n\n' + tip


def extract_response(message_str: str) -> str:
    return message_str
