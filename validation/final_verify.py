# -*- coding: utf-8 -*-
"""M2 全产品终验（final_verify 全产品版）：扫 output/**/manifest.json，
对每份 narrative_final 跑四道检查：回引三元组 / 禁用词 / 输出层档位+区间绑定 / 免责与 markdown。
运行：python validation/final_verify.py   （exit 0 = 全部通过）
"""
import sys, os, json, glob, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.render.trace import trace
from src.render import banned_scan
from src.render.compliance import output_tier_lint
from src.render.summary import build_summary
from src.render.loader import load_scenario

DATA = os.path.join(os.path.dirname(ROOT), '保险运营程序设计与实践_作业材料', '利益演示数据')
DISC_BLOCK = ('本材料仅供教学研究使用，演示利益基于假设、不代表未来实际收益，'
              '红利分配不确定，具体以保险公司正式条款及保险单为准。')
DISC = ['仅供教学研究使用', '演示利益基于假设', '不代表未来实际收益', '红利分配不确定', '红利分配是不确定']

manifests = sorted(glob.glob(os.path.join(ROOT, 'output', '**', 'manifest.json'), recursive=True))
assert manifests, "没有找到任何 manifest.json"
allok = True
for mf in manifests:
    outdir = os.path.dirname(mf)
    man = json.load(open(mf, encoding='utf-8'))
    nf = os.path.join(outdir, 'narrative_final.txt')
    if not os.path.exists(nf):
        print(f"== {os.path.relpath(outdir, ROOT)}: 缺 narrative_final.txt -> 不通过")
        allok = False
        continue
    rec, meta = load_scenario(DATA, man['product'], man['fn'])
    S = build_summary(rec, meta)                 # tier_lint 断言在 build 内
    ky = set(map(int, rec['现金价值'])) | set(range(0, 120))
    text = open(nf, encoding='utf-8').read()
    um, mt = trace(text, S['records'], known_years=ky)
    bh = banned_scan.scan(text)
    tv = output_tier_lint(text, S['records'], ky, require_footer=True)   # 档位+区间+覆盖+源(含页脚存在性) 双断言
    n_dis = text.count('仅供教学研究使用')
    body = text.replace(DISC_BLOCK, '')
    n_left = sum(body.count(p) for p in DISC)
    md = '**' in text
    has_footer = ('数据来源：' in text and '获取时点：' in text)
    ok = not um and not bh and not tv and n_dis == 1 and n_left == 0 and not md and has_footer
    allok &= ok
    tier_n = sum(1 for v in tv if v.get('kind') == 'tier')
    rng_n = sum(1 for v in tv if v.get('kind') == 'range')
    cov_n = sum(1 for v in tv if v.get('kind') == 'coverage')
    src_n = sum(1 for v in tv if v.get('kind') == 'source')
    print(f"== {man['product'][:14]}|{re.split(r'[,，]', man['fn'])[1]}: 回引 unmatched={len(um)} matched={len(mt)} | "
          f"禁词={len(bh)} | 档位={tier_n} 区间={rng_n} 覆盖={cov_n} 源标注={src_n} | "
          f"免责 块={n_dis}/残留={n_left} | 页脚={'√' if has_footer else '×'} | md={md} -> {'通过' if ok else '不通过'}")
    for raw, d in um[:5]:
        print("   × unmatched:", raw, d)
    for v in tv[:5]:
        print("   × lint:", v)
    for h in bh[:5]:
        print("   × banned:", h)

print(f"\n共 {len(manifests)} 份报告；总判定:", "全部通过" if allok else "存在不通过")
sys.exit(0 if allok else 1)
