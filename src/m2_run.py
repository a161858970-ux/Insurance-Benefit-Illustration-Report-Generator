# -*- coding: utf-8 -*-
"""M2 驱动：通用渲染全链。
1) 84 文件全量勾稽 → 基线断言（A=6720/6720 B=5760/5760 C=12600/12600 失败=0）
2) 7 产品形态自动检测清单（字段集合，无人工分支）
3) 合成第 8 种字段组合自测（subprocess）
4) 7 产品各出 1 份完整报告（subprocess 调 src/m1_run.py，LLM 链）
5) final_verify 全产品终验（subprocess）
运行：python src/m2_run.py
"""
import os, sys, json, subprocess, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src.render.loader import load_scenario, list_products, list_scenarios
from src.render.reconcile import reconcile, aggregate

DATA = None
from src.llm.client import load_config
DATA = load_config(os.path.join(ROOT, 'config.yaml'))['data']['benefit_data']
PY = sys.executable

def run(script, *args):
    r = subprocess.run([PY, script, *args], capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=900)
    return r.returncode, (r.stdout or '') + (('\n[stderr] ' + r.stderr) if r.returncode else '')

# ---------- 1) 全量勾稽 ----------
print("=" * 72)
print("[M2-1] 全量勾稽（84 文件）")
results, n = [], 0
for p in list_products(DATA):
    for fn in list_scenarios(DATA, p):
        rec, meta = load_scenario(DATA, p, fn)
        results.append(reconcile(rec, meta)); n += 1
tot = aggregate(results)
print(f"  文件数={n}  A={tot['A']['pass']}/{tot['A']['cnt']}  B={tot['B']['pass']}/{tot['B']['cnt']}  "
      f"C={tot['C']['pass']}/{tot['C']['cnt']}  失败={tot['A']['fails']+tot['B']['fails']+tot['C']['fails']}")
base_ok = (tot['A'] == {'pass': 6720, 'cnt': 6720, 'fails': 0}
           and tot['B'] == {'pass': 5760, 'cnt': 5760, 'fails': 0}
           and tot['C'] == {'pass': 12600, 'cnt': 12600, 'fails': 0} and n == 84)
print("  基线 A=6720 B=5760 C=12600(双档) 失败=0:", "√ 一致" if base_ok else "× 不一致")
assert base_ok, tot

# ---------- 2) 形态清单 ----------
print("=" * 72)
print("[M2-2] 形态自动检测（字段集合，无人工分支）")
CORE = {'性别', '年龄', '交费期间', '保费', '累交保费', '现金价值', '身故保险金', '红利', 'IRR', '单利利率'}
OPTIONAL = ['养老金', '年金', '满期金', '特别生存金', '累计领取', '领取年龄', '全残保险金']
for p in list_products(DATA):
    fn0 = list_scenarios(DATA, p)[0]
    r0, _ = load_scenario(DATA, p, fn0)
    opt = [f for f in OPTIONAL if f in r0]
    shape = '领取现金流型' if ('养老金' in r0 or '年金' in r0) else '纯增长型(增额寿类)'
    print(f"  {p[:20]:<22} 形态={shape}  可选模块={opt}")

# ---------- 3) 合成第8种组合 ----------
print("=" * 72)
print("[M2-3] 合成第 8 种字段组合自测")
rc, out = run(os.path.join('validation', 'synthetic_combination_test.py'))
print(out)
assert rc == 0, "合成自测失败"

# ---------- 4) 7 产品报告 ----------
print("=" * 72)
print("[M2-4] 7 产品各出 1 份完整报告")
# 场景多样性分配（M3-5）：0/30/45 岁 × 男女 × 1/3/10 年交 全覆盖
SCENE_PLAN = {
    '中意永续我爱':            ('男', '0', '1'),
    '国寿鑫益延年':            ('女', '45', '10'),
    '国寿鑫颐一生':            ('男', '30', '10'),
    '国寿鑫颐金生':            ('女', '0', '10'),
    '国寿鸿盈金生':            ('男', '45', '1'),
    '瑞众福临门':              ('女', '30', '10'),
    '长城八达岭':              ('男', '45', '3'),
}
PRIORITY_FN_TAIL = ('30，10.json', '30，3.json', '30，1.json', '0，10.json', '0，1.json')
manifest_report = []
for i, p in enumerate(list_products(DATA), 1):
    sns = list_scenarios(DATA, p)
    # 分配表优先（场景多样性），缺失回退 PRIORITY
    plan = next((v for k, v in SCENE_PLAN.items() if p.startswith(k)), None)
    fn = None
    if plan:
        g, a, pay = plan
        fn = next((f for f in sns if re.search(rf'[,，]{g}[,，]{a}[,，]{pay}\.json$', f)), None)
    if not fn:
        fn = next((f for t in PRIORITY_FN_TAIL for f in sns if f.endswith(t)), sns[0])
    outdir = f"m2/{i}_{p[:6]}"
    rc, out = run(os.path.join('src', 'm1_run.py'), fn, outdir)
    tag = "√" if rc == 0 else "×"
    print(f"  {tag} [{i}/7] {p[:20]} <- {re.split(r'[,，]', fn)[1:]} out={outdir}")
    if rc != 0:
        print(out[-2500:])
    manifest_report.append((p, fn, outdir, rc))
    assert rc == 0, f"报告生成失败: {p}"

# ---------- 5) 全产品终验 ----------
print("=" * 72)
print("[M2-5] final_verify 全产品终验")
rc, out = run(os.path.join('validation', 'final_verify.py'))
print(out)
assert rc == 0, "final_verify 未全过"

print("=" * 72)
print(f"M2 全链完成：84 文件勾稽 √ | 形态清单 √ | 合成第8组合 √ | 7 报告 √ | 终验 √")
