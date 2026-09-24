# -*- coding: utf-8 -*-
"""输出层档位断言测试：好句放行、真实违规句（场景2 实抓）必须拦截。
运行：python validation/output_tier_lint_test.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.render.compliance import output_tier_lint, sanitize

records = [
    {'field': '养老金', 'key': '60..104', 'tier': 'guar', 'variants': {'143550'}, 'hints': {'养老金', '领取合计'}, 'wanyuan': False, 'kind': 'amount'},
    {'field': '养老金', 'key': '60..104', 'tier': 'guar', 'variants': {'31500'}, 'hints': {'养老金', '领取合计'}, 'wanyuan': False, 'kind': 'amount',
     'is_range': True, 'range_tokens': {'60', '104', '45'}},
    {'field': '红利.rate.生存总利益', 'key': '105', 'tier': 'demo', 'variants': {'451822.42'}, 'hints': {'生存总利益'}, 'wanyuan': False},
    {'field': 'IRR.hl', 'key': '105', 'tier': 'demo', 'variants': {'2.51'}, 'hints': {'IRR', '复利', '演示'}, 'wanyuan': False},
    {'field': 'IRR.bzhl', 'key': '105', 'tier': 'guar', 'variants': {'1.65'}, 'hints': {'IRR', '复利', '保证'}, 'wanyuan': False},
]
ky = set(range(0, 120))

bad = "根据演示，到104岁累计可领取45年，合计143,550元。"   # 场景2 实抓违规
bad2 = "根据演示，在60到104岁期间，累计可领取养老金31,500元（保证）。"  # 场景1 实抓：句内"（保证）"曾绕过断言
good1 = "若考虑分红（演示、不保证），生存总利益可能达到451,822.42元。"
good2 = "保证档IRR（复利）为1.65%；演示档IRR（复利）为2.51%（演示、不保证）。"
good3 = "从60岁开始，每年可领取3,190元养老金（保证）。"

v_bad = output_tier_lint(bad, records, ky)
v_bad2 = output_tier_lint(bad2, records, ky)
v1 = output_tier_lint(good1, records, ky)
v2 = output_tier_lint(good2, records, ky)
v3 = output_tier_lint(good3, records, ky)

ok = bool(v_bad) and bool(v_bad2) and not v1 and not v2 and not v3
print(f"{'√' if v_bad else '×'} 违规句1被拦截: {v_bad}")
print(f"{'√' if v_bad2 else '×'} 违规句2（含'（保证）'字样）被拦截: {v_bad2}")
print(f"{'√' if not v1 else '×'} good1 放行: {v1}")
print(f"{'√' if not v2 else '×'} good2 放行: {v2}")
print(f"{'√' if not v3 else '×'} good3 放行: {v3}")
dirty = '**加粗**\n）\n正文。'
print(f"sanitize({dirty!r}) -> {sanitize(dirty)!r}")
# ===== B 条：合计数字必须同句带区间标签 =====
from src.render.compliance import range_binding_lint
bad_range = "根据合同约定的领取区间，累计可领取31,500元。"            # 场景1 实抓：无 60/104/45
good_range = "从60岁起，每年700元，60–104岁共45个保单年度累计可领取31,500元。"
vr_bad = range_binding_lint(bad_range, records)
vr_good = range_binding_lint(good_range, records)
print(f"{'√' if vr_bad else '×'} 合计无区间被拦截: {vr_bad}")
print(f"{'√' if not vr_good else '×'} 合计带区间放行: {vr_good}")
ok = ok and bool(vr_bad) and not vr_good

# ===== A 条：标量字段给正确出处（10年 vs 10万元 不得张冠李戴）=====
from src.render.trace import trace as _trace
recs_a = [
    {'field': '交费期间', 'key': '10', 'tier': 'guar', 'variants': {'10'}, 'hints': {'交费期间', '交', '年交', '持续'}, 'wanyuan': False, 'kind': 'scalar'},
    {'field': '累交保费', 'key': '40', 'tier': 'guar', 'variants': {'10'}, 'hints': {'保费', '万元'}, 'wanyuan': True, 'kind': 'amount'},
    {'field': '累交保费', 'key': '40', 'tier': 'guar', 'variants': {'100000'}, 'hints': {'保费', '累计'}, 'wanyuan': False, 'kind': 'amount'},
]
_, mt_a = _trace("持续交10年，总投入是10万元", recs_a, known_years=set(range(0, 120)))
# 按出现顺序断言：第1个'10'（交10年）→标量；第2个'10'（10万元）→万元换算
a1 = (len(mt_a) == 2 and mt_a[0][1] == '交费期间@10[guar]'
      and '万元换算' in mt_a[1][1])
_, mt_b = _trace("总投入是10万元", recs_a, known_years=set(range(0, 120)))
b1 = len(mt_b) == 1 and '万元换算' in mt_b[0][1]
print(f"{'√' if a1 else '×'} 同句两个'10'分别归属: {mt_a}")
print(f"{'√' if b1 else '×'} '10万元' 归属 万元换算: {mt_b}")
ok = ok and a1 and b1

sys.exit(0 if ok else 1)
