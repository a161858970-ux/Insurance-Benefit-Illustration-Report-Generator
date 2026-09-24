# -*- coding: utf-8 -*-
"""坏样本拦截证明：v1 真实犯过的错（"演示领取合计"标在保证字段 养老金 上）
必须被 tier_lint 抛 TierAssertionError。运行：python validation/tier_assert_intercept.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.render.summary import tier_lint, TierAssertionError, tier_of

print("tier_of('养老金') =", tier_of('养老金'))                # 期望 guar
print("tier_of('红利.rate.生存总利益') =", tier_of('红利.rate.生存总利益'))  # 期望 demo
print("tier_of('IRR.hl') =", tier_of('IRR.hl'))               # 期望 demo
print("tier_of('IRR.bzhl') =", tier_of('IRR.bzhl'))           # 期望 guar

# 坏样本1：v1 原文（summary_for_llm.txt 第14行的错法）
bad_rows = [
    {'text': '- 养老金 演示领取合计（60–105 岁）：31,500 元（源：养老金@60..105）', 'field': '养老金'},
    {'text': '- 累计领取 演示合计：143,550 元（源：累计领取@41..105）', 'field': '累计领取'},
]
try:
    tier_lint(bad_rows)
    print("FAIL: 坏样本未被拦截")
    sys.exit(1)
except TierAssertionError as e:
    print("\n[拦截成功] TierAssertionError 抛出：")
    print(str(e))

# 坏样本2：手写 label 混入"演示"但字段是保证档
try:
    tier_lint([{'text': '- 演示利益下现金价值：10,380 元（源：现金价值@5）', 'field': '现金价值'}])
    print("FAIL: 坏样本2未被拦截")
    sys.exit(1)
except TierAssertionError as e:
    print("\n[拦截成功] 坏样本2：")
    print(str(e).splitlines()[1])

# 好样本必须放行
good_rows = [
    {'text': '- 养老金 领取合计（区间：60–104 岁、共 45 个保单年度）（保证）：31,500 元（源：养老金@60..104）', 'field': '养老金'},
    {'text': '- 生存总利益（演示、不保证）：101,590.06 元（源：红利.rate.生存总利益@105）', 'field': '红利.rate.生存总利益'},
]
tier_lint(good_rows)
print("\n好样本放行 OK。断言有效：坏样本 2/2 拦截、好样本通过。")
