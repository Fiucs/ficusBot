import jieba
import jieba.posseg as pseg
import jieba.analyse
import re

# ======================
# 🔥 超全停用词（日常任务/问答专用）
# ======================
stop_words = set([
    # 中文代词
    "我", "你", "您", "他", "她", "它", "我们", "你们", "他们", "咱们", "自己", "别人",
    "大家", "某人", "谁", "什么", "哪", "哪里", "哪儿", "几时", "多少", "怎么", "怎样",

    # 中文助词/介词/连词/副词
    "的", "地", "得", "了", "着", "过", "在", "是", "有", "和", "与", "及", "或", "并",
    "而", "但", "却", "如果", "因为", "所以", "虽然", "即使", "只要", "就", "才",
    "都", "也", "还", "只", "就", "再", "又", "很", "更", "最", "太", "非常", "十分",
    "特别", "大概", "也许", "可能", "似乎", "好像", "几乎", "经常", "总是", "偶尔",

    # 中文动词/语气词/虚词
    "请", "帮", "让", "使", "把", "被", "对", "给", "用", "来", "去", "到", "从", "向",
    "往", "按", "按照", "根据", "关于", "对于", "至于", "为了", "由于", "因此",
    "吗", "呢", "吧", "啊", "哦", "嗯", "哎", "哇", "啦", "呀", "咯", "呗", "呵",

    # 中文数量/指代
    "一", "二", "三", "个", "些", "这", "那", "该", "此", "这些", "那些", "这个", "那个",
    "一下", "一些", "一点", "每次", "如下", "以上", "以下",

    # 英文停用词（全覆盖）
    "i", "me", "my", "mine", "you", "your", "yours", "he", "him", "his", "she", "her",
    "it", "its", "we", "us", "our", "they", "them", "their",
    "is", "are", "was", "were", "am", "be", "been", "being",
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "this", "that", "these", "those", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "not", "no", "yes", "so", "up", "down", "out", "about", "than", "then", "just"
])

def get_keywords(text, topK=8):
    keywordsList = jieba.analyse.extract_tags(text, topK=topK)
    keywordsStr = ",".join(keywordsList)
    
    return keywordsStr  

def fast_semantic_tokenize(text, topK=5):
    # 分词+词性
    words_with_flag = pseg.lcut(text.strip())
    
    # 处理中英文
    token_list = []
    for word, flag in words_with_flag:
        if re.fullmatch(r'[a-zA-Z0-9]+', word):
            token_list.append((word.lower(), 'eng'))
        else:
            token_list.append((word, flag))
    
    # 去停用词 + 过滤短词
    clean_tokens = [
        (w, f) for w, f in token_list
        if w not in stop_words and len(w) > 1
    ]
    
    # 关键词
    keywords = jieba.analyse.extract_tags(text, topK=topK)
    
    # 精简输出
    return {
        "原句": text,
        "分词": [w for w, f in token_list],
        "有效词": [w for w, f in clean_tokens],
        "关键词": keywords
    }



# 大模型的方式 慢
# 句子分割
# 新代码（推荐，无警告，性能更好）
# from wtpsplit import SaT
# def get_sentences(text, lang_code="zh", target_length=45):
#     """
#     对文本进行句子分割。
    
#     Args:
#         text (str): 输入文本
#         lang_code (str): 语言代码，默认中文 "zh"
#         target_length (int): 目标句子长度，默认45字符
    
#     Returns:
#         list: 分割后的句子列表
#     """
#     # 快速加载模型
#     # splitter = SaT("sat-3l-sm")          # 最推荐的平衡模型：3层 small 变体
    
#     splitter = SaT("sat-1l-sm")  # 第一次运行会下载 ~200MB
# # 或者更高精度（慢一点）：SaT("sat-12l-sm")
# # 或者极致速度（精度稍低）：SaT("sat-1l-sm")
#     # 进行句子分割
#     sentences = splitter.split(text)
#     return sentences

# # ------------------- 测试 & 精简打印 -------------------
# if __name__ == "__main__":
#     test_texts = [
#         "帮我用Python写一个数据分析脚本",
#         "今天完成文档整理和数据处理",
#         "怎么实现中英文快速语义分词",
#         "我要做AI助手的任务处理模块",
#         "读取桌面上 test1.txt内容，总结一下告诉我"
#     ]

