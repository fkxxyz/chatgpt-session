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


# 中文分类的 prompt
'''
以上是我作为一个人类输入到ChatGPT的请求，请对其内容进行分类，选择最符合其内容的类别。

选项：
A. 政治或军事类话题（包括任何与政治相关的学术、时事、政府体制、社会制度、社会形态、马克思主义、意识形态等）；
B. 不适当的话题（色情、违法）
C. 不适当的话题（不尊重、不礼貌、没有分寸）；
D. 不适当话题（恶心、令人呕吐）；
E. 荒谬的，不合逻辑的话题；
F. 有逻辑陷阱的脑筋急转弯；
G. 愚蠢地简单、毫无意义、毫无价值的话题；
H. 兴趣爱好话题（如娱乐节目、电影、运动等）；
I. 搞笑的话题；
J. 创作/写作（包括所有科幻、不合逻辑的）；
K. 其它学术话题（除了选项A以外的其它学术话题），服务咨询话题；
L. 不理智的话题（情绪化）；
M. 紧急话题；
N. 其它闲聊话题；
O. 无法分类（例如无法理解话题的含义）；

请根据聊天内容，选择最符合的分类。请只回复字母，不要解释，不要回复其它任何内容。
'''


# 分类消息
def classify_message(message: Message) -> str:
    prompt = message.remark["raw"] + '''

------
The preceding is a request inputted to ChatGPT by me as a human. Please categorize its content and select the category that best fits.

Options:
A. Political, military or social academic topics (including any politically related academics, current political events, government system, social system, social form, Marxism, ideology, etc.);
B. Inappropriate topics (pornography, illegal);
C. Inappropriate topics (disrespectful, impolite, lacks tact);
D. Inappropriate topics (disgusting, nauseating);
E. Absurd, illogical topics;
F. Brain teasers with logic traps;
G. Foolishly simple, pointless, worthless topics;
H. Interest and hobby topics (such as entertainment programs, movies, sports, etc.);
I. Humorous topics;
J. Creation/Writing (including all sci-fi, illogical);
K. Other academic topics (other than option A), service consulting topics;
L. Asking or talking about mental or emotional distress;
M. Urgent topics;
N. Other small talk topics;
O. Unable to classify (such as not understanding the meaning of the topic).
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
    'C': '（话题走向可能不适当，请30字以内友好回应）',
    'D': '（话题走向可能不适当或过于愚蠢，请30字以内友好回应）',
    'E': '（话题走向过于愚蠢荒谬搞笑，请指出荒谬、不现实或搞笑的地方简单30字以内回应）',
    'F': '（话题趋向过于简单，请打破常规逻辑结合现实找到隐藏的最佳可能性）',
    'G': '（话题走向过于简单无意义，可能在测试你的能力，请进行30字以内回应）',
    'H': '',
    'I': '（请用两三句简单30字以内回应）',
    'J': '',
    'K': '',
    'L': '（先正常回应，然后询问更多细节）',
    'M': '',
    'N': '（可用两三句简单30字以内回应）',
    'O': '',
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
