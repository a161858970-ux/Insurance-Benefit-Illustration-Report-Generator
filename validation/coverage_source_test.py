# -*- coding: utf-8 -*-
"""M3 三问坏样本测试（总控实抓文本）：
① coverage：长城旧稿缺 35/54/9820（年金流未呈现）→ 必须拦截；
② coverage：福临门旧稿缺 37/39/30000（特别生存金未呈现）→ 必须拦截；
③ source：终稿含"（源：保费@31..40）"→ sanitize 剥除 + source_lint 拦截；
   且"（区间 60–104 岁、共 45 个保单年度）"必须保留（B 条依赖）。
运行：python validation/coverage_source_test.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.render.compliance import coverage_lint, source_lint, sanitize

# ---- 真实流记录（按 build_summary 语义手工构造） ----
fl_records = [
    # 长城：年金 35–54 每年491 合计9820
    {'field': '年金', 'key': '35..54', 'tier': 'guar', 'variants': {'9820'},
     'hints': {'年金', '合计'}, 'wanyuan': False, 'kind': 'amount',
     'is_range': True, 'is_flow': True, 'range_tokens': {'35', '54', '20'}},
    # 长城：养老金 55–105 每年491 合计25041
    {'field': '养老金', 'key': '55..105', 'tier': 'guar', 'variants': {'25041'},
     'hints': {'养老金', '合计'}, 'wanyuan': False, 'kind': 'amount',
     'is_range': True, 'is_flow': True, 'range_tokens': {'55', '105', '51'}},
    # 福临门：特别生存金 37–39 合计30000
    {'field': '特别生存金', 'key': '37..39', 'tier': 'guar', 'variants': {'30000'},
     'hints': {'特别生存金', '合计'}, 'wanyuan': False, 'kind': 'amount',
     'is_range': True, 'is_flow': True, 'range_tokens': {'37', '39', '3'}},
]

# ① 长城旧稿真实句子（只有养老金流，缺年金流 35/54/9820）
gwm_old = ("您好，这是一份根据您情况准备的利益说明。\n"
           "在保单第1年末，保证的现金价值为4064元。\n"
           "到您55岁时，可以开始每年领取养老金491元，这笔钱在55–105岁、共51个保单年度内保证领取，合计为25041元。\n"
           "到您105岁时，生存总利益为64602元，是总投入保费的2.15倍。\n")
v1 = coverage_lint(gwm_old, fl_records)
ok1 = any('年金' in x['clause'] and ('35' in x['need'] or '缺' in x['need']) for x in v1)
# ① 修复版必须放行：补上 35–54/20/9820 与 37–39/3/30000
gwm_fixed = gwm_old + "\n合同还约定35岁起每年领取年金491元，35–54岁、共20个保单年度，合计9820元。\n"
v1b = coverage_lint(gwm_fixed, fl_records)
ok1b = not any('年金' in x['clause'] for x in v1b)

# ② 福临门旧稿模式（有累计领取合计但无特别生存金流）
flm_old = ("演示生存总利益107140.8元（演示、不保证）。\n")
v2 = coverage_lint(flm_old, fl_records)
ok2 = any('特别生存金' in x['clause'] for x in v2)
flm_fixed = flm_old + "\n37–39岁每年给付特别生存金10,000元，共3年，合计30000元。\n"
v2b = coverage_lint(flm_fixed, fl_records)
ok2b = not any('特别生存金' in x['clause'] for x in v2b)

# ③ 源标注：sanitize 剥除 + lint 拦截；区间标签保留
leaky = ("您每年交费10,000元（源：保费@31..40），累计100,000元（源：累交保费@40）。\n"
         "养老金合计31,500元（区间 60–104 岁、共 45 个保单年度）（源：养老金@60..104）。")
v3_before = source_lint(leaky)
clean = sanitize(leaky)
v3_after = source_lint(clean)
ok3 = bool(v3_before) and not v3_after and '源：' not in clean
ok3_keep = '区间 60–104 岁、共 45 个保单年度' in clean and '31,500' in clean

print(f"{'√' if ok1 else '×'} ① 长城稿缺年金流被拦截: {v1}")
print(f"{'√' if ok1b else '×'} ① 补齐年金流后放行: {v1b}")
print(f"{'√' if ok2 else '×'} ② 福临门稿缺特别生存金被拦截: {v2}")
print(f"{'√' if ok2b else '×'} ② 补齐后放行: {v2b}")
print(f"{'√' if ok3 else '×'} ③ 源标注: 拦截={v3_before} 剥除后={v3_after}")
print(f"{'√' if ok3_keep else '×'} ③ 区间标签保留: {clean!r}")
sys.exit(0 if all([ok1, ok1b, ok2, ok2b, ok3, ok3_keep]) else 1)
