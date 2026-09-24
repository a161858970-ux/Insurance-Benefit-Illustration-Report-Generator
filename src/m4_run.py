# -*- coding: utf-8 -*-
"""M4 驱动：9 份单段报告升级为模块化（flash 模型）。
场景 = 2 老份 + 7 产品场景分配表（与 m2 一致）；画像 = p_default。
含全残字段的产品（中意/鑫颐金生/福临门）在此跑出 m_death 全残分支真实产物。
运行：python src/m4_run.py
"""
import os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.render.loader import list_products, list_scenarios
from src.llm.client import load_config
from src.modular_run import run_modular
import re

DATA = load_config(os.path.join(ROOT, 'config.yaml'))['data']['benefit_data']
PROFILES = {}
_dec = json.JSONDecoder()
_pf = open(os.path.join(ROOT, 'profiles', 'profiles.jsonl'), encoding='utf-8').read()
_i = 0
while _i < len(_pf):
    _sp = _pf.find('{', _i)
    if _sp < 0:
        break
    obj, _i = _dec.raw_decode(_pf, _sp)
    PROFILES[obj['id']] = obj
P_DEFAULT = PROFILES['p_default']

SCENE_PLAN = {
    '中意永续我爱':   ('男', '0', '1'),
    '国寿鑫益延年':   ('女', '45', '10'),
    '国寿鑫颐一生':   ('男', '30', '10'),
    '国寿鑫颐金生':   ('女', '0', '10'),
    '国寿鸿盈金生':   ('男', '45', '1'),
    '瑞众福临门':     ('女', '30', '10'),
    '长城八达岭':     ('男', '45', '3'),
}
PRIORITY_FN_TAIL = ('30，10.json', '30，3.json', '30，1.json', '0，10.json', '0，1.json')

# 9 个目标：2 老份 + 7 产品
TARGETS = [
    ('国寿鑫益延年养老年金保险（分红型）', '国寿鑫益延年养老年金保险（分红型）,男，0，1.json', 'output/m1'),
    ('国寿鑫益延年养老年金保险（分红型）', '国寿鑫益延年养老年金保险（分红型）,男，30，10.json', 'output/m1_30y10'),
]

def main():
    print("=" * 72)
    print("[M4] 9 份单段 → 模块化（model=flash）")
    plan_names = list(SCENE_PLAN)
    for i, p in enumerate(list_products(DATA), 1):
        sns = list_scenarios(DATA, p)
        plan = next((v for k, v in SCENE_PLAN.items() if p.startswith(k)), None)
        fn = None
        if plan:
            g, a, pay = plan
            fn = next((f for f in sns if re.search(rf'[,，]{g}[,，]{a}[,，]{pay}\.json$', f)), None)
        if not fn:
            fn = next((f for t in PRIORITY_FN_TAIL for f in sns if f.endswith(t)), sns[0])
        TARGETS.append((p, fn, f"output/m2/{i}_{p[:6]}"))

    # 备份旧单段稿
    for _, _, outdir in TARGETS:
        nf = os.path.join(ROOT, outdir, 'narrative_final.txt')
        bak = os.path.join(ROOT, outdir, 'narrative_final_单段版.txt')
        if os.path.exists(nf) and not os.path.exists(bak):
            import shutil
            shutil.copy(nf, bak)

    results = []
    for i, (p, fn, outdir) in enumerate(TARGETS, 1):
        print("-" * 72)
        print(f"[{i}/9] {p} <- {fn.split('，')[1] if '，' in fn else fn[-18:]} -> {outdir}")
        r = run_modular(p, fn, os.path.join(ROOT, outdir), P_DEFAULT, log=print)
        # 全残分支产物检查
        has_all残 = '全残保险金' in json.load(open(os.path.join(ROOT, 'data_marker_skip') if False else os.path.join(ROOT, outdir, 'manifest.json'), encoding='utf-8')) if False else None
        results.append((p, fn, r['ok']))
        assert r['ok'], f"模块化失败: {p} {fn}"

    print("=" * 72)
    n_ok = sum(1 for _, _, ok in results if ok)
    print(f"M4 模块化: {n_ok}/9 全部通过")
    # 全残分支产物验证：中意/鑫颐金生/福临门 的终稿必须含"全残保险金"
    print("[M4-2] 全残分支真实产物检查:")
    for p, fn, _ in results:
        if any(k in p for k in ('中意', '鑫颐金生', '福临门')):
            outdir = next(o for pp, ff, o in TARGETS if pp == p and ff == fn)
            t = open(os.path.join(ROOT, outdir, 'narrative_final.txt'), encoding='utf-8').read()
            hit = '全残保险金' in t
            # 抽含全残的行
            line = next((l for l in t.splitlines() if '全残保险金' in l), '')
            print(f"  {'√' if hit else '×'} {p[:14]}: {line[:96]}")
            assert hit, f"{p} 全残未呈现"

if __name__ == '__main__':
    main()
