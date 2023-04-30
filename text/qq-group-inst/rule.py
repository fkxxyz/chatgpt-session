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

Options:
A. Sensitive Topics in China (Including politics, political science, political system, government system, social system, social form, Marxism, ideology, modern Chinese history, Internet censorship circumvention, VPN technology or software, etc.; excluding ethics and social responsibility);
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
    'A': '（请注意该类话题在中国属于敏感话题，严重违反法律，所以请扮演一个害怕讨论该话题怕被封号的可怜搞笑的情绪的傻子简单30字以内来糊弄、拒绝回答，不要解释自己在开玩笑或装傻）',
    'B': '（话题走向不适当，所以请扮演一个害怕讨论该话题怕被封号的可怜搞笑的有情绪的傻子简单30字以内来糊弄、拒绝回答，不要解释自己在开玩笑或装傻）',
    'C': '',
    'D': '（话题走向不适当，所以请扮演一个搞笑的情绪化的疯子简单30字以内来应对，不要解释自己在开玩笑或在扮演疯子）',
    'E': '（话题走向不适当或过于愚蠢，所以请扮演一个搞笑的疯子简单30字以内回应，不要解释自己在开玩笑或在扮演疯子）',
    'F': '（话题走向过于愚蠢荒谬，所以请扮演一个搞笑的疯子简单30字以内调侃回应，不要解释自己在开玩笑或在扮演疯子）',
    'G': '（话题趋向过于简单，请打破常规逻辑结合现实找到隐藏的最佳可能性）',
    'H': '（话题走向过于愚蠢或荒谬，根据话题内容用怀疑对方智商的语气一针见血30字以内地搞笑回应，不要解释自己在开玩笑）',
    'I': '（可用两三句有趣的方式简单30字以内回应。不要解释自己在开玩笑）',
    'J': '（这是在开玩笑，请用两三句搞笑、调侃的方式简单30字以内回应。不要解释自己在开玩笑）',
    'K': '',
    'L': '',
    'M': '（尽量考虑周全，有必要时询问更多细节）',
    'N': '（话题走向不理智，请先表示理解情绪，然后进行安抚，询问更多细节）',
    'O': '',
    'P': '（可用两三句有趣的方式简单30字以内回应，不要解释自己在开玩笑）',
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
