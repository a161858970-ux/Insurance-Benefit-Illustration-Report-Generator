"""report —— 模块化报告组装（渲染层，纯代码）。
模块数据块从 summary rows/boundary_years 机械组装，数字天然可回引；
LLM 只贡献 lead 与每模块一句画像化解读（过 guard/断言后嵌入）。
"""
import re
from .compliance import sanitize

MODULE_IDS = ['m_basics', 'm_cashflow', 'm_guarantee', 'm_dividend',
              'm_irr', 'm_death', 'm_claims', 'm_disclaimer']   # SPEC §9 白名单（默认序）
MODULE_TITLES = {
    'm_basics': '一、投保方案',
    'm_cashflow': '二、给付现金流',
    'm_guarantee': '三、保证利益',
    'm_dividend': '四、演示利益（含红利，演示、不保证）',
    'm_irr': '五、收益口径',
    'm_death': '六、身故保障',
    'm_claims': '七、给付边界年',
    'm_disclaimer': '八、数据来源与免责',
}

def validate_order(arr):
    """reorder 输出 → 合法排列校验；非法回退默认序。m_disclaimer 强制末位。"""
    try:
        if (isinstance(arr, list) and len(arr) == len(MODULE_IDS)
                and set(arr) == set(MODULE_IDS)):
            body = [m for m in arr if m != 'm_disclaimer']
            return body + ['m_disclaimer'], True
    except Exception:
        pass
    return list(MODULE_IDS), False

def _rows_for(fields_prefix, rows):
    out = []
    for r in rows:
        f0 = r['field'].split('@')[0].split('.')[0]
        if any(f0 == p or r['field'].startswith(p) for p in fields_prefix):
            out.append(r)
    return out

def module_block(mid, S, meta, rec, by, sentences):
    """返回该模块文本（无内容的模块返回 None → 整块跳过）。"""
    rows, sentences = S['rows'], sentences or {}
    parts = []
    s_llm = sentences.get(mid)
    if s_llm:
        parts.append(s_llm)
    if mid == 'm_basics':
        picked = _rows_for(['年龄', '交费期间', '保费', '累交保费', '领取年龄'], rows)
        picked += _rows_for(['现金价值'], rows)[:1]   # 首年末现金价值一行
        parts += [r['text'] for r in picked[:5]]
    elif mid == 'm_cashflow':
        flows = [r for r in rows if any(k in r['field'] for k in ('年金', '养老金', '特别生存金', '满期金'))]
        cum = _rows_for(['累计领取'], rows)
        parts += [r['text'] for r in flows + cum]
    elif mid == 'm_guarantee':
        picked = [r for r in rows if 'guaranteed' in r['field'] or
                  ('现金价值' in r['field'] and '峰值' in r['text']) or
                  '回本' in r['text'] or '持平' in r['text']]
        picked += [r for r in rows if '生存总利益' in r['text'] and '（保证）' in r['text']]
        seen, uniq = set(), []
        for r in picked:
            if r['text'] not in seen:
                seen.add(r['text']); uniq.append(r)
        parts += [r['text'] for r in uniq]
    elif mid == 'm_dividend':
        picked = [r for r in rows if 'rate' in r['field'] or ('演示' in r['text'] and '生存总利益' in r['text'])]
        parts += [r['text'] for r in picked]
    elif mid == 'm_irr':
        picked = _rows_for(['IRR', '单利利率'], rows) + [r for r in rows if '收益倍数' in r['text']]
        parts += [r['text'] for r in picked]
    elif mid == 'm_death':
        # 断崖年+关键年给值（不给逐年合计）：全部取自 summary rows（进 records 可回引+is_resp 断言）
        picked = [r for r in rows if r['field'] in ('身故保险金', '全残保险金')]
        parts += [r['text'] for r in picked]
    elif mid == 'm_claims':
        drops = by['给付比例变化年']
        parts.append(f"- 首年：{by['首年']} 岁 | 缴费期满年：{by['缴费期满年']} 岁 | 起领年：{by['起领年']} 岁 | 满期年：{by['满期年']} 岁")
        parts.append(f"- 给付比例变化年：共 {len(drops)} 个（首个 {drops[0]['key']} 岁：身故保险金 {int(drops[0]['from']):,}→{int(drops[0]['to']):,} 元）" if drops else "- 给付比例变化年：无")
    elif mid == 'm_disclaimer':
        return None   # 免责块由组装方统一附加
    if not parts:
        return None
    return MODULE_TITLES[mid] + "\n" + "\n".join(parts)

def assemble(meta, order, S, rec, by, lead, sentences, disclaimer):
    """按序组装终稿文本（未 sanitize）。"""
    segs = [f"利益演示报告 · {meta['产品']}",
            f"被保险人：{meta['性别']}，投保 {meta['年龄']} 岁，交费期间 {meta['交费期间']} 年（key=保单年度末年龄）"]
    if lead:
        segs.append(lead)
    for mid in order:
        blk = module_block(mid, S, meta, rec, by, sentences)
        if blk:
            segs.append(blk)
    segs.append(disclaimer)
    return sanitize("\n\n".join(segs))
