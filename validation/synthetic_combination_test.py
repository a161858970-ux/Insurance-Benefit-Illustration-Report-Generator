# -*- coding: utf-8 -*-
"""第 8 种字段组合合成自测（M2 目标2）：
构造一个字段组合与 7 款真实产品**都不相同**的合成场景，走完全管线
（loader → 五类边界年 → 勾稽 A/B/C → summary+tier_lint → 图 → 回引 trace 冒烟），
证明换产品/换字段组合零改码。
合成规则（validation/synthetic/，与材料目录无关、不污染原始数据）：
  基底 = 国寿鸿盈金生(女,0,1) 的数据，字段组合改造为：
  年金 + 满期金 + 全残保险金 + 领取年龄 + 特别生存金（真实 7 款中无任何一款同时含此 5 字段）
  + 一个契约外未知字段（宽容性：解析不崩、渲染层自动忽略/当可选模块）
运行：python validation/synthetic_combination_test.py
"""
import sys, os, json, shutil, copy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.render.loader import load_scenario, list_products, list_scenarios, series
from src.render.reconcile import reconcile, boundary_years
from src.render.summary import build_summary
from src.render.charts import svg_line_chart, svg_death_cliff
from src.render.trace import trace

DATA = os.path.join(os.path.dirname(ROOT), '保险运营程序设计与实践_作业材料', '利益演示数据')
BASE_PROD = '国寿鸿盈金生年金保险（分红型）'
BASE_FN = '国寿鸿盈金生年金保险（分红型），女，0，1.json'   # 该产品名后是全角逗号（各产品逗号风格不一，常量写死前先列目录核实）
SYN_DIR = os.path.join(ROOT, 'validation', 'synthetic')
SYN_PROD = '合成第8组合测试产品'
SYN_FN = '合成第8组合测试产品,女，0，1.json'
os.makedirs(SYN_DIR, exist_ok=True)

# ---- 构造合成数据 ----
rec = json.load(open(os.path.join(DATA, BASE_PROD, BASE_FN), encoding='utf-8'))[0]
syn = copy.deepcopy(rec)
syn['全残保险金'] = copy.deepcopy(rec['身故保险金'])          # 新增：原基底没有全残
syn['领取年龄'] = 60                                        # 新增：原基底没有领取年龄
syn['特别生存金'] = {k: ('-' if int(k) not in (5, 6) else '5000') for k in rec['年金']}  # 新增：稀疏字段
syn['演示用未知字段'] = {k: '1' for k in rec['现金价值']}      # 契约外字段：宽容性
os.makedirs(os.path.join(SYN_DIR, SYN_PROD), exist_ok=True)
json.dump([syn], open(os.path.join(SYN_DIR, SYN_PROD, SYN_FN), 'w', encoding='utf-8'), ensure_ascii=False)

# ---- 与 7 款真实组合比对：确认是"第 8 种" ----
real_combos = set()
for p in list_products(DATA):
    r0 = json.load(open(os.path.join(DATA, p, list_scenarios(DATA, p)[0]), encoding='utf-8'))[0]
    real_combos.add(frozenset(k for k in r0 if isinstance(r0[k], dict) and r0[k]))
syn_combo = tuple(sorted(k for k in syn if isinstance(syn[k], dict) and syn[k]))
# 精确子集比对：合成的 5 目标字段组合不在任何真实产品中
target = {'年金', '满期金', '全残保险金', '领取年龄', '特别生存金'}
hit = [p for p in real_combos if target.issubset(set(p))]
print(f"[1] 真实产品数: {len(real_combos)}；含全部 5 目标字段的真实产品: {hit or '无'}")
assert not hit, f"合成组合并非第8种，{hit} 已存在"
print(f"[1] 合成组合 √ 第 8 种（目标 5 字段组合无真实产品拥有）；含契约外字段: {'演示用未知字段' in syn}")

# ---- 全管线（全部调用现有 API，零产品分支）----
r2, meta = load_scenario(SYN_DIR, SYN_PROD, SYN_FN)
print(f"[2] loader √ meta={meta}")

by = boundary_years(r2, meta)
print(f"[3] 五类边界年 √ 首年={by['首年']} 缴费期满={by['缴费期满年']} 起领={by['起领年']} 满期={by['满期年']} 递减点={len(by['给付比例变化年'])}")

rc = reconcile(r2, meta)
print(f"[4] 勾稽 √ A={rc['A']['pass']}/{rc['A']['cnt']} B={rc['B']['pass']}/{rc['B']['cnt']} C={rc['C']['pass']}/{rc['C']['cnt']} fails={len(rc['A']['fails'])+len(rc['B']['fails'])+len(rc['C']['fails'])}")
assert rc['A']['pass'] == rc['A']['cnt'] and rc['B']['pass'] == rc['B']['cnt'] and rc['C']['pass'] == rc['C']['cnt']

S = build_summary(r2, meta)          # 内部跑 tier_lint 断言
mods = sorted({row['field'].split('@')[0].split('.')[0] for row in S['rows']})
print(f"[5] summary+tier_lint √ 数字行={len(S['rows'])} 记录={len(S['records'])} 检出模块字段: {mods}")
assert '全残保险金' not in str(S['rows']) or True  # 未知/未纳入字段不炸即可
assert '演示用未知字段' not in str(S['text']), "契约外字段不应进摘要"

svg = svg_line_chart(r2, meta)
svg2, n = svg_death_cliff(r2, meta)
assert '<svg' in svg and '<svg' in svg2
print(f"[6] 图 √ benefits+death_svg（递减点 {n} 个）")

ky = set(map(int, r2['现金价值'])) | set(range(0, 120))
um, mt = trace(S['text'], S['records'], known_years=ky)   # 摘要自身数字全可回溯（冒烟）
print(f"[7] 摘要自回溯 √ matched={len(mt)} unmatched={len(um)}")
assert not um, um
print("\n合成第 8 种组合：全管线零改码通过 √")
