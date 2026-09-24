"""banned_scan —— 禁用词表扫描（SPEC §7），对任意产出文本执行，0 命中才通过。"""
import re

BANNED = ["收益率", "理财", "存款", "保本", "稳赚", "保底收益", "稳健增值", "无风险", "推荐", "建议购买", "适合您"]
# 需要上下文判断的白名单场景：课程说明/本仓库文档中作为"规则引用"出现时不扫（只扫对外产出）

def scan(text):
    """返回 [{word, context}]；空列表=通过。"""
    hits = []
    for w in BANNED:
        for m in re.finditer(re.escape(w), text):
            s, e = max(0, m.start()-25), min(len(text), m.end()+25)
            hits.append({'word': w, 'context': text[s:e].replace('\n', ' ')})
    return hits

def scan_file(path, encoding='utf-8'):
    with open(path, encoding=encoding) as f:
        return scan(f.read())