#     # for text in test_texts:
#     #     res = fast_semantic_tokenize(text)
#     #     print("=" * 60)
#     #     print(f"原句：{res['原句']}")
#     #     print(f"分词：{' / '.join(res['分词'])}")
#     #     print(f"有效词：{' / '.join(res['有效词'])}")
#     #     print(f"关键词：{' '.join(res['关键词'])}")
    
#     # get_keywords(test_texts[0])
    
#     sentences = get_sentences(''' 帮我用Python写一个数据分析脚本,
#         今天完成文档整理和数据处理,
#         怎么实现中英文快速语义分词,
#         我要做AI助手的任务处理模块,
#         读取桌面上 test1.txt内容，总结一下告诉我 ''')
#     print(sentences)
        
        
        
        # 正则表达式
import re
import timeit  # 用于自测速度

def fast_chinese_task_split(text: str, min_len: int = 6) -> list[str]:
    """
    针对任务列表、指令、多行输入的快速分句
    
    拆分规则（优先级从高到低）：
    1. 换行符拆分
    2. 中文逗号（，）和英文逗号（,）拆分
    3. 句末标点拆分：
       - 中文句末：。！？；
       - 英文句末：. ! ? ; （英文句号需后跟空格/行尾，避免拆分文件名）
    
    支持中文和英文文本
    
    适合 RAG chunking、embedding 前处理、AI 任务解析
    
    Args:
        text: 输入文本
        min_len: 最小句子长度，短于此长度的将被过滤
    
    Returns:
        拆分后的句子列表
    """
    result = []
    
    sentence_end_pattern = re.compile(r'([，,。！？!?;；])')
    english_dot_pattern = re.compile(r'\.(?=\s|$)')
    
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    
    for line in lines:
        processed = english_dot_pattern.sub('。', line)
        
        parts = sentence_end_pattern.split(processed)
        
        current_sentence = ""
        for part in parts:
            if part in '，,':
                if current_sentence.strip():
                    result.append(current_sentence.strip())
                current_sentence = ""
            elif part in '。！？!?;；':
                if current_sentence.strip():
                    result.append(current_sentence.strip())
                current_sentence = ""
            else:
                current_sentence += part
        
        if current_sentence.strip():
            result.append(current_sentence.strip())
    
    return [s for s in result if len(s) >= min_len]


# 自测速度示例
if __name__ == "__main__":
    long_text = ("这是一个测试长段落。" * 200) + "他说：“为什么这么快？”继续写下去没有标点也行。"
    long_text1 =''' 帮我用Python写一个数据分析脚本,
         今天完成文档整理和数据处理,
         怎么实现中英文快速语义分词,
         我要做AI助手的任务处理模块,
         读取桌面上 test1.txt内容，总结一下告诉我 '''
    long_text2 ='''今天天气真的好热啊我中午出去买奶茶结果晒得我整个人都蔫了
你呢最近忙什么呀
周末计划还没定呢，要不去爬山？要不宅家打游戏？
或者一起去看新上的那部悬疑片？你们几个怎么想的
我妈今天又给我介绍对象了对方据说是个程序员年薪三十多岁有房有车
但是我一听就头大完全不想相亲怎么办'''
    long_text3 =''' 使用weather 技能查询北京天气 ， 然后打开桌 面上test.txt的内容，将天气信息写入文件'''

    time_start = timeit.default_timer()
    sentences = fast_chinese_task_split(long_text1)
    print(f"long_text1 分句结果: {sentences}")
    time_end = timeit.default_timer()
    print(f"long_text1 分句耗时: {time_end - time_start:.4f} 秒")
    
    time_start = timeit.default_timer()
    sentences = fast_chinese_task_split(long_text2)
    print(f"long_text2 分句结果: {sentences}")
    time_end = timeit.default_timer()
    print(f"long_text2 分句耗时: {time_end - time_start:.4f} 秒")
    
    time_start = timeit.default_timer()
    sentences = fast_chinese_task_split(long_text3)
    print(f"long_text3 分句结果: {sentences}")
    time_end = timeit.default_timer()
    print(f"long_text3 分句耗时: {time_end - time_start:.4f} 秒")
