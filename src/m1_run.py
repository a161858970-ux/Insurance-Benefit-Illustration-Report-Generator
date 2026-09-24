# -*- coding: utf-8 -*-
"""M1 最窄闭环：鑫益延年(男,0,1)
解析 → 五类边界年勾稽 → 与参考 HTML 逐数字对拍 → SVG 图 → MiMo 合规文案 → 回引校验 + 禁用词扫描
运行：python src/m1_run.py   （cwd = report-generator）
"""
import os, sys, re, json, io, contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.render.loader import load_scenario, list_products, list_scenarios, num, series, dividend
from src.render.reconcile import reconcile, aggregate, boundary_years
from src.render.summary import build_summary
from src.render.charts import svg_line_chart, svg_death_cliff
from src.render import banned_scan
from src.llm.client import load_config, MiMo
from src.llm.guard import guard_output

DATA = load_config(os.path.join(ROOT, 'config.yaml'))['data']['benefit_data']
# 场景可从命令行传入：python src/m1_run.py "<文件名>" [输出目录名]；默认=对拍场景 (男,0,1)
FN = sys.argv[1] if len(sys.argv) > 1 else '国寿鑫益延年养老年金保险（分红型）,男，0，1.json'
# 产品自动发现：在数据目录下搜该文件所属产品（换产品零改码）
PRODUCT = None
for _p in list_products(DATA):
    if FN in list_scenarios(DATA, _p):
        PRODUCT = _p
        break
assert PRODUCT, f'数据目录中找不到场景文件: {FN}'
DO_HTML_CHECK = (PRODUCT == '国寿鑫益延年养老年金保险（分红型）' and FN.endswith('男，0，1.json'))
if len(sys.argv) > 2 and sys.argv[2]:
    OUT = os.path.join(ROOT, 'output', sys.argv[2])
elif DO_HTML_CHECK:
    OUT = os.path.join(ROOT, 'output', 'm1')
else:
    OUT = os.path.join(ROOT, 'output', 'm1_' + FN.replace('.json', '').split('，')[-2] + 'y' + FN.replace('.json', '').split('，')[-1])
