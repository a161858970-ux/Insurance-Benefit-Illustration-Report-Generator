"""modular_run —— 模块化报告管道（参数化版，M4）。
单场景 × 单画像 → 模块化 narrative_final（reorder 结构化 + narrative_modular + 代码模块块
+ 六道断言终验循环）。从 m3_compare 抽取并参数化；m3_compare 保持已验收形态不动。
"""
import os, sys, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.render.loader import load_scenario
from src.render.reconcile import boundary_years
from src.render.summary import build_summary
from src.render.compliance import sanitize, output_tier_lint
from src.render.trace import trace
from src.render import banned_scan
from src.render.report import MODULE_IDS, validate_order, assemble
from src.llm.client import load_config, MiMo

DATA = load_config(os.path.join(ROOT, 'config.yaml'))['data']['benefit_data']
DISCLAIMER = ("本材料仅供教学研究使用，演示利益基于假设、不代表未来实际收益，"
              "红利分配不确定，具体以保险公司正式条款及保单为准。".replace('保单为准', '保险单为准'))

_llm = None
def get_llm():
    global _llm
    if _llm is None:
        _llm = MiMo(load_config(os.path.join(ROOT, 'config.yaml')))
    return _llm

def parse_json_array(t):
    m = re.search(r'\[.*\]', t, re.S)
    return json.loads(m.group(0)) if m else None

