# -*- coding: utf-8 -*-
"""M3 对比组：同一产品同一场景 × 3 个客户画像 → 3 份模块化报告。
每画像 2 次 LLM：reorder（模块顺序，结构化）+ narrative_modular（lead+模块句）。
顺序必须是 SPEC §9 白名单的合法排列，非法回退默认序；m_disclaimer 恒末位。
运行：python src/m3_compare.py   （cwd=report-generator）
"""
import os, sys, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.render.loader import load_scenario, list_products, list_scenarios
from src.render.reconcile import boundary_years
from src.render.summary import build_summary
from src.render.compliance import sanitize, output_tier_lint
from src.render.trace import trace
from src.render import banned_scan
from src.render.report import MODULE_IDS, validate_order, assemble
from src.llm.client import load_config, MiMo
from src.llm.guard import guard_output

DATA = load_config(os.path.join(ROOT, 'config.yaml'))['data']['benefit_data']
PRODUCT = '国寿鑫益延年养老年金保险（分红型）'
FN = '国寿鑫益延年养老年金保险（分红型）,男，30，10.json'   # 流+断崖+两档 全要素场景
_pf = open(os.path.join(ROOT, 'profiles', 'profiles.jsonl'), encoding='utf-8').read()
_dec = json.JSONDecoder()
PROFILES, _i = [], 0
while _i < len(_pf):
    _sp = _pf.find('{', _i)
    if _sp < 0:
        break
    obj, _i = _dec.raw_decode(_pf, _sp)
    PROFILES.append(obj)
if len(sys.argv) > 1:   # 画像过滤：python src/m3_compare.py p_analyst,p_parents
    keep = set(sys.argv[1].split(','))
    PROFILES = [x for x in PROFILES if x['id'] in keep]
llm = MiMo(load_config(os.path.join(ROOT, 'config.yaml')))

rec, meta = load_scenario(DATA, PRODUCT, FN)
by = boundary_years(rec, meta)
S = build_summary(rec, meta)
ky = set(map(int, rec['现金价值'])) | set(range(0, 120))
DISCLAIMER = ("本材料仅供教学研究使用，演示利益基于假设、不代表未来实际收益，"
              "红利分配不确定，具体以保险公司正式条款及保险单为准。")

def say(*a):
    print(*a)

def parse_json_array(t):
    m = re.search(r'\[.*\]', t, re.S)
    return json.loads(m.group(0)) if m else None

def lint_text(text):
    bh = banned_scan.scan(text)
    tv = output_tier_lint(text, S['records'], ky)
    um, _ = trace(text, S['records'], known_years=ky)
    return bh, tv, um

