"""compliance —— 输出层合规三件套：文本清洗 / 禁用词(转调 banned_scan) / 输出层档位断言。
输出层档位断言（SPEC §2.5 延伸到 LLM 输出）：
  子句（按 ；;。！？\n 切分）含"演示"且剥除"不保证"类短语后不含"保证" →
  该子句内每个回引数字必须是 [demo] 档或时点豁免；出现 [guar] 即违规。
"""
import re
from .trace import trace, NUM_RE, strip_footer
from . import banned_scan  # noqa

_W_ONLY = re.compile(r'^[\W_]+$', re.UNICODE)

def footer_block(product, fn):
    """数据来源+获取时点页脚两行（SPEC §10；作业合规清单第 2 条）。
    由组装层拼接（与免责块同逻辑），不走 LLM；product/fn 为标识信息（D053）。"""
    return (f"数据来源：课程作业材料《利益演示数据/》给定 JSON（{product}，{fn}）\n"
            f"获取时点：材料发布时点")

def sanitize(text):
    """去 Markdown 星号、剥纯标点残行、行首尾空白、折叠空行。"""
    text = text.replace('**', '')
    text = re.sub(r'(?<=\d)-(?=\d)', '\u2013', text)   # 数字区间连字符归一
    # 剥内部源标注（源：…）——溯源留验证层，不进客户文本（M3-③）；（区间 …）不含"源："不受影响
    text = re.sub(r'[（(][^（()）]*源：[^）()]*[)）]', '', text)
    lines = []
    for l in text.splitlines():
        s = l.strip()
        if not s:
            continue
        if _W_ONLY.match(s):
            continue
        lines.append(s)
    return '\n'.join(lines)

def range_binding_lint(text, records):
    """B 条：合计/求和类数字（is_range 记录）出现的句子里，区间标签（起止或年度数）必须同句出现。
    返回 [{'kind':'range','clause','num','need'}]。"""
    violations = []
    norm = re.sub(r'(?<=\d)-(?=\d)', '\u2013', text)
    sentences = re.split(r'[。！？\n]', norm)
    for r in records:
        if not r.get('is_range'):
            continue
        st = r.get('range_struct')
        if not st:
            # 兼容：无结构化区间的 is_range 记录，从 tokens 集回退构造（min/max/中值）
            rt0 = sorted(int(x) for x in (r.get('range_tokens') or set()))
            if not rt0:
                continue
            st = {'start': str(rt0[0]), 'end': str(rt0[-1]),
                  'n': str(rt0[1]) if len(rt0) == 3 else None}
        if st.get('start') == st.get('end'):
            continue   # 单点流（如满期金）无区间歧义，coverage 已管其呈现；区间绑定只管求和流
        rt_disp = '、'.join(x for x in (st.get('start'), st.get('end'), st.get('n')) if x)
        prefix = f"{r['field']}@{r['key']}"
        for sent in sentences:
            if not sent.strip():
                continue
            # 归属消歧：只有被 trace 判定归属本记录的数字才触发同句检查（防同值误伤）
            _, mt = trace(sent, records)
            owned = [(raw, d) for raw, d in mt
                     if d.startswith(prefix) and raw.replace(',', '').replace('，', '') in r['variants']]
            if not owned:
                continue
            toks = {mm.group(0).replace(',', '') for mm in NUM_RE.finditer(sent)}
            toks |= {t.rstrip('0').rstrip('.') for t in list(toks) if '.' in t}
            start, end, n = st.get('start'), st.get('end'), st.get('n')
            has_bound = (start in toks and end in toks) or \
                        (n and n in toks and (start in toks or end in toks)) or \
                        (n is None and start in toks)   # 单点流：key 同现即界
            if not has_bound:
                violations.append({'kind': 'range', 'clause': sent.strip(),
                                   'num': owned[0][0],
                                   'need': f'合计数字须同句带区间标签（要素: {rt_disp}）'})
    return violations


def coverage_lint(text, records):
    """M3-①②：给付流覆盖——每条 is_flow 的起止key/年数与合计必须出现在全文。"""
    violations = []
    norm = re.sub(r'(?<=\d)-(?=\d)', '\u2013', text)
    toks = set()
    for m in NUM_RE.finditer(norm):
        c = m.group(0).replace(',', '').replace('，', '')
        toks.add(c)
        if '.' in c:
            toks.add(c.rstrip('0').rstrip('.'))
    for r in records:
        if not r.get('is_flow'):
            continue
        rt = r.get('range_tokens') or set()
        miss_toks = sorted(t for t in rt if t not in toks)
        hit_sum = any(v in toks for v in r['variants'])   # 合计值存在即认（同值碰撞可接受）
        if miss_toks or not hit_sum:
            need = []
            if miss_toks:
                need.append(f"缺 起止/年数={miss_toks}")
            if not hit_sum:
                need.append("缺合计值")
            violations.append({'kind': 'coverage', 'clause': f"给付流 {r['field']}@{r['key']}",
                               'num': '、'.join(sorted(rt)),
                               'need': '；'.join(need) + "（须出现在终稿全文）"})
    return violations