def try_parse_obj(t):
    t = re.sub(r'^```(?:json)?|```$', '', (t or '').strip(), flags=re.M).strip()
    m = re.search(r'\{[\s\S]*\}', t)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def run_modular(product, fn, outdir, prof, log=print):
    """返回 {'ok': bool, 'order': [...], 'violations': [...]}；产物写 outdir/narrative_final.txt+manifest"""
    llm = get_llm()
    rec, meta = load_scenario(DATA, product, fn)
    by = boundary_years(rec, meta)
    S = build_summary(rec, meta)
    ky = set(map(int, rec['现金价值'])) | set(range(0, 120))

    def lint_text(text, require_footer=True):
        bh = banned_scan.scan(text)
        tv = output_tier_lint(text, S['records'], ky, require_footer=require_footer)
        um, _mt = trace(text, S['records'], known_years=ky)
        return bh, tv, um

    # 1) reorder
    tmpl_r = open(os.path.join(ROOT, 'prompts', 'reorder_v1.md'), encoding='utf-8').read()
    u_r = tmpl_r.replace('{profile_text}', prof['desc']).replace('{focus}', '、'.join(prof['focus']))
    rr = llm.chat('你只输出 JSON 数组。', u_r, max_tokens=3200, temperature=0.2)
    assert 'error' not in rr, rr
    order, valid = validate_order(parse_json_array(rr['content']))
    log(f"    reorder: 合法={'√' if valid else '×回退'} {'→'.join(m[2:] for m in order)}")

    # 2) narrative_modular
    tmpl_n = open(os.path.join(ROOT, 'prompts', 'narrative_modular_v2.md'), encoding='utf-8').read()
    u_n = (tmpl_n.replace('{profile_text}', prof['desc']).replace('{style}', prof['style'])
                 .replace('{summary_text}', S['text'])
                 .replace('{module_ids}', json.dumps(MODULE_IDS, ensure_ascii=False)))

    nr = llm.chat('你是保险利益演示报告文案撰写者，只输出 JSON。', u_n, max_tokens=4800, temperature=0.4)
    obj = try_parse_obj(nr.get('content') or '') if isinstance(nr, dict) else None
    attempts = 1
    while obj is None and attempts <= 4:
        nr = llm.chat('你是保险利益演示报告文案撰写者，只输出 JSON。',
                      u_n + '\n\n【重试】上一版为空或不是合法 JSON。直接输出 JSON 对象。',
                      max_tokens=4800, temperature=0.3)
        obj = try_parse_obj(nr.get('content') or '') if isinstance(nr, dict) else None
        attempts += 1
    assert obj and 'lead' in obj, f"narrative JSON 失败: {(nr.get('content') or str(nr.get('error')))[:200]}"
    lead, sentences = obj.get('lead', ''), obj.get('sentences', {})
    log(f"    narrative: lead={lead[:36]}… 句={len(sentences)}")

    # 2.5) 句子级三查（D058）：含从不渲染的 m_disclaimer 句——原实现只查终稿渲染正文，
    # 死角句带违规入库，H5 汇总可见文本时才暴雷。改写 ≤2 轮复检，仍不过则终态 ok=False。
    from src.render.compliance import probe_violations
    for _pr in range(3):
        _probe = "\n".join([lead] + [v for v in sentences.values()])
        _pbh, _ptv, _pum = probe_violations(_probe, S['records'], ky)
        if not (_pbh or _ptv or _pum):
            break
        log(f"    句查第{_pr + 1}轮: 禁词{len(_pbh)} 断言{len(_ptv)} 回引{len(_pum)} → 改写")
        _reasons = ([f"禁用词句：『{h['context']}』含“{h['word']}”——只改这句" for h in _pbh] +
                    [f"{v.get('kind')}违规：『{v.get('clause')}』 {v.get('need', v.get('src', v.get('num', '')))}——只改这一句"
                     for v in _ptv] +
                    [f"数字 {rv} 无出处/AMBIG（{dv}）——写明字段名，只改这一句" for rv, dv in _pum])
        # 单句 surgical 修改 → 关思考（实测 495s vs 6s；D050 的开思考仅针对整稿重写）
        _fix = llm.chat('你是合规改写者。',
                        u_n + "\n\n【合规重写】**只修改下面指出的句子，lead 与其余句子逐字保留**，只输出 JSON：\n- "
                              + "\n- ".join(_reasons[:8]),
                        max_tokens=6000, temperature=0.1, thinking=False)
        _o2 = try_parse_obj(_fix.get('content') or '') if 'error' not in _fix else None
        if _o2:
            lead, sentences = _o2.get('lead', lead), _o2.get('sentences', sentences)
    probe_ok = not (_pbh or _ptv or _pum)

    # 3) 终验循环（六道断言：回引/禁词/档位/区间/覆盖/源+保障责任）
    final = None
    for attempt in range(4):
        final = assemble(meta, order, S, rec, by, lead, sentences, DISCLAIMER)
        bh, tv, um = lint_text(final)
        if not (bh or tv or um):
            break
        if attempt == 3:
            break
        def _sent(tok):
            for ss in re.split(r'[。！？\n]', final):
                if re.search(r'(?<!\d)' + re.escape(tok).replace(',', r'[,，]') + r'(?!\d)', ss):
                    return ss.strip()
            return tok
        reasons = ([f"禁用词句：『{h['context']}』含“{h['word']}”——只改这句" for h in bh] +
                   [f"{v.get('kind')}违规：『{v.get('clause')}』 {v.get('need', v.get('src', v.get('num', '')))}——只改这一句"
                    for v in tv] +
                   [f"『{_sent(raw)}』中的 {raw} 无出处/AMBIG（{desc}）——写明字段名，只改这一句" for raw, desc in um])
        fix = llm.chat('你是合规改写者。',
                       u_n + "\n\n【合规重写】**只修改下面指出的句子，lead 与其余句子逐字保留**，只输出 JSON：\n- "
                             + "\n- ".join(reasons[:8]), max_tokens=6000, temperature=0.1, thinking=True)
        o2 = try_parse_obj(fix.get('content') or '') if 'error' not in fix else None
        if o2:
            lead, sentences = o2.get('lead', lead), o2.get('sentences', sentences)
        log(f"    终验第{attempt + 1}轮: 禁词{len(bh)} 断言{len(tv)} 回引{len(um)} → 改写")

    bh, tv, um = lint_text(final)
    n_dis = final.count('仅供教学研究使用')
    body = final.replace(DISCLAIMER, '')
    n_left = sum(body.count(x) for x in ['仅供教学研究使用', '演示利益基于假设', '不代表未来实际收益', '红利分配不确定'])
    ok = not (bh or tv or um) and n_dis == 1 and n_left == 0 and probe_ok
    log(f"    终验: 回引{len(um)} 禁词{len(bh)} 断言{len(tv)} 免责{n_dis}/{n_left} -> {'通过' if ok else '不通过'}")
    for v in tv[:5]:
        log(f"      × {v}")
    for u in um[:5]:
        log(f"      × trace: {u}")

    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, 'narrative_final.txt'), 'w', encoding='utf-8').write(final)
    json.dump({'product': product, 'fn': fn, 'profile': prof.get('id', 'p_default'),
               'order': order, 'order_valid': valid, 'lead': lead, 'sentences': sentences},
              open(os.path.join(outdir, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return {'ok': ok, 'order': order, 'violations': tv + [{'kind': 'banned'} for _ in bh]}
