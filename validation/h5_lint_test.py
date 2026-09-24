# -*- coding: utf-8 -*-
"""h5 校验（M4-3/4）：
1) data.json 存在且含 modules/profiles/series/spotlights；
2) 每个 series 点与 spotlight 的 (value, source) 能回溯到源 JSON 字段（重读源场景验证）；
3) 页面 index.html **不含硬编码业务数值**：源码中不得出现序列里的具体金额字面量；
4) 可见文本（lead/句/模块行/免责）复用同一套 lint（禁词/档位/区间/覆盖/源/保障责任+回引）；
5) data-source 属性：表格与关键值由生成器写入（index.html 模板含 data-source 机制）。
运行：python validation/h5_lint_test.py
"""
import sys, os, json, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.render.loader import load_scenario
from src.render.summary import build_summary
from src.render.compliance import output_tier_lint
from src.render.trace import trace
from src.render import banned_scan

DATA = os.path.join(os.path.dirname(ROOT), '保险运营程序设计与实践_作业材料', '利益演示数据')
PRODUCT = '国寿鑫益延年养老年金保险（分红型）'
FN = '国寿鑫益延年养老年金保险（分红型）,男，30，10.json'
H5 = os.path.join(ROOT, 'output', 'h5')
DISCLAIMER = ("本材料仅供教学研究使用，演示利益基于假设、不代表未来实际收益，"
              "红利分配不确定，具体以保险公司正式条款及保险单为准。")

fails = []
d = json.load(open(os.path.join(H5, 'data.json'), encoding='utf-8'))
html = open(os.path.join(H5, 'index.html'), encoding='utf-8').read()

# 1) 结构
for k in ('modules', 'profiles', 'series', 'spotlights', 'ages', 'boundary'):
    if k not in d:
        fails.append(f"data.json 缺字段 {k}")
print(f"[1] 结构: {'√' if not fails else '×'} keys={sorted(d.keys())}")

# 2) 数字回溯：series 点/spotlight 的 (value, source) → 源 JSON 字段@key 值一致
rec, meta = load_scenario(DATA, PRODUCT, FN)
S = build_summary(rec, meta)
def src_value(field, key):
    """按 field@key 从源 record 取值。"""
    f = field.split('.')[0]
    if f in ('IRR', '单利利率'):
        parts = field.split('.')
        return num_of(rec[parts[0]][parts[1]].get(key))
    if f == '红利':
        parts = field.split('.')
        return num_of(rec['红利'][parts[1]][parts[2]].get(key))
    v = rec.get(field, {})
    if isinstance(v, dict):
        return num_of(v.get(str(key)))
    return None
def num_of(s):
    if s is None or s == '-': return None
    return float(str(s).replace(',', '').replace('%', ''))

n_pt = n_ok_pt = 0
for s in d['series']:
    for p in s['points']:
        n_pt += 1
        f, k = p['source'].rsplit('@', 1)
        sv = src_value(f, k)
        if sv is not None and abs(sv - p['v']) < 0.011:
            n_ok_pt += 1
        else:
            fails.append(f"series 点回溯失败: {p} 源值={sv}")
n_sp = n_ok_sp = 0
rec_variants = set()
for rc in S['records']:
    rec_variants |= rc['variants']
    rec_variants |= {v.rstrip('0').rstrip('.') for v in rc['variants'] if '.' in v}
for sp in d['spotlights']:
    n_sp += 1
    if sp['value'] in rec_variants:
        n_ok_sp += 1
    else:
        fails.append(f"spotlight 回溯失败: {sp}")
print(f"[2] 数字回溯: series {n_ok_pt}/{n_pt} | spotlights {n_ok_sp}/{n_sp}")

# 3) 页面无硬编码业务数值：源码不得含序列具体金额（取若干真实金额字面量扫源码）
hard = []
sample_vals = set()
for s in d['series']:
    for p in s['points'][::7]:
        v = int(p['v'])
        if v >= 10000:
            sample_vals.add(f"{v:,}")
            sample_vals.add(str(v))
for v in list(sample_vals)[:40]:
    if re.search(r'(?<![\w.])' + re.escape(v) + r'(?![\w.])', html):
        hard.append(v)
print(f"[3] 硬编码检查: {'√ 源码0硬编码金额' if not hard else '× 发现 ' + str(hard[:6])}")
if hard:
    fails.append(f"index.html 硬编码金额: {hard[:6]}")

# 4) 可见文本 lint（复用同一套）
texts = [d['disclaimer'], d['product']]
for p in d['profiles']:
    texts.append(p['lead']); texts.extend(p['sentences'].values())
for m in d['modules'].values():
    texts.append(m['title']); texts.extend(l['text'] for l in m['lines'])
visible = '\n'.join(texts)
ky = set(range(0, 130))
bh = banned_scan.scan(visible)
tv = output_tier_lint(visible, S['records'], ky)
print(f"[4] 可见文本 lint: 禁词={len(bh)} 断言={len(tv)}")
for x in bh: fails.append(f"禁词 {x}")
for x in tv: fails.append(f"断言 {x}")

# 5) data-source 机制存在
has_ds = html.count('data-source') >= 2 and "setAttribute('data-source'" in html and "data-source=" in html
print(f"[5] data-source 机制: {'√' if has_ds else '×'}")
if not has_ds:
    fails.append("index.html 缺 data-source 机制")

# 6) 真交互机制存在：profile onchange 重排 + year input 高亮
inter = ("renderProfile" in html and "renderMods" in html and "oninput" in html
         and "classList.toggle('hl'" in html)
print(f"[6] 交互机制: {'√ 切画像重排+切年度高亮' if inter else '×'}")
if not inter:
    fails.append("交互机制缺失")

print()
if fails:
    print(f"FAIL {len(fails)}:")
    for f in fails[:12]:
        print("  ×", f)
    sys.exit(1)
print("h5_lint_test: 全部通过")
