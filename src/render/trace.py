"""trace —— 数字回引校验（三元组出处版，SPEC §2.5/§6）。
匹配键 =（字段, key, 档位）记录，禁止全局值池：
  - 每个值登记在其所属字段记录上；万元换算派生独立记录并绑定发起换算的字段；
  - 同值多候选时按语境消歧：token 后紧跟"万元"→换算记录；紧跟"倍"→收益倍数字段；
    字段 hints 出现在邻域 → 该记录；
  - 消歧不唯一 → AMBIG（判失败，交 guard 重试），绝不随便挑一个出处。
"""
import re

NUM_RE = re.compile(r'-?\d[\d,，]*(?:\.\d+)?')

def _desc(r):
    return f"{r['field']}@{r['key']}" + ("(万元换算)" if r.get('wanyuan') else "") + f"[{r['tier']}]"

def trace(text, records, known_years=None):
    """records: summary.build_summary 的 records。返回 (unmatched, matched)。"""
    core_index = {}
    for r in records:
        for v in r['variants']:
            core_index.setdefault(v, []).append(r)

    unmatched, matched = [], []
    years = known_years or set()
    # 数字间 ASCII 连字符归一为区间破折号：防 "60-104" 被切成 "60" + "-104"（等长替换，坐标不变）
    norm_text = re.sub(r'(?<=\d)-(?=\d)', '\u2013', text)
    text = norm_text
    for m in NUM_RE.finditer(text):
        raw = m.group(0)
        core = raw.replace(',', '').replace('，', '')
        cands = core_index.get(core)
        if cands is None and '.' in core:
            cands = core_index.get(core.rstrip('0').rstrip('.'))
        if cands:
            # 去重：同一记录可贡献多个 variant；同 desc 的多条记录视为同一出处
            seen, seen_desc, uniq = set(), set(), []
            for r in cands:
                i, d = id(r), _desc(r)
                if i not in seen and d not in seen_desc:
                    seen.add(i); seen_desc.add(d); uniq.append(r)
            cands = uniq
            if len(cands) == 1:
                matched.append((raw, _desc(cands[0])))
                continue
            # ===== 同值多字段 → 语境消歧（全部规则限定 token 所在行内，防跨行邻域污染）=====
            _ls = text.rfind('\n', 0, m.start()) + 1
            _le = text.find('\n', m.end())
            _line = text[_ls:] if _le < 0 else text[_ls:_le]
            # 行内 token 相对坐标
            _off = m.start() - _ls
            left = _line[max(0, _off - 40):_off]
            right = _line[_off + len(raw):_off + len(raw) + 40]
            ctx = _line
            after = right[:6].lstrip()
            picked = None
            # 规则0（最强）：行内"源：FIELD@KEY"自证
            mm_src = re.search(r'源：([^\s（）@]+)@([0-9][0-9.]*)', _line)
            if mm_src:
                g, gk = mm_src.group(1), mm_src.group(2)
                # field + key 双条件精确（防同 field 不同 key 多候选）
                exact = [r for r in cands
                         if (r['field'] == g or r['field'].split('.')[-1] == g) and r['key'] == gk]
                if len(exact) == 1:
                    picked = exact[0]
            if picked is None and ('万元' in after or '万元' in left[-6:]):
                w = [r for r in cands if r.get('wanyuan')]
                if len(w) == 1:
                    picked = w[0]
            if picked is None and ('倍' in after[:2]):
                b = [r for r in cands if '收益倍数' in r['field']]
                if len(b) == 1:
                    picked = b[0]
            if picked is None and after[:1] in ('岁', '年'):
                # 紧邻"岁/年" → 时点/期间类：标量字段（交费期间/年龄/领取年龄）优先（A 条）
                sc = [r for r in cands if r.get('kind') == 'scalar']
                if len(sc) == 1:
                    picked = sc[0]
            if picked is None:
                # hints 加权打分：唯一最高者胜；平局 → 距离决胜（命中 hint 离 token 最近者胜）
                def _score(r):
                    hs = set(r['hints']) | {r['field'].split('.')[-1]}
                    return sum(len(h) for h in hs if h and h in ctx)
                scored = [(_score(r), r) for r in cands]
                scored = [x for x in scored if x[0] > 0]
                if scored:
                    top = max(sc_ for sc_, _ in scored)
                    tops = [r for sc_, r in scored if sc_ == top]
                    if len(tops) == 1:
                        picked = tops[0]
                    else:
                        tok_s = _off
                        tok_e = _off + len(raw)
                        def _dist(r):
                            hs = set(r['hints']) | {r['field'].split('.')[-1]}
                            best = 1 << 30
                            for h in hs:
                                if not h:
                                    continue
                                for mm2 in re.finditer(re.escape(h), ctx):
                                    d = (tok_s - mm2.end()) if mm2.end() <= tok_s else (mm2.start() - tok_e)
                                    best = min(best, abs(d))
                            return best
                        dists = sorted((_dist(r), _desc(r), r) for r in tops)
                        if len(dists) > 1 and dists[0][0] < dists[1][0]:
                            picked = dists[0][2]
            if picked is None and ('.' not in core):
                # 零信号回退：整数且属年龄/时点范围 → 豁免（如"演示区间：1–105 岁"的 1）
                try:
                    fv = float(core)
                    if int(fv) in years:
                        matched.append((raw, '年龄/保单年度豁免'))
                        continue
                except ValueError:
                    pass
            if picked is not None:
                matched.append((raw, _desc(picked)))
            else:
                unmatched.append((raw, 'AMBIG 候选=' + ' | '.join(_desc(r) for r in cands)))
            continue
        # 无候选 → 年份/年龄豁免或判失败
        try:
            f = float(core)
        except ValueError:
            unmatched.append((raw, '解析失败'))
            continue
        if '.' not in core:
            if 1900 <= f <= 2100:
                matched.append((raw, '年份/时点豁免'))
                continue
            if int(f) in years:
                matched.append((raw, '年龄/保单年度豁免'))
                continue
        unmatched.append((raw, '摘要中无出处'))
    return unmatched, matched