def source_lint(text, require_footer=False):
    """M3-③ + M5：双向断言（D053）。
    ① 泄漏：剥除页脚行后的正文不得含内部源标注（先剥再查——页脚"数据来源："含裸"源："子串，
      不剥会把合法页脚误杀；先剥也不掩盖正文真泄漏）。
    ② 存在性（require_footer=True，仅终稿级调用）：页脚"数据来源"与"获取时点"两行必须都在。
    """
    v = []
    if '源：' in strip_footer(text):
        v.append({'kind': 'source', 'clause': '终稿含内部源标注', 'num': '源：', 'need': '剥除全部（源：…）括注'})
    if require_footer:
        if '数据来源：' not in text:
            v.append({'kind': 'source', 'clause': '终稿缺数据来源', 'num': '数据来源：',
                      'need': '页脚须含「数据来源」行（SPEC §10，由代码拼接）'})
        if '获取时点：' not in text:
            v.append({'kind': 'source', 'clause': '终稿缺获取时点', 'num': '获取时点：',
                      'need': '页脚须含「获取时点」行（SPEC §10，由代码拼接）'})
    return v


def responsibility_lint(text, records):
    """M4-①：字段存在（有 is_resp 记录）则其值必须出现在终稿——身故/全残代码断言。"""
    violations = []
    norm = re.sub(r'(?<=\d)-(?=\d)', '\u2013', text)
    toks = set()
    for m in NUM_RE.finditer(norm):
        c = m.group(0).replace(',', '').replace('，', '')
        toks.add(c)
        if '.' in c:
            toks.add(c.rstrip('0').rstrip('.'))
    for r in records:
        if not r.get('is_resp'):
            continue
        if not any(v in toks for v in r['variants']):
            violations.append({'kind': 'responsibility', 'clause': f"保障责任 {r['field']}@{r['key']}",
                               'num': '、'.join(sorted(r['variants'])[:3]),
                               'need': f"{r['field']}@{r['key']} 的值须出现在终稿（字段存在即必须呈现）"})
    return violations


def output_tier_lint(text, records, known_years, require_footer=False):
    """返回违规列表 [{'clause','num','src'}]；空=通过。
    窗口规则（D028）：子句剥除"不保证"类短语后含"演示" →
    取"演示"首次出现到子句内随后首次出现"保证"字样之间的窗口（无"保证"则到子句末），
    窗口内每个回引数字必须 [demo] 或时点豁免；出现 [guar] 即违规。
    这样"根据演示，…31,500元（保证）"这类混排句也会被拦，而
    "保证档IRR为1.65%；演示档IRR为2.51%"按；切分后各子句单一档位不受误伤。
    页脚（数据来源/获取时点）为代码拼接的标识文本：窗口/区间/覆盖/责任检查均在剥页脚后的
    正文上跑（页脚"利益演示数据"含"演示"、文件名含投保年龄，会误触窗口且改写修不掉）；
    页脚存在性由 source_lint(require_footer) 单独断言（D053）。
    """
    body = strip_footer(text)
    violations = []
    for clause in re.split(r'[；;。\n!?！？]', body):
        if '演示' not in clause:
            continue
        c2 = clause.replace('演示、不保证', '').replace('不保证', '')
        i_demo = c2.find('演示')
        if i_demo < 0:
            continue
        i_guar = c2.find('保证', i_demo)
        window = c2[i_demo:] if i_guar < 0 else c2[i_demo:i_guar]
        if not re.search(r'\d', window):
            continue
        # 窗口内的数字按原句坐标截取做回引（窗口是子串，直接对 window 跑 trace）
        um, mt = trace(window, records, known_years=known_years)
        for raw, desc in mt:
            if desc.endswith('[guar]'):
                violations.append({'kind': 'tier', 'clause': clause.strip(), 'num': raw, 'src': desc})
    violations.extend(range_binding_lint(body, records))
    violations.extend(coverage_lint(body, records))
    violations.extend(source_lint(text, require_footer=require_footer))
    violations.extend(responsibility_lint(body, records))
    return violations


def probe_violations(text, records, known_years):
    """句子级三查（D058）：禁词 + 档位窗口/区间/源泄漏 + 回引，剔除文档级断言
    （coverage/responsibility 要求"全稿齐现"，对 lead/单句片段必然误报，归终稿 lint 管）。
    用途：LLM 产出的每条句子（含 module_block 恒不渲染的 m_disclaimer 句）在入库前必查——
    否则从不渲染的句子成为 lint 死角，H5 汇总可见文本时才暴雷。"""
    bh = banned_scan.scan(text)
    tv = [v for v in output_tier_lint(text, records, known_years)
          if v.get('kind') not in ('coverage', 'responsibility')]
    um, _mt = trace(text, records, known_years=known_years)
    return bh, tv, um
