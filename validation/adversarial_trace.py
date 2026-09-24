# -*- coding: utf-8 -*-
"""对抗用例：同值多字段时回引出处必须三元组正确（SPEC §2.5）。
场景：26,500 元（现金价值@59）的万元换算 = 2.65，恰与 红利.guaranteed.收益倍数@59 = 2.65 同值；
     42,200 元（生存总利益@105）万元换算 = 4.22，恰与 收益倍数@105 = 4.22 同值。
运行：python validation/adversarial_trace.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.render.trace import trace

records = [
    {'field': '现金价值', 'key': '59', 'tier': 'guar', 'variants': {'26500', '26,500'}, 'hints': {'现金价值', '峰值', '最高'}, 'wanyuan': False},
    {'field': '现金价值', 'key': '59', 'tier': 'guar', 'variants': {'2.65'}, 'hints': {'现金价值', '万元'}, 'wanyuan': True},
    {'field': '红利.guaranteed.收益倍数', 'key': '59', 'tier': 'guar', 'variants': {'2.65'}, 'hints': {'收益倍数', '倍'}, 'wanyuan': False},
    {'field': '红利.guaranteed.生存总利益', 'key': '105', 'tier': 'guar', 'variants': {'42200', '42,200'}, 'hints': {'生存总利益'}, 'wanyuan': False},
    {'field': '红利.guaranteed.生存总利益', 'key': '105', 'tier': 'guar', 'variants': {'4.22'}, 'hints': {'生存总利益', '万元'}, 'wanyuan': True},
    {'field': '红利.guaranteed.收益倍数', 'key': '105', 'tier': 'guar', 'variants': {'4.22'}, 'hints': {'收益倍数', '倍'}, 'wanyuan': False},
    {'field': '红利.rate.生存总利益', 'key': '105', 'tier': 'demo', 'variants': {'101590.06', '101,590.06'}, 'hints': {'生存总利益'}, 'wanyuan': False},
    {'field': '红利.rate.生存总利益', 'key': '105', 'tier': 'demo', 'variants': {'10.16'}, 'hints': {'生存总利益', '万元'}, 'wanyuan': True},
    {'field': '红利.rate.收益倍数', 'key': '105', 'tier': 'demo', 'variants': {'10.16'}, 'hints': {'收益倍数', '倍'}, 'wanyuan': False},
]

cases = [
    # (文案, token, 期望出处描述)
    ("保证现金价值峰值为26,500元，是保费的2.65倍", '2.65', '红利.guaranteed.收益倍数@59[guar]'),
    ("保证现金价值峰值为26,500元，是保费的2.65倍", '26,500', '现金价值@59[guar]'),
    ("59岁时现金价值达2.65万元", '2.65', '现金价值@59(万元换算)[guar]'),
    ("保证生存总利益42,200元，收益倍数为4.22", '4.22', '红利.guaranteed.收益倍数@105[guar]'),
    ("保证生存总利益达4.22万元", '4.22', '红利.guaranteed.生存总利益@105(万元换算)[guar]'),
    ("演示生存总利益101,590.06元（演示、不保证），收益倍数10.16", '10.16', '红利.rate.收益倍数@105[demo]'),
    ("演示生存总利益达10.16万元（演示、不保证）", '10.16', '红利.rate.生存总利益@105(万元换算)[demo]'),
    # 无语境的同值 token 必须 AMBIG 判失败，不许乱挑出处
    ("数字10.16没有任何语境", '10.16', 'AMBIG'),
]

fails = 0
for text, token, expect in cases:
    um, mt = trace(text, records)
    got = None
    for raw, desc in mt:
        if raw.replace(',', '') == token.replace(',', ''):
            got = desc
    if got is None:
        for raw, desc in um:
            if raw.replace(',', '') == token.replace(',', ''):
                got = 'AMBIG 候选=' + desc.split('AMBIG ')[-1] if 'AMBIG' in desc else desc
                if 'AMBIG' in desc:
                    got = 'AMBIG'
    ok = (got == expect) if expect != 'AMBIG' else (got == 'AMBIG' or (got is None and any('AMBIG' in d for _, d in um)))
    fails += (not ok)
    print(f"{'√' if ok else '×'} token={token:>10} 期望={expect:<45} 实得={got}")

print(f"\n对抗用例: {len(cases)-fails}/{len(cases)} 通过")
sys.exit(1 if fails else 0)