os.makedirs(OUT, exist_ok=True)
json.dump({'product': PRODUCT, 'fn': FN},
          open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
report = io.StringIO()

def say(*a):
    print(*a)
    print(*a, file=report)

# ---------- 1. 解析 ----------
rec, meta = load_scenario(DATA, PRODUCT, FN)
say("=" * 72)
say("[1] 解析:", FN)
say("    meta =", meta)

# ---------- 2. 五类边界年 ----------
by = boundary_years(rec, meta)
say("[2] 五类边界年:")
say("    首年 =", by['首年'], "| 缴费期满年 =", by['缴费期满年'], "| 起领年 =", by['起领年'], "| 满期年 =", by['满期年'])
say(f"    给付比例变化年: {len(by['给付比例变化年'])} 个身故金递减点")
for d in by['给付比例变化年'][:6]:
    say(f"      {d['key']}岁: {int(d['from'])} → {int(d['to'])}")
if len(by['给付比例变化年']) > 6:
    say(f"      ...（其余 {len(by['给付比例变化年'])-6} 个已存 JSON）")
json.dump(by, open(os.path.join(OUT, 'boundary_years.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------- 3. 勾稽（单场景 + 全量 84 文件） ----------
r1 = reconcile(rec, meta)
say(f"[3] 单场景勾稽 {FN}:")
for x in 'ABC':
    say(f"    {x}: {r1[x]['pass']}/{r1[x]['cnt']}  fails={len(r1[x]['fails'])} {r1[x]['fails'][:3]}")

all_res, files_n = [], 0
for p in list_products(DATA):
    for fn in list_scenarios(DATA, p):
        rc, mt = load_scenario(DATA, p, fn)
        all_res.append(reconcile(rc, mt)); files_n += 1
tot = aggregate(all_res)
say(f"[3b] 全量勾稽（{files_n} 文件）:")
for x in 'ABC':
    say(f"    {x} = {tot[x]['pass']}/{tot[x]['cnt']}  失败={tot[x]['fails']}")
say("    基线对照: A=6720/6720 B=5760/5760 C=6300/6300(C单档=双档各自) →",
    "一致" if (tot['A']['pass'], tot['A']['cnt'], tot['B']['pass'], tot['B']['cnt']) == (6720, 6720, 5760, 5760)
    and tot['C']['cnt'] == 12600 else "不一致，需解释口径")

if DO_HTML_CHECK:
    # ---------- 4. 与参考 HTML 逐数字对拍 ----------
    html_path = os.path.join(DATA, '鑫益延年客户演示.html')
    html = open(html_path, encoding='utf-8').read()
    html_flat = html.replace(',', '')
    def in_html(v):
        cands = {f"{v:,}", str(v), f"{v:.2f}"}
        return any(c in html or c.replace(',', '') in html_flat for c in cands)

    # (HTML字面, JSON原值, 源字段, 关系)  —— 字面命中与数值关系分列，如实标注舍入
    cv = series(rec, '现金价值'); pens = series(rec, '养老金'); mat = series(rec, '满期金')
    dv_rate, dv_src = dividend(rec, '累积红利', 'rate')
    st_rate, _ = dividend(rec, '生存总利益', 'rate')
    targets = [
        ('10,380', num(rec['现金价值']['5']),  '现金价值@5（第5保单年度末，超保费）', 'exact'),
        ('13,010', num(rec['现金价值']['18']), '现金价值@18', 'exact'),
        ('2,820',  dv_rate.get(18),            f'红利.rate.{dv_src}@18', 'round0'),   # JSON=2819.63，HTML四舍五入到元
        ('26,500', num(rec['现金价值']['59']), '现金价值@59（价值高峰）', 'exact'),
        ('700',    pens.get(60),               '养老金@60（每年领取）', 'exact'),
        ('10,700', mat.get(105),               '满期金@105', 'exact'),
        ('10.16',  num(rec['红利']['rate']['收益倍数']['105']), '红利.rate.收益倍数@105（倍数口径）', 'exact'),
        ('10.16',  round(st_rate.get(105, 0)/10000, 3), '红利.rate.生存总利益@105÷10000（万元展示，HTML舍入）', 'round2'),
        ('2.65',   num(rec['红利']['guaranteed']['收益倍数']['59']), '红利.guaranteed.收益倍数@59', 'exact'),
    ]
    say("[4] 与参考成品 HTML 逐数字对拍（字面命中 / 数值关系 分列）:")
    say(f"    {'HTML字面':>9} | {'命中':^4} | {'JSON取值':>10} | 关系 | 源字段")
    all_ok = True
    for shown, val, src, rel in targets:
        literal = shown in html or shown.replace(',', '') in html_flat
        if val is None:
            rel_ok = False
        elif rel == 'exact':
            rel_ok = abs(float(shown) - val) < 0.005 + 1e-9 if '.' in shown else abs(float(shown.replace(',', '')) - val) < 0.5
        elif rel == 'round0':   # HTML 展示为四舍五入到元
            rel_ok = round(val) == float(shown.replace(',', ''))
        elif rel == 'round2':   # HTML 展示为四舍五入到 2 位小数（万元）
            rel_ok = abs(round(val, 2) - float(shown)) < 0.005
        else:
            rel_ok = False
        all_ok &= (literal and rel_ok)
        j = f"{val:g}" if val is not None else '—'
        rel_txt = {'exact': '逐字', 'round0': 'HTML舍入到元', 'round2': 'HTML舍入到2位小数'}[rel]
        say(f"    {shown:>9} | {'√' if literal else '×':^4} | {j:>10} | {'√' if rel_ok else '×'} {rel_txt} | {src}")
    say("    对拍结论:", "全部一致 √（含 2 处 HTML 舍入展示，JSON 原值逐字核对）" if all_ok else "存在不一致 ×")
    all_ok_check = all_ok


else:
    say('[4] 跳过 HTML 对拍（参考成品仅对应 (男,0,1) 场景）')
    all_ok_check = None
# ---------- 5. 出图 ----------
svg1 = svg_line_chart(rec, meta)
open(os.path.join(OUT, 'chart_benefits.svg'), 'w', encoding='utf-8').write(svg1)
svg2, n_drop = svg_death_cliff(rec, meta)
open(os.path.join(OUT, 'chart_death.svg'), 'w', encoding='utf-8').write(svg2)
say(f"[5] 图已出: chart_benefits.svg / chart_death.svg（身故金递减点 {n_drop} 个，原值未修复）")

# ---------- 6. LLM：摘要 → 提示词 → MiMo → 回引 → 禁用词 ----------
cfg = load_config(os.path.join(ROOT, 'config.yaml'))
if not cfg['llm'].get('model'):
    cfg['llm']['model'] = 'mimo-v2.5-pro'
llm = MiMo(cfg)
say(f"[6] LLM: model={llm.model} base={llm.base}")

S = build_summary(rec, meta)          # 返回 dict: text/records/rows（rows 已过 tier_lint 断言）
records = S['records']
known_years = set(map(int, rec['现金价值'])) | set(range(0, 120))

def trace_all(t):
    from src.render.trace import trace as _t
    return _t(t, records, known_years=known_years)
summary_text = S['text']
say(f"[6] 摘要生成: 数字行 {len(S['rows'])} 条，回引三元组记录 {len(records)} 条，tier_lint=通过")
# 画像按场景 meta 动态生成（D024：硬编码曾导致 30 岁场景配"0 岁宝宝"画像）
has_flow = ('养老金' in rec) or ('年金' in rec)   # 形态自动检测：有领取流 vs 纯增长（增额寿类）
if meta['年龄'] <= 12 and has_flow:
    profile_text = (f"被保险人为 {meta['年龄']} 岁{'男童' if meta['性别']=='男' else '女童'}，投保人是其父母，"
                    "首次接触保险，不懂金融术语；关心这笔钱是否确定、什么时候能用、孩子一生的关键节点有没有现金流。")
elif meta['年龄'] <= 12:
    profile_text = (f"被保险人为 {meta['年龄']} 岁{'男童' if meta['性别']=='男' else '女童'}，投保人是其父母，"
                    "首次接触保险，不懂金融术语；关心这笔钱是否确定、多年后增值到多少、教育等节点能否用上。")
elif has_flow:
    profile_text = (f"被保险人为 {meta['年龄']} 岁{'男士' if meta['性别']=='男' else '女士'}，投保人即本人，"
                    "首次接触保险，不懂金融术语；关心投入是否确定、什么时候能回本、退休后每年有多少现金流。")
else:
    profile_text = (f"被保险人为 {meta['年龄']} 岁{'男士' if meta['性别']=='男' else '女士'}，投保人即本人，"
                    "首次接触保险，不懂金融术语；关心投入是否确定、现金价值如何逐年增长、需要用钱时能拿到多少。")

tmpl = open(os.path.join(ROOT, 'prompts', 'narrative_v5.md'), encoding='utf-8').read()
user_prompt = tmpl.replace('{profile_text}', profile_text).replace('{summary_text}', summary_text)

resp = llm.chat('你是保险利益演示说明文案撰写者，只做表达不做计算。', user_prompt,
                max_tokens=2000, temperature=0.3)
if 'error' in resp:
    say("    LLM 调用失败:", resp['error'])
    sys.exit(1)
say(f"    探活/调用成功: model_returned={resp['model']} sec={resp['sec']} proxy={resp['proxy']} usage={resp['usage']}")

def retry_fn(attempt, unmatched):
    u = ', '.join(x[0] for x in unmatched)
    r2 = llm.chat('你是保险利益演示说明文案撰写者，只做表达不做计算。',
                  user_prompt + f"\n\n【重试】你上一版中这些数字在摘要里找不到出处：{u}。"
                               f"请只用【数据摘要】里出现过的数字重写全文；【硬性约束】每一条仍然全部生效，一条都不许违反。",
                  max_tokens=2000, temperature=0.1)
    return r2.get('content', '')

g = guard_output(resp['content'], records, known_years, max_retry=2, retry_fn=retry_fn)
say(f"[6b] 数字回引校验: ok={g['ok']} retried={g['retried']} degraded={g['degraded']} "
    f"matched={len(g['matched'])} unmatched={len(g['unmatched'])}")
for m in g['matched'][:10]:
    say("      √", m)
for m in g['unmatched']:
    say("      ×", m)

# ---------- 7. 合规循环：禁用词 + 输出层档位断言（任一违规→改写≤2→复检） ----------
from src.render.compliance import sanitize, output_tier_lint
text = sanitize(g['text'])

def violations_report(bh, tv):
    rs = []
    if bh:
        rs.append("禁用词：" + '、'.join(sorted({h['word'] for h in bh})))
    for v in tv:
        k = v.get('kind', 'tier')
        if k == 'tier':
            rs.append(f"档位违规：句子『{v['clause']}』中的 {v['num']} 是保证档（{v['src']}），不得放在演示语境")
        elif k == 'range':
            rs.append(f"区间缺失：句子『{v['clause']}』中的合计 {v['num']} {v['need']}")
        elif k == 'coverage':
            rs.append(f"给付流覆盖不全：{v['clause']} {v['need']}——该产品全部给付流（含每条的起止年龄、年度数、合计）都必须在文中出现")
        elif k == 'source':
            rs.append("内部源标注泄漏：删掉一切“（源：…”括注，溯源信息不进客户文本")
    return rs

attempts = 0
bh = banned_scan.scan(text)
tv = output_tier_lint(text, records, known_years)
while (bh or tv) and attempts < 3:
    attempts += 1
    reasons = violations_report(bh, tv)
    um_pre, _ = trace_all(text)
    if um_pre:
        reasons.append("无出处数字：" + ', '.join(u[0] for u in um_pre))
    r2 = llm.chat('你是保险利益演示文案的合规改写者。',
                  user_prompt + "\n\n【合规重写】你上一版存在以下问题，逐条改正，其余内容与全部数字保持不变，"
                               "【硬性约束】每一条仍然全部生效：\n- " + "\n- ".join(reasons),
                  max_tokens=2000, temperature=0.1)
    cand = sanitize(r2.get('content') or '')
    if cand.strip():
        text = cand
    bh = banned_scan.scan(text)
    tv = output_tier_lint(text, records, known_years)

say(f"[7] 禁用词扫描（11 词表）: 合规改写 {attempts} 轮 → 最终命中 {len(bh)} 处")
for h in bh:
    say("      ×", h)
say(f"[7c] 输出层档位断言: 最终违规 {len(tv)} 处（演示语境句内的保证档数字）")
for v in tv:
    say("      ×", v)

# ---- ④ 免责去重：正文里的免责/风险句一律剥掉，由代码统一附加一次（SPEC §10） ----
import re as _re
DISCLAIMER = ("本材料仅供教学研究使用，演示利益基于假设、不代表未来实际收益，"
              "红利分配不确定，具体以保险公司正式条款及保险单为准。")
DISC_PATS = ['仅供教学研究使用', '演示利益基于假设', '不代表未来实际收益', '红利分配不确定', '红利分配是不确定']
def strip_disclaimer(t):
    parts = _re.split(r'(?<=[。！？\n])', t)
    return '\n'.join(x.strip() for x in parts
                     if x.strip() and not any(p in x for p in DISC_PATS)).strip()
body = strip_disclaimer(text)
body_hits = sum(body.count(p) for p in DISC_PATS)
final_text = body + '\n\n' + DISCLAIMER
n_dis = final_text.count('仅供教学研究使用')
say(f"[7b] 免责去重: 正文残留免责短语 {body_hits} 次（须=0）、'仅供教学研究使用' {n_dis} 次（须=1）")
assert body_hits == 0 and n_dis == 1, f"免责重复未消除: body_hits={body_hits} n_dis={n_dis}"

# ---------- 落盘 ----------
open(os.path.join(OUT, 'narrative_raw.txt'), 'w', encoding='utf-8').write(resp['content'])
open(os.path.join(OUT, 'narrative_guarded.txt'), 'w', encoding='utf-8').write(g['text'])
open(os.path.join(OUT, 'narrative_final.txt'), 'w', encoding='utf-8').write(final_text)
# 终稿再做一次回引复核（合规改写不得引入新数字）
g_final = (lambda t: __import__('src.render.trace', fromlist=['trace']).trace(t, records, known_years=known_years))(final_text)
say(f"[9] 终稿回引复核: unmatched={len(g_final[0])} matched={len(g_final[1])}")
for u in g_final[0]:
    say("      ×", u)
open(os.path.join(OUT, 'summary_for_llm.txt'), 'w', encoding='utf-8').write(summary_text)
open(os.path.join(OUT, 'prompt_filled.txt'), 'w', encoding='utf-8').write(user_prompt)
open(os.path.join(OUT, 'reconcile_report.txt'), 'w', encoding='utf-8').write(report.getvalue())
say(f"[10] 产物已落盘 {os.path.relpath(OUT, ROOT)}: chart_benefits.svg chart_death.svg narrative_final.txt "
    "summary_for_llm.txt prompt_filled.txt boundary_years.json reconcile_report.txt")