results = []
for prof in PROFILES:
    say("=" * 70)
    say(f"[画像] {prof['id']} {prof['name']}")
    # ---- 1) reorder：结构化模块顺序 ----
    tmpl_r = open(os.path.join(ROOT, 'prompts', 'reorder_v1.md'), encoding='utf-8').read()
    u_r = tmpl_r.replace('{profile_text}', prof['desc']).replace('{focus}', '、'.join(prof['focus']))
    rr = llm.chat('你只输出 JSON 数组。', u_r, max_tokens=3200, temperature=0.2)
    assert 'error' not in rr, rr
    arr = parse_json_array(rr['content'])
    order, valid = validate_order(arr)
    say(f"    reorder: LLM输出={arr}")
    say(f"    合法排列={'√' if valid else '× 回退默认序'} -> {order}")

    # ---- 2) narrative_modular：lead + 每模块句 ----
    tmpl_n = open(os.path.join(ROOT, 'prompts', 'narrative_modular_v2.md'), encoding='utf-8').read()
    u_n = (tmpl_n.replace('{profile_text}', prof['desc'])
                 .replace('{style}', prof['style'])
                 .replace('{summary_text}', S['text'])
                 .replace('{module_ids}', json.dumps(MODULE_IDS, ensure_ascii=False)))

    def try_parse(t):
        t = re.sub(r'^```(?:json)?|```$', '', t.strip(), flags=re.M).strip()
        m = re.search(r'\{[\s\S]*\}', t)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    nr = llm.chat('你是保险利益演示报告文案撰写者，只输出 JSON。', u_n, max_tokens=4800, temperature=0.4)
    assert 'error' not in rr, nr
    obj = try_parse(nr.get('content') or '') if 'error' not in nr else None
    attempts = 1
    while obj is None and attempts <= 4:
        nr = llm.chat('你是保险利益演示报告文案撰写者，只输出 JSON。',
                      u_n + '\n\n【重试】上一版为空或不是合法 JSON。忽略一切思考过程，直接输出 JSON 对象。',
                      max_tokens=4800, temperature=0.3)
        obj = try_parse(nr.get('content') or '') if isinstance(nr, dict) else None
        attempts += 1
    _dbg = nr.get('content') or str(nr.get('error'))[:300] if isinstance(nr, dict) else str(nr)[:300]
    assert obj and 'lead' in obj, f"narrative_modular JSON 解析失败: {_dbg}"
    lead, sentences = obj.get('lead', ''), obj.get('sentences', {})
    say(f"    narrative: lead={lead[:40]}… 模块句={len(sentences)} 个")

    # ---- 3) 组装 + 全套断言（lead+句 逐条回引/禁词/档位；整稿 coverage/源/区间/免责） ----
    raw = assemble(meta, order, S, rec, by, lead, sentences, DISCLAIMER)
    # lead/句 先过 guard 式回引（把违规句交给 LLM 改写一次）
    probe = "\n".join([lead] + [v for v in sentences.values()])
    bh, tv, um = lint_text(probe)
    if bh or tv or um:
        say(f"    首版违规: 禁词{len(bh)} 档位/区间/覆盖{len(tv)} 回引{len(um)} -> 改写")
        fix = llm.chat('你是合规改写者。',
                       u_n + f"\n\n【合规重写】上一版问题：禁用词={sorted({h['word'] for h in bh})}；"
                             f"断言={[v.get('need', v.get('src', v.get('clause'))) for v in tv]}；"
                             f"无出处数字={[x[0] for x in um]}。逐条改正，只输出 JSON。",
                       max_tokens=4800, temperature=0.1)
        obj2 = try_parse(fix.get('content') or '') if 'error' not in fix else None
        if obj2:
            lead, sentences = obj2.get('lead', lead), obj2.get('sentences', sentences)
        else:
            say(f"    改写返回异常({fix.get('error', 'JSON解析失败')})，保留当前版本继续")
    # 终验循环：整稿违规 → 改写 lead/模块句 → 重组（≤3 轮）
    final = None
    for attempt in range(4):
        final = assemble(meta, order, S, rec, by, lead, sentences, DISCLAIMER)
        bh2, tv2, um2 = lint_text(final)
        if not (bh2 or tv2 or um2):
            break
        if attempt == 3:
            break
        say(f"    终验违规第{attempt + 1}轮: 禁词{len(bh2)} 断言{len(tv2)} 回引{len(um2)} -> 改写")
        # surgical 改写：指出违规句原文+AMBIG 候选字段，只准改被指出的句子
        def _find_sent(tok):
            for ss in re.split(r'[。！？\n]', final):
                if re.search(r'(?<!\d)' + re.escape(tok).replace(',', r'[,，]') + r'(?!\d)', ss):
                    return ss.strip()
            return tok
        reasons = []
        for h in bh2:
            reasons.append(f"禁用词句：『{h['context']}』含禁用词“{h['word']}”——只改这一句")
        for v in tv2:
            reasons.append(f"{v.get('kind')}违规句：『{v.get('clause')}』 {v.get('need', v.get('src', v.get('num', '')))}——只改这一句")
        for raw, desc in um2:
            reasons.append(f"『{_find_sent(raw)}』中的 {raw} 无法确定字段归属，候选：{desc}——"
                           f"若指现金价值就写明“现金价值”，若指身故就写明“身故保险金”，只改这一句")
        fix = llm.chat('你是合规改写者。',
                       u_n + "\n\n【合规重写】**只修改下面指出的句子，lead 与其余句子逐字保留**，只输出 JSON：\n- "
                             + "\n- ".join(reasons[:8]),
                       max_tokens=4800, temperature=0.1)
        obj2 = try_parse(fix.get('content') or '') if 'error' not in fix else None
        if obj2:
            lead, sentences = obj2.get('lead', lead), obj2.get('sentences', sentences)
        else:
            say(f"    改写返回异常({fix.get('error', 'JSON解析失败')})，保留当前版本继续")

    # 整稿断言（终态）
    bh2, tv2, um2 = lint_text(final)
    n_dis = final.count('仅供教学研究使用')
    body = final.replace(DISCLAIMER, '')
    n_left = sum(body.count(p) for p in ['仅供教学研究使用', '演示利益基于假设', '不代表未来实际收益', '红利分配不确定'])
    ok = not bh2 and not tv2 and not um2 and n_dis == 1 and n_left == 0
    say(f"    终验: 回引{len(um2)} 禁词{len(bh2)} 断言{len(tv2)} 免责{n_dis}/{n_left} -> {'通过' if ok else '不通过'}")
    for v in tv2[:4]:
        say("      ×", v)
    for u in um2[:4]:
        say("      ×", u)

    outdir = os.path.join(ROOT, 'output', 'm3', f"cmp_{prof['id']}")
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, 'narrative_final.txt'), 'w', encoding='utf-8').write(final)
    json.dump({'product': PRODUCT, 'fn': FN, 'profile': prof['id'], 'order': order, 'order_valid': valid,
               'lead': lead, 'sentences': sentences},
              open(os.path.join(outdir, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    results.append((prof['id'], order, valid, ok))

say("=" * 70)
say("[三份并排对比]")
for pid, order, valid, ok in results:
    say(f"  {pid}: 序={ '→'.join(m[2:] for m in order) } 合法={'√' if valid else '回退'} 终验={'过' if ok else '未过'}")
allok = all(v and ok for _, _, v, ok in results)
say("M3 对比组:", "3/3 通过" if allok else "存在未过")
sys.exit(0 if allok else 1)
