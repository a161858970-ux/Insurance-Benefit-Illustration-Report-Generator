# -*- coding: utf-8 -*-
"""M3 三问坏样本测试（总控实抓文本）：
① coverage：长城旧稿缺 35/54/9820（年金流未呈现）→ 必须拦截；
② coverage：福临门旧稿缺 37/39/30000（特别生存金未呈现）→ 必须拦截；
③ source：终稿含"（源：保费@31..40）"→ sanitize 剥除 + source_lint 拦截；
   且"（区间 60–104 岁、共 45 个保单年度）"必须保留（B 条依赖）。
④ footer（M5/D053）：数据来源+获取时点页脚存在性坏样本 5 例
   （缺页脚拦 / 半截页脚拦 / 齐全放行且子串不误杀 / 正文泄漏仍拦 / 片段级不强求）。
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
# ④ 数据来源+获取时点页脚（M5 / 作业合规清单第2条，D053）——坏样本拦截证明
from src.render.compliance import source_lint as _sl, footer_block as _fb

body_only = "您好，这是一份根据您情况准备的利益说明。\n在保单第1年末，保证的现金价值为4064元。"
# ④-a 缺页脚 → require_footer=True 必须拦截（缺数据来源+缺获取时点 = 2 条）
v4a = _sl(body_only, require_footer=True)
ok4a = len(v4a) == 2 and {x['num'] for x in v4a} == {'数据来源：', '获取时点：'}
# ④-b 只有数据来源行、缺获取时点 → 拦截（防半截页脚蒙混）
v4b = _sl(body_only + "\n数据来源：课程作业材料《利益演示数据/》给定 JSON（p，f.json）", require_footer=True)
ok4b = len(v4b) == 1 and v4b[0]['num'] == '获取时点：'
# ④-c 页脚齐全 → 放行；且页脚"数据来源："含裸"源："子串不得误判为内部泄漏
full = body_only + "\n" + _fb('国寿鑫益延年养老年金保险（分红型）', '国寿鑫益延年养老年金保险（分红型）,男，30，10.json')
v4c = _sl(full, require_footer=True)
ok4c = not v4c
# ④-d 正文真泄漏 + 页脚齐全 → 仍必须拦截（先剥页脚再查，不掩盖正文泄漏）
leaky = "现金价值4064元（源：现金价值@31）。\n" + _fb('国寿鑫益延年养老年金保险（分红型）', '国寿鑫益延年养老年金保险（分红型）,男，30，10.json')
v4d = _sl(leaky, require_footer=True)
ok4d = len(v4d) == 1 and v4d[0]['num'] == '源：'
# ④-e require_footer=False（片段级调用，如 probe）不得强求页脚
v4e = _sl(body_only, require_footer=False)
ok4e = not v4e

print(f"{'√' if ok4a else '×'} ④-a 缺页脚被拦截: {[(x['clause'], x['num']) for x in v4a]}")
print(f"{'√' if ok4b else '×'} ④-b 缺获取时点被拦截: {[(x['clause'], x['num']) for x in v4b]}")
print(f"{'√' if ok4c else '×'} ④-c 页脚齐全放行（'数据来源：'子串不误杀）: {v4c}")
print(f"{'√' if ok4d else '×'} ④-d 正文真泄漏+页脚齐全仍拦截: {v4d}")
print(f"{'√' if ok4e else '×'} ④-e 片段级调用不强求页脚: {v4e}")

# ⑤ 句子级三查坏样本（M5/D058）：从不渲染的 m_disclaimer 死角句必须被句查拦截
from src.render.compliance import probe_violations as _pv

recs_t = [
    {'field': 'IRR.bzhl', 'key': '105', 'tier': 'guar', 'variants': {'1.65'},
     'hints': {'IRR', '复利', '保证'}, 'wanyuan': False},
    {'field': 'IRR.hl', 'key': '105', 'tier': 'demo', 'variants': {'2.51'},
     'hints': {'IRR', '复利', '演示'}, 'wanyuan': False},
]
# ⑤-a 实抓坏句（p_analyst m_disclaimer 死角句）：1.65 保证档落在演示语境 → 必拦
dead_bad = "保证与演示差额由IRR复利1.65%与2.51%量化。"
_, tv5, _ = _pv(dead_bad, recs_t, set(range(0, 120)))
ok5a = any(v.get('kind') == 'tier' and v.get('num') == '1.65' for v in tv5)
# ⑤-b 修正写法（两档显式分述）→ 放行
dead_good = "保证档IRR复利为1.65%，演示档IRR复利为2.51%（演示、不保证）。"
_, tv5b, _ = _pv(dead_good, recs_t, set(range(0, 120)))
ok5b = not tv5b
# ⑤-c 文档级 coverage 不得误伤片段（这正是句查与终稿 lint 的分界）
recs_flow = [{'field': '年金', 'key': '40..104', 'tier': 'guar', 'variants': {'3030'},
              'hints': {'年金', '合计'}, 'wanyuan': False, 'kind': 'amount',
              'is_range': True, 'is_flow': True, 'range_tokens': {'40', '104', '65'}}]
_, tvc, _ = _pv("每年领取年金491元。", recs_flow, set(range(0, 120)))
ok5c = not any(v.get('kind') == 'coverage' for v in tvc)

print(f"{'√' if ok5a else '×'} ⑤-a 死角句 tier 违规被句查拦截: {tv5}")
print(f"{'√' if ok5b else '×'} ⑤-b 两档分述句放行: {tv5b}")
print(f"{'√' if ok5c else '×'} ⑤-c 文档级 coverage 不误伤片段: {[v for v in tvc if v.get('kind')=='coverage']}")

sys.exit(0 if all([ok1, ok1b, ok2, ok2b, ok3, ok3_keep, ok4a, ok4b, ok4c, ok4d, ok4e,
                   ok5a, ok5b, ok5c]) else 1)
